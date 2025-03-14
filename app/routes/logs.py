from flask import Blueprint, render_template, request, jsonify
from app import db
from app.database import Logs
from datetime import datetime

bp = Blueprint('logs', __name__, url_prefix='/logs')

@bp.route('/')
def logs():
    """Render the logs overview page with grouped log counts."""
    results = (
        db.session.query(
            Logs.process_name, 
            Logs.log_level, 
            db.func.count().label("count")
        )
        .group_by(Logs.process_name, Logs.log_level)
        .all()
    )

    log_counts = {}
    for process_name, log_level, count in results:
        if process_name not in log_counts:
            log_counts[process_name] = {'Total': 0, 'TRACE': 0, 'INFO': 0, 'ERROR': 0}
        log_counts[process_name][log_level.upper()] = count
        log_counts[process_name]['Total'] += count

    return render_template('tables/logs.html', log_counts=log_counts, page='Logs')

@bp.route('/<process_name>/log_levels')
def get_log_levels(process_name):
    """Return a list of distinct log levels for a specific process."""
    levels = (
        db.session.query(Logs.log_level)
        .filter(Logs.process_name == process_name) 
        .distinct()
        .order_by(Logs.log_level.asc())
        .all()
    )

    return jsonify([level[0] for level in levels if level[0] is not None]) 

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
    """Return log entries for a specific process with pagination, filtering, and sorting."""
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

    # Apply filters
    if filter_level:
        query = query.filter(Logs.log_level == filter_level)
    if start_date and end_date:
        query = query.filter(Logs.log_time.between(start_date, end_date))
    if search:
        query = query.filter(
            (Logs.log_message.ilike(f"%{search}%")) | 
            (Logs.log_level.ilike(f"%{search}%"))
        )

    # Apply sorting & pagination
    if order.lower() == "desc":
        query = query.order_by(getattr(Logs, sort).desc())
    else:
        query = query.order_by(getattr(Logs, sort))

    total_count = query.count()
    rows = query.offset(offset).limit(limit).all()

    formatted_rows = [
        {
            "id": row.id, 
            "log_time": row.log_time.strftime("%Y-%m-%d %H:%M:%S"),  # Convert datetime to string
            "log_level": row.log_level, 
            "process_name": row.process_name, 
            "log_message": row.log_message
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
