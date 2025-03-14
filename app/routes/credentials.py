from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
import os
from cryptography.fernet import Fernet
from sqlalchemy import column
from app import db
from app.database import Credentials 

bp = Blueprint("credentials", __name__, url_prefix="/credentials")

# Load encryption key from environment variable
ENCRYPTION_KEY = os.getenv("OpenOrchestratorKey")
if not ENCRYPTION_KEY:
    raise ValueError("Missing environment variable: OpenOrchestratorKey")

cipher = Fernet(ENCRYPTION_KEY)

def encrypt_string(plain_text):
    """Encrypt plain text."""
    return cipher.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text):
    """Decrypt encrypted text."""
    return cipher.decrypt(encrypted_text.encode()).decode()

@bp.route("/")
def credentials():
    """Render credentials management page."""
    return render_template("tables/credentials.html", page="Credentials")

@bp.route("/data")
def get_credentials():
    """Return credentials with pagination, sorting, search, and filtering."""

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 10, type=int)
    search = request.args.get("search", "", type=str)
    sort = request.args.get("sort", "changed_at")
    order = request.args.get("order", "desc")

    order_by = column(sort).desc() if order.lower() == "desc" else column(sort).asc()

    query = db.session.query(Credentials)

    if search:
        query = query.filter(
            (Credentials.name.ilike(f"%{search}%")) | 
            (Credentials.username.ilike(f"%{search}%"))
        )

    total_count = query.count()
    results = query.order_by(order_by).offset(offset).limit(limit).all()

    formatted_rows = []
    for cred in results:
        changed_at = cred.changed_at
        if isinstance(changed_at, str):
            try:
                changed_at = datetime.strptime(changed_at, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                changed_at = datetime.strptime(changed_at, "%Y-%m-%d %H:%M:%S")

        formatted_rows.append({
            "name": cred.name,
            "username": cred.username,
            "changed_at": changed_at.strftime("%d-%m-%Y %H:%M") if changed_at else "N/A",
            "actions": f"""
                <button class="btn btn-sm btn-primary" onclick="editCredential('{cred.name}', '{cred.username}')">
                    <i class="bi bi-pencil-square"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteCredential('{cred.name}')">
                    <i class="bi bi-trash"></i> Delete
                </button>
            """
        })

    return jsonify({"total": total_count, "rows": formatted_rows})



@bp.route("/create", methods=["POST"])
def create_credential():
    """Create a new credential."""
    data = request.json
    name = data.get("name")
    username = data.get("username")
    password = data.get("password")

    if not name or not username or not password:
        return jsonify({"success": False, "error": "All fields are required"}), 400

    existing = db.session.query(Credentials).filter_by(name=name).first()
    if existing:
        return jsonify({"success": False, "error": "Credential with this name already exists"}), 409

    encrypted_password = encrypt_string(password)

    new_credential = Credentials(
        name=name,
        username=username,
        password=encrypted_password,
        changed_at=datetime.now()
    )
    db.session.add(new_credential)
    db.session.commit()
    return jsonify({"success": True})


@bp.route("/update", methods=["POST"])
def update_credential():
    """Update an existing credential (with encrypted password)."""
    data = request.json
    original_name = data.get("id")
    new_name = data.get("name")
    username = data.get("username")
    password = data.get("password")
    change_password = data.get("change_password", False)

    # Find the credential by its original name
    credential = db.session.query(Credentials).filter_by(name=original_name).first()

    if not credential:
        return jsonify({"success": False, "error": "Credential not found"}), 404

    credential.name = new_name
    credential.username = username

    if change_password:
        credential.password = encrypt_string(password)  # Encrypt new password

    credential.changed_at = datetime.now()

    db.session.commit()
    return jsonify({"success": True})

@bp.route("/delete", methods=["POST"])
def delete_credential():
    """Delete a credential."""
    data = request.json
    name = data.get("name")

    credential = db.session.query(Credentials).filter_by(name=name).first()
    if not credential:
        return jsonify({"success": False, "error": "Credential not found"}), 404

    db.session.delete(credential)
    db.session.commit()
    return jsonify({"success": True})

@bp.route("/decrypt", methods=["POST"])
def decrypt_password():
    """Decrypts and returns a password with verification of the decryption key."""
    data = request.json
    name = data.get("name")
    user_key = data.get("key") 

    credential = db.session.query(Credentials).filter_by(name=name).first()
    if not credential:
        return jsonify({"success": False, "error": "Credential not found"}), 404

    if user_key != os.getenv("OpenOrchestratorKey"):
        return jsonify({"success": False, "error": "Invalid decryption key"}), 403  # Forbidden

    try:
        decrypted_password = decrypt_string(credential.password)
        return jsonify({"success": True, "password": decrypted_password})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
