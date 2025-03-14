from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
from app import db
from app.database import Constants
from sqlalchemy.sql import column

bp = Blueprint("constants", __name__, url_prefix="/constants")


@bp.route("/")
def constants():
    """Render constants management page."""
    return render_template("tables/constants.html", page="Constants")

@bp.route("/data")
def get_constants():
    """Return all constants with server-side pagination, sorting, and search."""

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 10, type=int)
    search = request.args.get("search", "", type=str)
    sort = request.args.get("sort", "changed_at")
    order = request.args.get("order", "desc")

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()

    query = db.session.query(Constants)

    if search:
        query = query.filter(
            (Constants.name.ilike(f"%{search}%")) |
            (Constants.value.ilike(f"%{search}%"))
        )

    total_count = query.count()
    results = query.order_by(order_by).offset(offset).limit(limit).all()

    formatted_rows = []
    for const in results:
        changed_at = const.changed_at
        if isinstance(changed_at, str):
            try:
                changed_at = datetime.strptime(changed_at, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                changed_at = datetime.strptime(changed_at, "%Y-%m-%d %H:%M:%S")

        formatted_rows.append({
            "name": const.name,
            "value": const.value,
            "changed_at": changed_at.strftime("%d-%m-%Y %H:%M") if changed_at else "N/A",
            "actions": f"""
                <button class="btn btn-sm btn-primary" onclick="editConstant('{const.name}', '{const.value}')">
                    <i class="bi bi-pencil-square"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteConstant('{const.name}')">
                    <i class="bi bi-trash"></i> Delete
                </button>
            """
        })

    return jsonify({"total": total_count, "rows": formatted_rows})


@bp.route("/create", methods=["POST"])
def create_constant():
    """Create a new constant."""
    data = request.json
    name = data.get("name")
    value = data.get("value")

    if not name or not value:
        return jsonify({"success": False, "error": "All fields are required"}), 400

    existing = db.session.query(Constants).filter_by(name=name).first()
    if existing:
        return jsonify({"success": False, "error": "Constant with this name already exists"}), 409

    new_constant = Constants(
        name=name,
        value=value,
        changed_at=datetime.now()
    )
    db.session.add(new_constant)
    db.session.commit()
    return jsonify({"success": True})

@bp.route("/update", methods=["POST"])
def update_constant():
    """Update an existing constant."""
    data = request.json
    original_name = data.get("id")
    name = data.get("name")
    value = data.get("value")

    constant = db.session.query(Constants).filter_by(name=original_name).first()
    
    if not constant:
        return jsonify({"success": False, "error": "Constant not found"}), 404

    constant.value = value
    constant.name = name
    constant.changed_at = datetime.now()

    db.session.commit()
    return jsonify({"success": True})

@bp.route("/delete", methods=["POST"])
def delete_constant():
    """Delete a constant."""
    data = request.json
    name = data.get("name")

    constant = db.session.query(Constants).get(name)
    if not constant:
        return jsonify({"success": False, "error": "Constant not found"}), 404

    db.session.delete(constant)
    db.session.commit()
    return jsonify({"success": True})
