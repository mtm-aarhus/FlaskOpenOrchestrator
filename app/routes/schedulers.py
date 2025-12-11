from flask import Blueprint, render_template, request, jsonify
from app import db
from app.database import Schedulers
from sqlalchemy.sql import column
from datetime import datetime, timedelta

bp = Blueprint("schedulers", __name__, url_prefix="/schedulers")

@bp.route("/")
def schedulers():
    return render_template("tables/schedulers.html", page="Schedulers")

@bp.route("/data")
def get_schedulers_data():
    """Server-side pagination, sorting, and filtering for schedulers."""
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 25, type=int)
    search = request.args.get("search", "", type=str)
    sort = request.args.get("sort", "last_update")
    order = request.args.get("order", "desc")

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()
    base_query = db.session.query(Schedulers)

    if search:
        base_query = base_query.filter(
            db.or_(
                Schedulers.machine_name.ilike(f"%{search}%"),
                Schedulers.latest_trigger.ilike(f"%{search}%"),
            )
        )

    total_count = base_query.with_entities(db.func.count()).scalar()

    schedulers = base_query.order_by(order_by).offset(offset).limit(limit).all()


    now = datetime.now()
    rows = []
    for s in schedulers:
        delta = now - s.last_update if s.last_update else timedelta.max
        is_online = delta < timedelta(minutes=5)
        print(type(s.last_update), s.last_update)
        rows.append({
            "machine_name": s.machine_name,
            "status": "online" if is_online else "offline",
            "last_update": s.last_update.strftime("%d-%m-%Y %H:%M:%S") if s.last_update else "N/A",
            "latest_trigger": s.latest_trigger or "N/A",
            "latest_trigger_time": (
                s.latest_trigger_time.strftime("%d-%m-%Y %H:%M:%S") if s.latest_trigger_time else "N/A"
            ),
        })

    return jsonify({"total": total_count, "rows": rows})
