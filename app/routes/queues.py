import uuid

from flask import Blueprint, render_template, request, jsonify, url_for
from app import db
from app.database import Queues, QueueTriggers, Triggers, queue_handled_t
from sqlalchemy.sql import column
from datetime import datetime
from app.helper_tables import mark_queue_handled, mark_log_viewed
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, exists, and_, func, case

bp = Blueprint('queues', __name__, url_prefix='/queues')

@bp.route('/')
def queues():
    """Render the queues overview page."""
    return render_template('tables/queues.html', page='Queues')

@bp.route('/data')
def get_queues_data():
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "FAILED")
    order = request.args.get("order", "desc")
    search = request.args.get("search", "", type=str)
    has_failed = request.args.get("has_failed", "false").lower() == "true"
    has_new = request.args.get("has_new", "false").lower() == "true"
    has_done = request.args.get("has_done", "false").lower() == "true"
    has_in_progress = request.args.get("has_in_progress", "false").lower() == "true"
    has_abandoned = request.args.get("has_abandoned", "false").lower() == "true"
    start_date = request.args.get("start_date", "", type=str)
    end_date = request.args.get("end_date", "", type=str)
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")

    # 1) Base-filter
    q = db.session.query(
        Queues.queue_name,
        Queues.status,
        db.func.count().label("cnt"),
    )

    if search:
        q = q.filter(Queues.queue_name.ilike(f"%{search}%"))
    if start_date:
        q = q.filter(Queues.created_date >= start_date)
    if end_date:
        q = q.filter(Queues.created_date <= end_date)

    status_counts = (
        q.group_by(Queues.queue_name, Queues.status)
         .all()
    )

    # 2) Separat query: hvor mange FAILED er markeret handled pr queue
    #    (join på helper-tabellen og group_by queue_name)
    handled_failed_counts = (
        db.session.query(
            Queues.queue_name,
            db.func.count().label("handled_failed"),
        )
        .join(queue_handled_t, queue_handled_t.c.queue_id == Queues.id)
        .filter(Queues.status == "FAILED")
        .group_by(Queues.queue_name)
        .all()
    )

    handled_failed_by_queue = {qn: c for qn, c in handled_failed_counts}

    # 3) Saml som dict (samme idé som logs.py)
    queue_counts = {}
    for queue_name, status, cnt in status_counts:
        if queue_name not in queue_counts:
            queue_counts[queue_name] = {
                "NEW": 0,
                "IN_PROGRESS": 0,
                "DONE": 0,
                "FAILED": 0,
                "ABANDONED": 0,
                "Total": 0,
            }
        s = (status or "").upper()
        if s in queue_counts[queue_name]:
            queue_counts[queue_name][s] += cnt
        queue_counts[queue_name]["Total"] += cnt

    # 4) Træk handled FAILED fra FAILED
    for queue_name, handled_failed in handled_failed_by_queue.items():
        if queue_name in queue_counts:
            queue_counts[queue_name]["FAILED"] = max(
                0,
                queue_counts[queue_name]["FAILED"] - handled_failed
            )

    # 5) Apply has_* filters after aggregation, build rows, propagate filters to detail link.
    active_status_filters = {
        "FAILED": has_failed,
        "NEW": has_new,
        "DONE": has_done,
        "IN_PROGRESS": has_in_progress,
        "ABANDONED": has_abandoned,
    }
    detail_kwargs = {}
    if start_date:
        detail_kwargs["start_date"] = start_date.strftime("%Y-%m-%dT%H:%M")
    if end_date:
        detail_kwargs["end_date"] = end_date.strftime("%Y-%m-%dT%H:%M")
    # If exactly one status filter is on, drill into the detail page filtered to that status.
    active_count = sum(1 for v in active_status_filters.values() if v)
    if active_count == 1:
        for status, on in active_status_filters.items():
            if on:
                detail_kwargs["filter_status"] = status
                break

    rows = []
    for queue_name, counts in queue_counts.items():
        # If any status filters are active, the queue must have >0 in at least one of them.
        if active_count > 0 and not any(
            counts[status] > 0 for status, on in active_status_filters.items() if on
        ):
            continue
        link = url_for("queues.queues_detail", queue_name=queue_name, **detail_kwargs)
        rows.append({
            "queue_name": queue_name,
            **counts,
            "Actions": f'<a href="{link}" class="btn btn-primary btn-sm">View Queue Items</a>',
        })

    reverse = (order.lower() == "desc")
    if sort not in {"queue_name", "NEW", "IN_PROGRESS", "DONE", "FAILED", "ABANDONED", "Total"}:
        sort = "FAILED"

    rows.sort(key=lambda r: (r[sort] if sort != "queue_name" else (r["queue_name"] or "")), reverse=reverse)

    total_count = len(rows)
    if limit is not None:
        rows = rows[offset: offset + limit]
    else:
        rows = rows[offset:]

    return jsonify({"total": total_count, "rows": rows})

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

    handled_exists = exists(
        select(1).select_from(queue_handled_t).where(queue_handled_t.c.queue_id == Queues.id)
    )

    if filter_status:
        if filter_status == "HANDLED":
            base_query = base_query.filter(Queues.status == "FAILED", handled_exists)
        elif filter_status == "FAILED":
            base_query = base_query.filter(Queues.status == "FAILED", ~handled_exists)
        else:
            base_query = base_query.filter(Queues.status == filter_status)

    if start_date and end_date:
        base_query = base_query.filter(Queues.start_date >= start_date, Queues.end_date <= end_date)
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

    result_ids = [r.id for r in results]
    handled_ids = set()
    if result_ids:
        handled_ids = set(
            db.session.execute(
                select(queue_handled_t.c.queue_id).where(queue_handled_t.c.queue_id.in_(result_ids))
            ).scalars().all()
        )

    formatted_rows = []
    for row in results:
        row_dict = {
            "id": row.id,
            "queue_name": row.queue_name,
            "status": ("HANDLED" if (row.status == "FAILED" and row.id in handled_ids) else row.status),
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

    # Tilføj HANDLED som filtervalg, hvis der findes handled rows for denne queue
    has_handled = db.session.execute(
        select(1)
        .select_from(queue_handled_t)
        .join(Queues, queue_handled_t.c.queue_id == Queues.id)
        .where(Queues.queue_name == queue_name)
        .limit(1)
    ).first() is not None

    if has_handled and "HANDLED" not in status_list:
        status_list.append("HANDLED")


    return jsonify(status_list)


def _parse_optional_dt(value):
    if not value:
        return None
    # Accept "YYYY-MM-DDTHH:MM" (datetime-local) or already-formatted "DD-MM-YYYY HH:MM".
    for fmt in ("%Y-%m-%dT%H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime format: {value}")


@bp.route('/element/<element_id>')
def get_queue_element(element_id):
    """Return a single queue element for the edit modal."""
    row = db.session.query(Queues).filter_by(id=element_id).first()
    if not row:
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({
        "success": True,
        "element": {
            "id": str(row.id),
            "queue_name": row.queue_name,
            "status": row.status,
            "data": row.data,
            "reference": row.reference,
            "message": row.message,
            "created_by": row.created_by,
            "created_date": row.created_date.strftime("%Y-%m-%dT%H:%M") if row.created_date else None,
            "start_date": row.start_date.strftime("%Y-%m-%dT%H:%M") if row.start_date else None,
            "end_date": row.end_date.strftime("%Y-%m-%dT%H:%M") if row.end_date else None,
        },
    })


@bp.route('/create_element', methods=['POST'])
def create_queue_element():
    """Create a new queue element. Matches OO 3.0 popup behavior."""
    data = request.json or {}
    queue_name = data.get("queue_name")
    if not queue_name:
        return jsonify({"success": False, "error": "queue_name is required"}), 400

    try:
        new_id = str(uuid.uuid4()).upper()
        created_date = _parse_optional_dt(data.get("created_date")) or datetime.now()
        new_row = Queues(
            id=new_id,
            queue_name=queue_name,
            status=data.get("status") or "NEW",
            data=data.get("data") or None,
            reference=data.get("reference") or None,
            message=data.get("message") or None,
            created_by=data.get("created_by") or "FlaskOrchestrator UI",
            created_date=created_date,
            start_date=_parse_optional_dt(data.get("start_date")),
            end_date=_parse_optional_dt(data.get("end_date")),
        )
        db.session.add(new_row)
        db.session.commit()
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/edit_element', methods=['POST'])
def edit_queue_element():
    """Edit fields on a single queue element. Matches OO 3.0 popup behavior."""
    data = request.json or {}
    element_id = data.get("id")
    if not element_id:
        return jsonify({"success": False, "error": "id is required"}), 400

    row = db.session.query(Queues).filter_by(id=element_id).first()
    if not row:
        return jsonify({"success": False, "error": "Queue element not found"}), 404

    try:
        if "status" in data:
            row.status = data["status"]
        if "data" in data:
            row.data = data["data"]
        if "reference" in data:
            row.reference = data["reference"]
        if "message" in data:
            row.message = data["message"]
        if "created_date" in data:
            row.created_date = _parse_optional_dt(data["created_date"])
        if "start_date" in data:
            row.start_date = _parse_optional_dt(data["start_date"])
        if "end_date" in data:
            row.end_date = _parse_optional_dt(data["end_date"])
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


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


@bp.route("/toggle_handled", methods=["POST"])
def toggle_handled():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    try:
        # Kun FAILED kan toggles
        failed_ids = [
            r[0] for r in db.session.query(Queues.id)
            .filter(Queues.id.in_(ids), Queues.status == "FAILED")
            .all()
        ]
        if not failed_ids:
            return jsonify({"success": False, "error": "Only failed queue elements can be toggled."}), 400

        existing = set(
            db.session.execute(
                select(queue_handled_t.c.queue_id).where(queue_handled_t.c.queue_id.in_(failed_ids))
            ).scalars().all()
        )

        to_insert = [qid for qid in failed_ids if qid not in existing]
        to_delete = [qid for qid in failed_ids if qid in existing]

        # Insert nye
        for qid in to_insert:
            mark_queue_handled(qid)

        # Delete eksisterende
        if to_delete:
            db.session.execute(
                queue_handled_t.delete().where(queue_handled_t.c.queue_id.in_(to_delete))
            )

        db.session.commit()
        return jsonify({
            "success": True,
            "marked": len(to_insert),
            "unmarked": len(to_delete),
            "ignored_non_failed": len(ids) - len(failed_ids)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
