from flask import Blueprint, render_template, url_for, jsonify
from datetime import datetime, timedelta
from sqlalchemy import cast, Date
from app import db
from app.database import Logs, Queues, Triggers  

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

    # Fetch 5 most recent error logs
    recent_errors = (
        db.session.query(Logs)
        .filter(Logs.log_level.ilike("ERROR"), Logs.log_time >= time_range)
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

    #  Fetch 5 most recent failed queue elements
    recent_failed_queues = (
        db.session.query(Queues)
        .filter(Queues.status.ilike("FAILED"))
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
        .filter(Triggers.process_status.ilike("FAILED"))
        .order_by(Triggers.trigger_name.asc())
        .all()
    )

    failed_trigger_list = [
        {
            "name": trigger.trigger_name,
            "process": trigger.process_name,
            "status": trigger.process_status,
            "link": url_for("triggers.triggers"), 
        }
        for trigger in failed_triggers
    ]

    return render_template(
        "index.html",
        error_logs=error_logs,
        failed_queues=failed_queues,
        failed_triggers=failed_trigger_list,
        page='Home'
    )

@bp.route("/performance")
def queue_performance():
    """Return queue success vs failed counts for the last 4 days."""
    now = datetime.now()
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4, -1, -1)]

    success_counts = []
    failed_counts = []

    for day in days:
        start_of_day = datetime.strptime(day, "%Y-%m-%d")
        end_of_day = start_of_day + timedelta(days=1)

        success_count = db.session.query(Queues).filter(
            Queues.status.ilike("DONE"),
            Queues.created_date >= start_of_day,
            Queues.created_date < end_of_day
        ).count()

        failed_count = db.session.query(Queues).filter(
            Queues.status.ilike("FAILED"),
            Queues.created_date >= start_of_day,
            Queues.created_date < end_of_day
        ).count()

        success_counts.append(success_count)
        failed_counts.append(failed_count)

    return jsonify({"dates": days, "success": success_counts, "failed": failed_counts})