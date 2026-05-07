from flask import Blueprint, render_template, request, jsonify
from app import db
from app.database import Queues, Triggers, Schedulers, Jobs
from datetime import datetime, timedelta

bp = Blueprint("stats", __name__, url_prefix="/stats")


@bp.route("/")
def stats():
    """Render the Statistics overview page."""
    return render_template("stats.html", page="Stats")


@bp.route("/queue_names")
def queue_names():
    """Distinct queue names (for the savings calculator dropdown)."""
    rows = (
        db.session.query(Queues.queue_name)
        .distinct()
        .order_by(Queues.queue_name.asc())
        .all()
    )
    return jsonify([r[0] for r in rows if r[0] is not None])


@bp.route("/savings")
def savings():
    """
    Calculate hours saved for a given queue between two dates.
    Counts queue elements with status DONE, multiplies by minutes_per_item.
    """
    queue_name = request.args.get("queue_name", "", type=str)
    minutes_per_item = request.args.get("minutes_per_item", 0, type=float)
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)

    if not queue_name:
        return jsonify({"error": "queue_name is required"}), 400

    query = db.session.query(db.func.count()).filter(
        Queues.queue_name == queue_name,
        Queues.status == "DONE",
    )
    if start_date:
        query = query.filter(Queues.end_date >= datetime.strptime(start_date, "%Y-%m-%dT%H:%M"))
    if end_date:
        query = query.filter(Queues.end_date <= datetime.strptime(end_date, "%Y-%m-%dT%H:%M"))

    done_count = query.scalar() or 0
    minutes_saved = done_count * minutes_per_item
    hours_saved = round(minutes_saved / 60.0, 2)

    return jsonify({
        "queue_name": queue_name,
        "done_count": done_count,
        "minutes_per_item": minutes_per_item,
        "minutes_saved": minutes_saved,
        "hours_saved": hours_saved,
    })


@bp.route("/scheduler_health")
def scheduler_health():
    """Scheduler ping freshness — green/yellow/red per machine."""
    now = datetime.now()
    rows = []
    for s in db.session.query(Schedulers).order_by(Schedulers.machine_name.asc()).all():
        delta = (now - s.last_update) if s.last_update else timedelta.max
        if delta < timedelta(minutes=5):
            health = "online"
        elif delta < timedelta(minutes=30):
            health = "stale"
        else:
            health = "offline"
        rows.append({
            "machine_name": s.machine_name,
            "health": health,
            "last_update": s.last_update.strftime("%d-%m-%Y %H:%M:%S") if s.last_update else None,
            "minutes_since": int(delta.total_seconds() // 60) if s.last_update else None,
            "latest_trigger": s.latest_trigger,
        })
    return jsonify(rows)


@bp.route("/downtime")
def downtime():
    """
    Per-trigger run summary based on Jobs (OO 3.0).
    Returns counts and average duration over the supplied window.
    """
    days = request.args.get("days", 30, type=int)
    since = datetime.now() - timedelta(days=days)

    rows = (
        db.session.query(
            Jobs.process_name,
            Jobs.status,
            db.func.count().label("cnt"),
        )
        .filter(Jobs.start_time >= since)
        .group_by(Jobs.process_name, Jobs.status)
        .all()
    )

    by_process = {}
    for process_name, status, cnt in rows:
        bucket = by_process.setdefault(process_name, {
            "process_name": process_name,
            "RUNNING": 0, "DONE": 0, "FAILED": 0, "KILLED": 0, "total": 0,
        })
        if status in bucket:
            bucket[status] += cnt
        bucket["total"] += cnt

    return jsonify({"days": days, "rows": list(by_process.values())})
