from flask import Blueprint, request, jsonify, render_template
from app import db
from app.database import Triggers, SingleTriggers, ScheduledTriggers, QueueTriggers
from sqlalchemy.sql import column
from cronsim import CronSim
from datetime import datetime
import uuid

bp = Blueprint('triggers', __name__, url_prefix='/triggers')

@bp.route('/')
def triggers():
    """Render the triggers overview page."""
    return render_template('tables/triggers.html', page='Triggers')

@bp.route('/data')
def get_triggers_data():
    """Return triggers data with filtering, sorting, and pagination."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", None, type=int)
    search = request.args.get("search", "", type=str)
    sort = request.args.get("sort", "trigger_name")
    order = request.args.get("order", "desc")

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()

    base_query = (
        db.session.query(
            Triggers.id,
            Triggers.trigger_name,
            Triggers.process_name,
            Triggers.process_path,
            Triggers.process_status,
            Triggers.process_args,
            Triggers.type,
            Triggers.is_git_repo,
            Triggers.is_blocking,
            SingleTriggers.next_run.label("single_next_run"),
            ScheduledTriggers.next_run.label("scheduled_next_run"),
            ScheduledTriggers.cron_expr,
            QueueTriggers.queue_name,
            QueueTriggers.min_batch_size,
            Triggers.last_run,
            db.case(
                (Triggers.type == "SCHEDULED", ScheduledTriggers.next_run),
                (Triggers.type == "SINGLE", SingleTriggers.next_run),
                else_=None
            ).label("next_run")
        )
        .outerjoin(SingleTriggers, Triggers.id == SingleTriggers.id)
        .outerjoin(ScheduledTriggers, Triggers.id == ScheduledTriggers.id)
        .outerjoin(QueueTriggers, Triggers.id == QueueTriggers.id)
    )

    if search:
        base_query = base_query.filter(
            db.or_(
                Triggers.trigger_name.ilike(f"%{search}%"),
                Triggers.process_name.ilike(f"%{search}%"),
                Triggers.process_path.ilike(f"%{search}%"),
                Triggers.process_status.ilike(f"%{search}%"),
                QueueTriggers.queue_name.ilike(f"%{search}%")
            )
        )

    # Get the total filtered count
    total_count = base_query.with_entities(db.func.count()).scalar()

    # Apply sorting, pagination, and get results
    paginated_query = base_query.order_by(order_by).offset(offset).limit(limit)
    results = paginated_query.all()

    formatted_rows = []
    for row in results:
        row_dict = {
            "id": row.id,
            "trigger_name": row.trigger_name,
            "process_name": row.process_name,
            "process_path": row.process_path,
            "process_status": row.process_status,
            "process_args": row.process_args,
            "type": row.type,
            "is_git_repo": row.is_git_repo,
            "is_blocking": row.is_blocking,
            "single_next_run": row.single_next_run,
            "scheduled_next_run": row.scheduled_next_run,
            "cron_expr": row.cron_expr,
            "queue_name": row.queue_name,
            "min_batch_size": row.min_batch_size,
            "last_run": row.last_run,
            "next_run": row.next_run,
        }

        for key in ["last_run", "next_run"]:
            if row_dict[key]:
                if isinstance(row_dict[key], str):
                    try:
                        row_dict[key] = datetime.strptime(row_dict[key], "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        row_dict[key] = datetime.strptime(row_dict[key], "%Y-%m-%d %H:%M:%S")
                row_dict[key] = row_dict[key].strftime("%d-%m-%Y %H:%M")

        formatted_rows.append(row_dict)

    return jsonify({"total": total_count, "rows": formatted_rows})


@bp.route('/edit', methods=['POST'])
def edit_trigger():
    """Edit an existing trigger and update corresponding sub-table."""
    data = request.json
    trigger_id = data.get("id")
    trigger_type = data.get("type")

    if not trigger_id:
        return jsonify({"success": False, "error": "Trigger ID is required for editing"}), 400

    try:
        # Update main trigger table
        trigger = db.session.query(Triggers).filter_by(id=trigger_id).first()
        if not trigger:
            return jsonify({"success": False, "error": "Trigger not found"}), 404

        trigger.trigger_name = data["trigger_name"]
        trigger.process_name = data["process_name"]
        trigger.process_path = data["process_path"]
        trigger.process_args = data.get("process_args", "")
        trigger.is_git_repo = data.get("is_git_repo", False)
        trigger.is_blocking = data.get("is_blocking", False)

        # Handle different trigger types
        if trigger_type == "SINGLE":
            next_run = parse_datetime(data["single_next_run"])
            single_trigger = db.session.query(SingleTriggers).filter_by(id=trigger_id).first()
            if single_trigger:
                single_trigger.next_run = next_run
            else:
                db.session.add(SingleTriggers(id=trigger_id, next_run=next_run))

        elif trigger_type == "SCHEDULED":
            cron_expr = data["cron_expr"]
            next_run = parse_datetime(data["scheduled_next_run"])
            scheduled_trigger = db.session.query(ScheduledTriggers).filter_by(id=trigger_id).first()
            if scheduled_trigger:
                scheduled_trigger.cron_expr = cron_expr
                scheduled_trigger.next_run = next_run
            else:
                db.session.add(ScheduledTriggers(id=trigger_id, cron_expr=cron_expr, next_run=next_run))

        elif trigger_type == "QUEUE":
            queue_name = data["queue_name"]
            min_batch_size = data["min_batch_size"]
            queue_trigger = db.session.query(QueueTriggers).filter_by(id=trigger_id).first()
            if queue_trigger:
                queue_trigger.queue_name = queue_name
                queue_trigger.min_batch_size = min_batch_size
            else:
                db.session.add(QueueTriggers(id=trigger_id, queue_name=queue_name, min_batch_size=min_batch_size))

        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

# Helper function to handle multiple datetime formats
def parse_datetime(date_str):
    """Try parsing datetime in multiple formats."""
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M"):  # Allow both formats
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{date_str}' does not match expected formats.")

@bp.route('/create', methods=['POST'])
def create_trigger():
    """Create a new trigger and its corresponding sub-table entry."""
    data = request.json
    new_trigger_id = str(uuid.uuid4()).upper()

    try:
        # Create main trigger entry
        new_trigger = Triggers(
            id=new_trigger_id,
            trigger_name=data["trigger_name"],
            process_name=data["process_name"],
            process_path=data["process_path"],
            process_args=data.get("process_args", ""),
            is_git_repo=data.get("is_git_repo", False),
            is_blocking=data.get("is_blocking", False),
            type=data.get("type"),
            process_status="IDLE"
        )
        db.session.add(new_trigger)

        # Create the appropriate sub-table entry
        trigger_type = data.get("type")

        if trigger_type == "SINGLE":
            next_run = parse_datetime(data["single_next_run"])  # Fixed format
            db.session.add(SingleTriggers(id=new_trigger_id, next_run=next_run))

        elif trigger_type == "SCHEDULED":
            cron_expr = data["cron_expr"]
            next_run = datetime.strptime(data["scheduled_next_run"], "%d-%m-%Y %H:%M")  # Fixed format
            db.session.add(ScheduledTriggers(id=new_trigger_id, cron_expr=cron_expr, next_run=next_run))

        elif trigger_type == "QUEUE":
            queue_name = data["queue_name"]
            min_batch_size = data["min_batch_size"]
            db.session.add(QueueTriggers(id=new_trigger_id, queue_name=queue_name, min_batch_size=min_batch_size))

        db.session.commit()
        return jsonify({"success": True, "id": new_trigger_id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/update_status', methods=['POST'])
def update_status():
    """Update the status of a trigger."""
    data = request.json
    trigger_id = data.get("id")
    new_status = data.get("new_status")

    if not trigger_id:
        return jsonify({"success": False, "error": "Missing trigger ID"}), 400

    try:
        db.session.query(Triggers).filter_by(id=trigger_id).update({"process_status": new_status})
        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/delete', methods=['POST'])
def delete_trigger():
    """Delete a trigger and its corresponding entry from related tables."""
    data = request.json
    trigger_id = data.get("id")

    if not trigger_id:
        return jsonify({"success": False, "error": "Missing trigger ID"}), 400

    try:
        # Find the trigger type before deleting
        trigger = db.session.query(Triggers).filter_by(id=trigger_id).first()
        if not trigger:
            return jsonify({"success": False, "error": "Trigger not found"}), 404

        # First, delete from the corresponding sub-table based on type
        if trigger.type == "SINGLE":
            db.session.query(SingleTriggers).filter_by(id=trigger_id).delete()
        elif trigger.type == "SCHEDULED":
            db.session.query(ScheduledTriggers).filter_by(id=trigger_id).delete()
        elif trigger.type == "QUEUE":
            db.session.query(QueueTriggers).filter_by(id=trigger_id).delete()

        # Then, delete from the main Triggers table
        db.session.query(Triggers).filter_by(id=trigger_id).delete()

        # Commit the changes
        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/get_next_run", methods=["POST"])
def get_next_run():
    """Calculate next run time based on a cron expression."""
    try:
        data = request.get_json()
        cron_expr = data.get("cron_expr", "").strip()

        if not cron_expr:
            return jsonify({"error": "Cron expression is required"}), 400

        now = datetime.now()
        cron = CronSim(cron_expr, now)
        next_run = next(cron)  # Fetch the next run time

        return jsonify({"next_run": next_run.strftime("%d-%m-%Y %H:%M")})

    except Exception as e:
        return jsonify({"error": str(e)}), 400
