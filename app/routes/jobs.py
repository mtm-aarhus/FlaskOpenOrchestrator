from flask import Blueprint, render_template, request, jsonify
from app import db
from app.database import Jobs, Logs, Triggers
from sqlalchemy.sql import column
from datetime import datetime

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@bp.route("/")
def jobs():
    """Render the Jobs overview page."""
    return render_template("tables/jobs.html", page="Jobs")


@bp.route("/data")
def get_jobs_data():
    """Server-side pagination/sort/filter for Jobs."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "start_time")
    order = request.args.get("order", "desc")
    search = request.args.get("search", "", type=str)
    filter_status = request.args.get("filter_status", "", type=str)
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)

    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")

    query = db.session.query(Jobs)

    if search:
        query = query.filter(
            db.or_(
                Jobs.process_name.ilike(f"%{search}%"),
                Jobs.scheduler_name.ilike(f"%{search}%"),
            )
        )
    if filter_status:
        query = query.filter(Jobs.status == filter_status)
    if start_date and end_date:
        query = query.filter(Jobs.start_time.between(start_date, end_date))

    sort_col = getattr(Jobs, sort, Jobs.start_time)
    query = query.order_by(sort_col.desc() if order.lower() == "desc" else sort_col.asc())

    total_count = query.count()
    rows = query.offset(offset).limit(limit).all()

    # ONE grouped query for all visible jobs instead of N per-row counts.
    # Without an index on Logs.job_id this is still much faster than the loop:
    # it lets the optimizer pick an IN-list strategy and avoids N round-trips.
    log_counts = {}
    if rows:
        job_ids = [r.id for r in rows]
        log_counts = dict(
            db.session.query(Logs.job_id, db.func.count())
            .filter(Logs.job_id.in_(job_ids))
            .group_by(Logs.job_id)
            .all()
        )

    formatted_rows = []
    for row in rows:
        formatted_rows.append({
            "id": str(row.id),
            "process_name": row.process_name,
            "scheduler_name": row.scheduler_name,
            "status": row.status,
            "start_time": row.start_time.strftime("%d-%m-%Y %H:%M:%S") if row.start_time else "",
            "end_time": row.end_time.strftime("%d-%m-%Y %H:%M:%S") if row.end_time else "",
            # ISO form for client-side live-ticking duration on RUNNING rows.
            "start_time_iso": row.start_time.isoformat() if row.start_time else None,
            "end_time_iso":   row.end_time.isoformat() if row.end_time else None,
            "duration": _duration_str(row.start_time, row.end_time),
            "log_count": log_counts.get(row.id, 0),
        })

    return jsonify({"total": total_count, "rows": formatted_rows})


@bp.route("/statuses")
def get_job_statuses():
    """Distinct job statuses for the filter dropdown."""
    rows = db.session.query(Jobs.status).distinct().order_by(Jobs.status.asc()).all()
    return jsonify([s[0] for s in rows if s[0] is not None])


@bp.route("/<job_id>")
def job_detail(job_id):
    """Render a job's linked logs."""
    job = db.session.query(Jobs).filter_by(id=job_id).first()
    if not job:
        return ("Job not found", 404)
    return render_template("tables/jobs_detail.html", job=job, job_id=job_id, page="Jobs")


@bp.route("/<job_id>/logs")
def get_job_logs(job_id):
    """Server-side data for a job's linked logs."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "log_time")
    order = request.args.get("order", "desc")

    query = db.session.query(Logs).filter(Logs.job_id == job_id)
    sort_col = getattr(Logs, sort, Logs.log_time)
    query = query.order_by(sort_col.desc() if order.lower() == "desc" else sort_col.asc())

    total_count = query.count()
    rows = query.offset(offset).limit(limit).all()

    formatted = [
        {
            "id": str(row.id),
            "log_time": row.log_time.strftime("%Y-%m-%d %H:%M:%S") if row.log_time else "",
            "log_level": row.log_level,
            "process_name": row.process_name,
            "log_message": row.log_message,
        }
        for row in rows
    ]
    return jsonify({"total": total_count, "rows": formatted})


@bp.route("/<job_id>/kill", methods=["POST"])
def kill_job(job_id):
    """
    Request a kill for a running job. Mirrors what the OO 3.0 Orchestrator does:
    we flip the matching trigger's process_status to KILLING. The scheduler that
    owns this job picks up the change, kills the process tree, and writes both
    Jobs.status = KILLED and Triggers.process_status = KILLED.
    """
    job = db.session.query(Jobs).filter_by(id=job_id).first()
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404
    if job.status != "RUNNING":
        return jsonify({
            "success": False,
            "error": f"Job is not running (status={job.status}); nothing to kill.",
        }), 400

    # Find the trigger that's currently running this process. Prefer scheduler match.
    candidates = (
        db.session.query(Triggers)
        .filter(
            Triggers.process_name == job.process_name,
            Triggers.process_status.in_(("RUNNING", "PAUSING")),
        )
        .all()
    )
    if not candidates:
        return jsonify({
            "success": False,
            "error": "No trigger currently in RUNNING state for this process. "
                     "If the scheduler died, mark the job KILLED via the force-reset.",
        }), 400

    # Single trigger → easy. Multiple → take the one whose scheduler_whitelist contains
    # this job's scheduler_name (best heuristic available without a job→trigger link).
    if len(candidates) == 1:
        target = candidates[0]
    else:
        target = next(
            (t for t in candidates if (t.scheduler_whitelist or "").find(job.scheduler_name) >= 0),
            candidates[0],
        )

    try:
        target.process_status = "KILLING"
        db.session.commit()
        return jsonify({"success": True, "trigger_id": str(target.id)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/<job_id>/force_kill", methods=["POST"])
def force_kill_job(job_id):
    """Force-mark a job as KILLED. Used when the scheduler is dead and the kill request can't be honored."""
    job = db.session.query(Jobs).filter_by(id=job_id).first()
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404
    try:
        job.status = "KILLED"
        if not job.end_time:
            job.end_time = datetime.now()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


def _duration_str(start, end):
    if not start:
        return ""
    end = end or datetime.now()
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"
