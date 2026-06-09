import uuid
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, url_for
from sqlalchemy import and_, case, exists, func, literal, or_, select

from app import db
from app.database import QueueTriggers, Queues, Triggers, queue_handled_t
from app.helper_tables import mark_queue_handled

bp = Blueprint("queues", __name__, url_prefix="/queues")

STATUS_FILTERS = {
    "FAILED": "has_failed",
    "NEW": "has_new",
    "DONE": "has_done",
    "IN_PROGRESS": "has_in_progress",
    "ABANDONED": "has_abandoned",
}


def _parse_filter_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime format: {value}")


def _parse_end_date_window(start_value, end_value):
    start_dt = _parse_filter_datetime(start_value)
    end_dt = _parse_filter_datetime(end_value)
    # datetime-local has minute precision. Treat the "to" minute as inclusive.
    if end_dt:
        end_dt = end_dt + timedelta(minutes=1)
    return start_dt, end_dt


@bp.route("/")
def queues():
    """Render the queues overview page."""
    return render_template("tables/queues.html", page="Queues")


@bp.route("/data")
def get_queues_data():
    start_date_raw = request.args.get("start_date", "", type=str)
    end_date_raw = request.args.get("end_date", "", type=str)
    start_date, end_date = _parse_end_date_window(start_date_raw, end_date_raw)

    active_status_filters = {
        status: request.args.get(param, "false").lower() == "true"
        for status, param in STATUS_FILTERS.items()
    }
    active_count = sum(1 for v in active_status_filters.values() if v)
    selected_statuses = [status for status, on in active_status_filters.items() if on]

    include_failed_count = not selected_statuses or "FAILED" in selected_statuses
    handled_ids = None
    if include_failed_count:
        handled_ids = (
            select(queue_handled_t.c.queue_id)
            .group_by(queue_handled_t.c.queue_id)
            .subquery()
        )

    def status_count(status):
        if status == "FAILED":
            if not include_failed_count:
                return literal(0)
            predicate = and_(Queues.status == "FAILED", handled_ids.c.queue_id.is_(None))
        else:
            predicate = Queues.status == status
        return func.sum(case((predicate, 1), else_=0))

    count_exprs = {status: status_count(status) for status in STATUS_FILTERS}
    statuses_to_count = selected_statuses or list(STATUS_FILTERS.keys())
    total_exprs = [count_exprs[status] for status in statuses_to_count]
    total_expr = total_exprs[0]
    for expr in total_exprs[1:]:
        total_expr = total_expr + expr

    q = db.session.query(
        Queues.queue_name.label("queue_name"),
        count_exprs["NEW"].label("NEW"),
        count_exprs["IN_PROGRESS"].label("IN_PROGRESS"),
        count_exprs["DONE"].label("DONE"),
        count_exprs["FAILED"].label("FAILED"),
        count_exprs["ABANDONED"].label("ABANDONED"),
        total_expr.label("Total"),
    )

    if handled_ids is not None:
        q = q.outerjoin(
            handled_ids,
            and_(Queues.status == "FAILED", handled_ids.c.queue_id == Queues.id),
        )

    if start_date:
        q = q.filter(or_(Queues.end_date >= start_date, Queues.end_date.is_(None)))
    if end_date:
        q = q.filter(or_(Queues.end_date < end_date, Queues.end_date.is_(None)))
    if selected_statuses:
        q = q.filter(Queues.status.in_(selected_statuses))

    grouped = q.group_by(Queues.queue_name).having(total_expr > 0).subquery()

    rows_query = db.session.query(
        grouped.c.queue_name,
        grouped.c.NEW,
        grouped.c.IN_PROGRESS,
        grouped.c.DONE,
        grouped.c.FAILED,
        grouped.c.ABANDONED,
        grouped.c.Total,
    ).order_by(
        func.coalesce(grouped.c.FAILED, 0).desc(),
        grouped.c.queue_name.asc(),
    )
    result_rows = rows_query.all()

    detail_kwargs = {}
    if start_date_raw:
        detail_kwargs["start_date"] = start_date_raw
    if active_count == 1:
        for status, on in active_status_filters.items():
            if on:
                detail_kwargs["filter_status"] = status
                break
    if end_date_raw and detail_kwargs.get("filter_status") not in {"NEW", "IN_PROGRESS"}:
        detail_kwargs["end_date"] = end_date_raw

    rows = []
    for row in result_rows:
        counts = {
            "NEW": int(row.NEW or 0),
            "IN_PROGRESS": int(row.IN_PROGRESS or 0),
            "DONE": int(row.DONE or 0),
            "FAILED": int(row.FAILED or 0),
            "ABANDONED": int(row.ABANDONED or 0),
            "Total": int(row.Total or 0),
        }
        link = url_for("queues.queues_detail", queue_name=row.queue_name, **detail_kwargs)
        rows.append({
            "queue_name": row.queue_name,
            **counts,
            "Actions": f'<a href="{link}" class="btn btn-primary btn-sm">View Queue Items</a>',
        })

    return jsonify({"total": len(rows), "rows": rows})


@bp.route("/<queue_name>")
def queues_detail(queue_name):
    """Render queue details page with optional filters."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    return render_template(
        "tables/queues_detail.html",
        queue_name=queue_name,
        start_date=start_date,
        end_date=end_date,
        page="Queues",
    )


@bp.route("/<queue_name>/data")
def get_queue_detail_data(queue_name):
    """Return queue detail data with filtering, sorting, and pagination."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    sort = request.args.get("sort", "created_date")
    order = request.args.get("order", "desc")
    filter_status = request.args.get("filter_status", "", type=str)
    start_date_raw = request.args.get("start_date", "", type=str)
    end_date_raw = request.args.get("end_date", "", type=str)
    search = request.args.get("search", "", type=str)
    start_date, end_date = _parse_end_date_window(start_date_raw, end_date_raw)

    sort_columns = {
        "id": Queues.id,
        "status": Queues.status,
        "data": Queues.data,
        "reference": Queues.reference,
        "created_date": Queues.created_date,
        "start_date": Queues.start_date,
        "end_date": Queues.end_date,
        "message": Queues.message,
        "created_by": Queues.created_by,
    }
    sort_col = sort_columns.get(sort, Queues.created_date)
    order_by = sort_col.desc() if order.lower() == "desc" else sort_col.asc()

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

    if start_date:
        base_query = base_query.filter(or_(Queues.end_date >= start_date, Queues.end_date.is_(None)))
    if end_date:
        base_query = base_query.filter(or_(Queues.end_date < end_date, Queues.end_date.is_(None)))
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


@bp.route("/update_status", methods=["POST"])
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


@bp.route("/<queue_name>/status")
def get_queue_status(queue_name):
    """Return distinct queue statuses for a specific queue."""
    statuses = (
        db.session.query(Queues.status)
        .filter(Queues.queue_name == queue_name)
        .distinct()
        .order_by(Queues.status.asc())
        .all()
    )

    status_list = [status[0] for status in statuses if status[0] is not None]

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
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime format: {value}")


@bp.route("/element/<element_id>")
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


@bp.route("/create_element", methods=["POST"])
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


@bp.route("/edit_element", methods=["POST"])
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


@bp.route("/delete", methods=["POST"])
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
    """Fetch process name based on queue name via queue_triggers and triggers."""
    queue_name = request.args.get("queue_name")

    queue_trigger = db.session.query(QueueTriggers).filter_by(queue_name=queue_name).first()
    if not queue_trigger:
        return jsonify({"success": False, "error": "Queue trigger not found"}), 404

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

        for qid in to_insert:
            mark_queue_handled(qid)

        if to_delete:
            db.session.execute(
                queue_handled_t.delete().where(queue_handled_t.c.queue_id.in_(to_delete))
            )

        db.session.commit()
        return jsonify({
            "success": True,
            "marked": len(to_insert),
            "unmarked": len(to_delete),
            "ignored_non_failed": len(ids) - len(failed_ids),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
