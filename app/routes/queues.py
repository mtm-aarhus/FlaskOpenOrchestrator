from flask import Blueprint, render_template, request, jsonify, url_for
from app import db
from app.database import Queues, QueueTriggers, Triggers
from sqlalchemy.sql import column
from datetime import datetime

bp = Blueprint('queues', __name__, url_prefix='/queues')

@bp.route('/')
def queues():
    """Render the queues overview page."""
    return render_template('tables/queues.html', page='Queues')

@bp.route('/data')
def get_queues_data():
    """Return queue overview data with counts for different statuses."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "FAILED")
    order = request.args.get("order", "desc")
    search = request.args.get("search", "", type=str)

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()

    base_query = db.session.query(Queues.queue_name)

    if search:
        base_query = base_query.filter(Queues.queue_name.ilike(f"%{search}%"))
    query = (
        base_query.with_entities(
            Queues.queue_name,
            db.func.sum(db.case((Queues.status == "NEW", 1), else_=0)).label("NEW"),
            db.func.sum(db.case((Queues.status == "IN_PROGRESS", 1), else_=0)).label("IN_PROGRESS"),
            db.func.sum(db.case((Queues.status == "DONE", 1), else_=0)).label("DONE"),
            db.func.sum(db.case((Queues.status == "FAILED", 1), else_=0)).label("FAILED"),
            db.func.sum(db.case((Queues.status == "ABANDONED", 1), else_=0)).label("ABANDONED"),
            db.func.count().label("Total"),
        )
        .group_by(Queues.queue_name)
        .order_by(order_by)
        .offset(offset)
        .limit(limit)
    )

    total_count = base_query.distinct().count()
    results = query.all()

    formatted_rows = [
        {
            "queue_name": row.queue_name,
            "NEW": row.NEW,
            "IN_PROGRESS": row.IN_PROGRESS,
            "DONE": row.DONE,
            "FAILED": row.FAILED,
            "ABANDONED": row.ABANDONED,
            "Total": row.Total,
            "Actions": f'<a href="{url_for("queues.queues_detail", queue_name=row.queue_name)}" class="btn btn-primary btn-sm">View Queue Items</a>',
        }
        for row in results
    ]

    return jsonify({"total": total_count, "rows": formatted_rows})


@bp.route('/<queue_name>')
def queues_detail(queue_name):
    """Render queue details page with optional filters."""
    start_date = request.args.get("start_date") 
    end_date = request.args.get("end_date")
    
    return render_template(
        "tables/queues_detail.html", queue_name=queue_name, start_date=start_date, end_date=end_date, page='Queues'
    )

@bp.route('/<queue_name>/data')
def get_queue_detail_data(queue_name):
    """Return queue detail data with filtering, sorting, and pagination."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "created_date")
    order = request.args.get("order", "desc")
    filter_status = request.args.get("filter_status", "", type=str)
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)
    search = request.args.get("search", "", type=str)
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()

    base_query = db.session.query(Queues).filter(Queues.queue_name == queue_name)

    if filter_status:
        base_query = base_query.filter(Queues.status == filter_status)
    if start_date and end_date:
        base_query =     base_query = base_query.filter(Queues.start_date >= start_date, Queues.end_date <= end_date)
    if search:
        base_query = base_query.filter(
            (Queues.message.ilike(f"%{search}%")) |
            (Queues.data.ilike(f"%{search}%")) |
            (Queues.reference.ilike(f"%{search}%")) |
            (Queues.created_by.ilike(f"%{search}%"))
        )

    total_count = base_query.count()

    results = (
        base_query
        .order_by(order_by)
        .offset(offset)
        .limit(limit)
        .all()
    )

    formatted_rows = []
    for row in results:
        row_dict = {
            "id": row.id,
            "queue_name": row.queue_name,
            "status": row.status,
            "data": row.data,
            "reference": row.reference,
            "created_date": row.created_date,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "message": row.message,
            "created_by": row.created_by,
        }

        for key in ["created_date", "start_date", "end_date"]:
            if row_dict[key]:
                if isinstance(row_dict[key], str):
                    try:
                        row_dict[key] = datetime.strptime(row_dict[key], "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        row_dict[key] = datetime.strptime(row_dict[key], "%Y-%m-%d %H:%M:%S")
                row_dict[key] = row_dict[key].strftime("%d-%m-%Y %H:%M")

        formatted_rows.append(row_dict)

    return jsonify({"total": total_count, "rows": formatted_rows})

@bp.route('/update_status', methods=['POST'])
def update_queue_status():
    """Update status of selected queue items."""
    data = request.json
    selected_ids = data.get("ids", [])
    new_status = data.get("status", "NEW")  

    if not selected_ids:
        return jsonify({"success": False, "error": "No queue IDs provided"}), 400

    try:
        db.session.query(Queues).filter(Queues.id.in_(selected_ids)).update({"status": new_status}, synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/<queue_name>/status')
def get_queue_status(queue_name):
    """Return distinct queue statuses for a specific queue."""
    statuses = (
        db.session.query(Queues.status)
        .filter(Queues.queue_name == queue_name)
        .distinct()
        .order_by(Queues.status.asc())
        .all()
    )

    # Ensure we return a flat list instead of a list of tuples
    status_list = [status[0] for status in statuses if status[0] is not None]

    return jsonify(status_list)


@bp.route('/delete', methods=['POST'])
def delete_selected_queues():
    """Delete selected queue items."""
    data = request.json
    selected_ids = data.get("ids", [])

    if not selected_ids:
        return jsonify({"success": False, "error": "No queue IDs provided"}), 400

    try:
        db.session.query(Queues).filter(Queues.id.in_(selected_ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    
@bp.route("/get_process_name")
def get_process_name():
    """Fetch process name based on queue name via queue_triggers & triggers."""
    queue_name = request.args.get("queue_name")

    # Step 1: Lookup queue in queue_triggers to find trigger_id
    queue_trigger = db.session.query(QueueTriggers).filter_by(queue_name=queue_name).first()
    if not queue_trigger:
        return jsonify({"success": False, "error": "Queue trigger not found"}), 404

    # Step 2: Lookup trigger in triggers to fetch process_name
    trigger = db.session.query(Triggers).filter_by(id=queue_trigger.id).first()
    if not trigger:
        return jsonify({"success": False, "error": "Trigger not found"}), 404

    return jsonify({"success": True, "process_name": trigger.process_name})

