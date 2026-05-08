from flask import Blueprint, render_template, url_for, jsonify
from datetime import datetime, timedelta
from sqlalchemy import cast, Date, exists, select
from app import db
from app.database import Logs, Queues, Triggers, log_viewed_t, queue_handled_t

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    """Render the homepage with recent error logs, failed queue elements, and failed triggers."""
    now = datetime.now()
    weekday = now.weekday()  # Monday=0, Sunday=6

    # Determine time range: 72 hours (Sat–Mon) or 48 hours (Tue–Fri)
    time_range = now - timedelta(hours=72 if weekday in {5, 6, 0} else 48)

    def format_datetime(value):
        """Ensure datetime conversion before formatting."""
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value

    # Fetch 5 most recent error logs (exclude VIEWED)
    viewed_exists = (
        exists(
            select(1)
            .select_from(log_viewed_t)
            .where(log_viewed_t.c.log_id == Logs.id)
        )
        .correlate(Logs)
    )

    recent_errors = (
        db.session.query(Logs)
        .filter(
            Logs.log_level == "ERROR",
            Logs.log_time >= time_range,
            ~viewed_exists
        )
        .order_by(Logs.log_time.desc())
        .limit(5)
        .all()
    )


    error_logs = [
        {
            "time": format_datetime(log.log_time).strftime("%d-%m-%Y %H:%M"),
            "process": log.process_name[:34] + ("..." if len(log.process_name) > 34 else ""),
            "message": log.log_message[:34] + ("..." if len(log.log_message) > 34 else ""),
            "link": url_for(
                "logs.view_logs", 
                process_name=log.process_name,
                start_date=(format_datetime(log.log_time) - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                end_date=(format_datetime(log.log_time) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")            ),
        }
        for log in recent_errors
    ]

    # Fetch 5 most recent failed queue elements (exclude HANDLED)
    handled_exists = (
        exists(
            select(1)
            .select_from(queue_handled_t)
            .where(queue_handled_t.c.queue_id == Queues.id)
        )
        .correlate(Queues)
    )

    recent_failed_queues = (
        db.session.query(Queues)
        .filter(
            Queues.status == "FAILED",
            ~handled_exists
        )
        .order_by(Queues.end_date.desc())
        .limit(5)
        .all()
    )



    failed_queues = [
        {
            "failed": format_datetime(queue.end_date).strftime("%d-%m-%Y %H:%M"),
            "queue_name": queue.queue_name[:34] + ("..." if len(queue.queue_name) > 34 else ""),
            "reference": queue.reference[:34] + ("..." if len(queue.reference) > 34 else "") if queue.reference else "-",
            "link": url_for(
                "queues.queues_detail",  
                queue_name=queue.queue_name,
                start_date=format_datetime(queue.start_date).strftime("%Y-%m-%d %H:%M"),
                end_date=(format_datetime(queue.end_date)+ timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                filter_status=queue.status
            ),
        }
        for queue in recent_failed_queues
    ]

    # Fetch all "FAILED" triggers
    failed_triggers = (
        db.session.query(Triggers)
        .filter(Triggers.process_status == "FAILED")
        .order_by(Triggers.trigger_name.asc())
        .all()
    )

    failed_trigger_list = [
        {
            "name": trigger.trigger_name,
            "process": trigger.process_name,
            "status": trigger.process_status,
            # Deep-link to the triggers page with this exact trigger pre-filtered.
            "link": url_for(
                "triggers.triggers",
                search=trigger.trigger_name,
                status_filter="FAILED",
            ),
        }
        for trigger in failed_triggers
    ]

    # KPI counts for the home dashboard.
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {
        "failed_triggers": len(failed_triggers),
        # All-time: every unhandled FAILED queue element regardless of when it failed.
        "failed_queues_total": db.session.query(db.func.count())
            .select_from(Queues)
            .filter(
                Queues.status == "FAILED",
                ~handled_exists,
            )
            .scalar() or 0,
        "recent_errors": db.session.query(db.func.count())
            .select_from(Logs)
            .filter(
                Logs.log_level == "ERROR",
                Logs.log_time >= time_range,
                ~viewed_exists,
            )
            .scalar() or 0,
        "done_today": db.session.query(db.func.count())
            .select_from(Queues)
            .filter(
                Queues.status == "DONE",
                Queues.end_date >= today_start,
            )
            .scalar() or 0,
    }

    return render_template(
        "index.html",
        error_logs=error_logs,
        failed_queues=failed_queues,
        failed_triggers=failed_trigger_list,
        counts=counts,
        # Used by the "Done today" KPI card to deep-link with a today-range filter.
        today_iso=today_start.strftime("%Y-%m-%dT%H:%M"),
        tomorrow_iso=(today_start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        page='Home'
    )

@bp.route("/performance")
def queue_performance():
    """Return queue success vs failed counts for the last 5 days. Two grouped queries total."""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days = [today_start - timedelta(days=i) for i in range(4, -1, -1)]
    window_start = days[0]
    window_end = today_start + timedelta(days=1)

    handled_exists = (
        exists(
            select(1)
            .select_from(queue_handled_t)
            .where(queue_handled_t.c.queue_id == Queues.id)
        )
        .correlate(Queues)
    )

    day_col = cast(Queues.created_date, Date).label("d")

    # One grouped query for success counts.
    success_rows = (
        db.session.query(day_col, db.func.count())
        .filter(
            Queues.status == "DONE",
            Queues.created_date >= window_start,
            Queues.created_date < window_end,
        )
        .group_by(day_col)
        .all()
    )
    success_by_day = {d.strftime("%Y-%m-%d"): c for d, c in success_rows}

    # One grouped query for failed counts (excluding handled).
    failed_rows = (
        db.session.query(day_col, db.func.count())
        .filter(
            Queues.status == "FAILED",
            Queues.created_date >= window_start,
            Queues.created_date < window_end,
            ~handled_exists,
        )
        .group_by(day_col)
        .all()
    )
    failed_by_day = {d.strftime("%Y-%m-%d"): c for d, c in failed_rows}

    days_iso = [d.strftime("%Y-%m-%d") for d in days]
    return jsonify({
        "dates": days_iso,
        "success": [success_by_day.get(d, 0) for d in days_iso],
        "failed":  [failed_by_day.get(d, 0)  for d in days_iso],
    })