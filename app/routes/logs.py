from flask import Blueprint, render_template, request, jsonify
from app import db
from app.database import Logs, log_viewed_t
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, exists
from app.helper_tables import mark_log_viewed
from sqlalchemy.sql import column

bp = Blueprint('logs', __name__, url_prefix='/logs')

@bp.route('/')
def logs():
    """Render the logs overview page with grouped log counts (ERROR excludes VIEWED)."""

    # 1) Tæl alle logs pr process og level
    results = (
        db.session.query(
            Logs.process_name,
            Logs.log_level,
            db.func.count().label("count"),
        )
        .group_by(Logs.process_name, Logs.log_level)
        .all()
    )

    # 2) Tæl viewed ERROR pr process (separat)
    viewed_error = (
        db.session.query(
            Logs.process_name,
            db.func.count().label("viewed_error"),
        )
        .join(log_viewed_t, log_viewed_t.c.log_id == Logs.id)
        .filter(Logs.log_level == "ERROR")
        .group_by(Logs.process_name)
        .all()
    )
    viewed_error_by_process = {p: c for p, c in viewed_error}

    # 3) Merge i Python (samme stil som queues)
    log_counts = {}
    for process_name, log_level, count in results:
        if process_name not in log_counts:
            log_counts[process_name] = {'Total': 0, 'TRACE': 0, 'INFO': 0, 'ERROR': 0}

        lvl = (log_level or "").upper()
        if lvl in log_counts[process_name]:
            log_counts[process_name][lvl] += count
            log_counts[process_name]['Total'] += count

    # 4) Træk viewed ERROR fra ERROR
    for process_name, vcount in viewed_error_by_process.items():
        if process_name in log_counts:
            log_counts[process_name]['ERROR'] = max(0, log_counts[process_name]['ERROR'] - vcount)

    return render_template('tables/logs.html', log_counts=log_counts, page='Logs')


@bp.route('/<process_name>/log_levels')
def get_log_levels(process_name):
    levels = (
        db.session.query(Logs.log_level)
        .filter(Logs.process_name == process_name)
        .distinct()
        .order_by(Logs.log_level.asc())
        .all()
    )

    level_list = [lvl[0] for lvl in levels if lvl[0] is not None]

    has_viewed = db.session.execute(
        select(1)
        .select_from(log_viewed_t)
        .join(Logs, log_viewed_t.c.log_id == Logs.id)
        .where(Logs.process_name == process_name, Logs.log_level == "ERROR")
        .limit(1)
    ).first() is not None

    if has_viewed and "VIEWED" not in level_list:
        level_list.append("VIEWED")

    return jsonify(level_list)


@bp.route('/<process_name>')
def view_logs(process_name):
    """Render the detailed log page for a specific process."""
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    filter_level = request.args.get("filter_level", "")

    return render_template(
        'tables/logs_detail.html',
        process_name=process_name,
        start_date=start_date,
        end_date=end_date,
        filter_level=filter_level,
        page='Logs'
    )


@bp.route('/<process_name>/data')
def get_logs_data(process_name):
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "log_time")
    order = request.args.get("order", "desc")
    filter_level = request.args.get("filter_level", "", type=str)
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)
    search = request.args.get("search", "", type=str)

    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")

    query = db.session.query(Logs).filter(Logs.process_name == process_name)

    viewed_exists = (
        exists(
            select(1)
            .select_from(log_viewed_t)
            .where(log_viewed_t.c.log_id == Logs.id)
        )
        .correlate(Logs)
    )

    # Filter
    if filter_level:
        if filter_level == "VIEWED":
            query = query.filter(Logs.log_level == "ERROR", viewed_exists)
        elif filter_level == "ERROR":
            query = query.filter(Logs.log_level == "ERROR", ~viewed_exists)
        else:
            query = query.filter(Logs.log_level == filter_level)

    if start_date and end_date:
        query = query.filter(Logs.log_time.between(start_date, end_date))

    if search:
        query = query.filter(
            (Logs.log_message.ilike(f"%{search}%")) |
            (Logs.log_level.ilike(f"%{search}%"))
        )

    # Sort (samme mønster som din gamle, fungerende kode)
    sort_col = getattr(Logs, sort, Logs.log_time)
    query = query.order_by(sort_col.desc() if order.lower() == "desc" else sort_col.asc())

    total_count = query.count()
    rows = query.offset(offset).limit(limit).all()

    row_ids = [r.id for r in rows]
    viewed_ids = set()
    if row_ids:
        viewed_ids = set(
            db.session.execute(
                select(log_viewed_t.c.log_id).where(log_viewed_t.c.log_id.in_(row_ids))
            ).scalars().all()
        )

    formatted_rows = [
        {
            "id": row.id,
            "log_time": row.log_time.strftime("%Y-%m-%d %H:%M:%S") if row.log_time else "",
            "log_level": ("VIEWED" if (row.log_level == "ERROR" and row.id in viewed_ids) else row.log_level),
            "process_name": row.process_name,
            "log_message": row.log_message,
        }
        for row in rows
    ]

    return jsonify({"total": total_count, "rows": formatted_rows})


@bp.route('/delete', methods=['POST'])
def delete_logs():
    """Delete selected log entries."""
    data = request.json
    if not data or "ids" not in data or not data["ids"]:
        return jsonify({"error": "No IDs provided"}), 400

    try:
        db.session.query(Logs).filter(Logs.id.in_(data["ids"])).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "success": False}), 500

@bp.route('/<process_name>/delete_all', methods=['POST'])
def delete_all_logs(process_name):
    """Delete all log entries for a specific process."""
    try:
        db.session.query(Logs).filter(Logs.process_name == process_name).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
        
@bp.route("/toggle_viewed", methods=["POST"])
def toggle_viewed():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    try:
        # Kun ERROR kan toggles
        error_ids = [
            r[0] for r in db.session.query(Logs.id)
            .filter(Logs.id.in_(ids), Logs.log_level == "ERROR")
            .all()
        ]
        if not error_ids:
            return jsonify({"success": False, "error": "Only error logs can be toggled."}), 400

        existing = set(
            db.session.execute(
                select(log_viewed_t.c.log_id).where(log_viewed_t.c.log_id.in_(error_ids))
            ).scalars().all()
        )

        to_insert = [lid for lid in error_ids if lid not in existing]
        to_delete = [lid for lid in error_ids if lid in existing]

        for lid in to_insert:
            mark_log_viewed(lid)

        if to_delete:
            db.session.execute(
                log_viewed_t.delete().where(log_viewed_t.c.log_id.in_(to_delete))
            )

        db.session.commit()
        return jsonify({
            "success": True,
            "marked": len(to_insert),
            "unmarked": len(to_delete),
            "ignored_non_error": len(ids) - len(error_ids)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route("/all")
def view_all_logs():
    """Render the detailed log page for ALL processes."""
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    filter_level = request.args.get("filter_level", "")

    return render_template(
        "tables/logs_all.html",
        start_date=start_date,
        end_date=end_date,
        filter_level=filter_level,
        page="Logs",
    )

@bp.route("/all/data")
def get_all_logs_data():
    """Return log entries across ALL processes with pagination, filtering, and sorting."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "log_time")
    order = request.args.get("order", "desc")

    filter_level = request.args.get("filter_level", "", type=str)
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)
    search = request.args.get("search", "", type=str)

    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")

    query = db.session.query(Logs)

    if filter_level:
        query = query.filter(Logs.log_level == filter_level)
    if start_date and end_date:
        query = query.filter(Logs.log_time.between(start_date, end_date))
    if search:
        query = query.filter(
            (Logs.log_message.ilike(f"%{search}%")) |
            (Logs.log_level.ilike(f"%{search}%")) |
            (Logs.process_name.ilike(f"%{search}%"))
        )

    if order.lower() == "desc":
        query = query.order_by(getattr(Logs, sort).desc())
    else:
        query = query.order_by(getattr(Logs, sort))

    total_count = query.count()
    rows = query.offset(offset).limit(limit).all()

    formatted_rows = [
        {
            "id": row.id,
            "log_time": row.log_time.strftime("%Y-%m-%d %H:%M:%S"),
            "log_level": row.log_level,
            "process_name": row.process_name,
            "log_message": row.log_message,
        }
        for row in rows
    ]

    return jsonify({"total": total_count, "rows": formatted_rows})

@bp.route("/all/log_levels")
def get_all_log_levels():
    levels = (
        db.session.query(Logs.log_level)
        .filter(Logs.log_level.isnot(None))
        .distinct()
        .order_by(Logs.log_level.asc())
        .all()
    )
    level_list = [lvl[0] for lvl in levels if lvl[0] is not None]

    has_viewed = db.session.execute(
        select(1)
        .select_from(log_viewed_t)
        .join(Logs, log_viewed_t.c.log_id == Logs.id)
        .where(Logs.log_level == "ERROR")
        .limit(1)
    ).first() is not None

    if has_viewed and "VIEWED" not in level_list:
        level_list.append("VIEWED")

    return jsonify(level_list)