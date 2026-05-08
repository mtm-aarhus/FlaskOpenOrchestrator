"""Stats page routes — savings calculator, settings persistence via Constants.

Settings are stored in the existing Constants table under the `flaskstats.` prefix:

    flaskstats.hourly_wage_dkk            -> "300"
    flaskstats.savings.queue.<queue_name> -> JSON {"minutes_per_item": 5, "clicks_per_item": 20, "frustration_per_item": 1}
    flaskstats.savings.process.<name>     -> JSON {"minutes_per_run": 10, ...}

That avoids a new schema migration and keeps everything visible in the existing Constants UI.
"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import cast, Date
from app import db
from app.database import Queues, Triggers, Constants, Jobs

bp = Blueprint("stats", __name__, url_prefix="/stats")

PREFIX = "flaskstats."
WAGE_KEY = f"{PREFIX}hourly_wage_dkk"
QUEUE_KEY_PREFIX = f"{PREFIX}savings.queue."
PROCESS_KEY_PREFIX = f"{PREFIX}savings.process."
DEFAULT_HOURLY_WAGE = 300.0  # DKK


@bp.route("/")
def stats():
    return render_template("stats.html", page="Stats")


def _upsert_constant(name: str, value: str) -> None:
    row = db.session.query(Constants).filter_by(name=name).first()
    now = datetime.now()
    if row:
        row.value = value
        row.changed_at = now
    else:
        db.session.add(Constants(name=name, value=value, changed_at=now))


def _load_settings() -> dict:
    """Read flaskstats.* Constants and return as nested dict."""
    rows = (
        db.session.query(Constants)
        .filter(Constants.name.like(f"{PREFIX}%"))
        .all()
    )
    settings = {
        "hourly_wage_dkk": DEFAULT_HOURLY_WAGE,
        "queues": {},
        "processes": {},
    }
    for row in rows:
        if row.name == WAGE_KEY:
            try:
                settings["hourly_wage_dkk"] = float(row.value)
            except (TypeError, ValueError):
                pass
        elif row.name.startswith(QUEUE_KEY_PREFIX):
            qn = row.name[len(QUEUE_KEY_PREFIX):]
            try:
                settings["queues"][qn] = json.loads(row.value or "{}")
            except json.JSONDecodeError:
                pass
        elif row.name.startswith(PROCESS_KEY_PREFIX):
            pn = row.name[len(PROCESS_KEY_PREFIX):]
            try:
                settings["processes"][pn] = json.loads(row.value or "{}")
            except json.JSONDecodeError:
                pass
    return settings


@bp.route("/settings", methods=["GET"])
def get_settings():
    """
    Return:
      - hourly_wage_dkk
      - queues: ONLY items already configured (any non-zero value)
      - processes: same
      - available_queues: every distinct queue_name in DB (for the picker)
      - available_processes: every distinct trigger process_name (for the picker)
    """
    settings = _load_settings()

    available_queues = sorted({
        r[0] for r in db.session.query(Queues.queue_name).distinct().all() if r[0]
    })
    available_processes = sorted({
        r[0] for r in db.session.query(Triggers.process_name).distinct().all() if r[0]
    })

    queue_rows = []
    for qn in sorted(settings["queues"].keys()):
        cfg = settings["queues"][qn]
        queue_rows.append({
            "name": qn,
            "minutes_per_item": cfg.get("minutes_per_item", 0),
            "clicks_per_item": cfg.get("clicks_per_item", 0),
        })

    process_rows = []
    for pn in sorted(settings["processes"].keys()):
        cfg = settings["processes"][pn]
        process_rows.append({
            "name": pn,
            "minutes_per_run": cfg.get("minutes_per_run", 0),
            "clicks_per_run": cfg.get("clicks_per_run", 0),
        })

    return jsonify({
        "hourly_wage_dkk": settings["hourly_wage_dkk"],
        "queues": queue_rows,
        "processes": process_rows,
        "available_queues": available_queues,
        "available_processes": available_processes,
    })


def _delete_constant(name: str) -> None:
    row = db.session.query(Constants).filter_by(name=name).first()
    if row:
        db.session.delete(row)


@bp.route("/settings/wage", methods=["POST"])
def save_wage():
    """Save just the hourly wage."""
    data = request.json or {}
    try:
        wage = float(data.get("hourly_wage_dkk") or 0)
        _upsert_constant(WAGE_KEY, str(wage))
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/settings/item", methods=["POST"])
def save_item():
    """
    Save a single queue/process settings entry.
    Payload: {kind: "queue"|"process", name: str, fields: {...}}
    If all field values are zero, the underlying Constant row is removed.
    """
    data = request.json or {}
    kind = data.get("kind")
    name = (data.get("name") or "").strip()
    fields = data.get("fields") or {}
    if kind not in ("queue", "process") or not name:
        return jsonify({"success": False, "error": "kind and name are required"}), 400
    try:
        cfg = {k: float(v or 0) for k, v in fields.items()}
        prefix = QUEUE_KEY_PREFIX if kind == "queue" else PROCESS_KEY_PREFIX
        key = f"{prefix}{name}"
        if any(cfg.values()):
            _upsert_constant(key, json.dumps(cfg))
        else:
            _delete_constant(key)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/settings/item", methods=["DELETE"])
def delete_item():
    """Remove a single queue/process settings entry. Payload: {kind, name}."""
    data = request.json or {}
    kind = data.get("kind")
    name = (data.get("name") or "").strip()
    if kind not in ("queue", "process") or not name:
        return jsonify({"success": False, "error": "kind and name are required"}), 400
    try:
        prefix = QUEUE_KEY_PREFIX if kind == "queue" else PROCESS_KEY_PREFIX
        _delete_constant(f"{prefix}{name}")
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/settings", methods=["POST"])
def save_settings():
    """Bulk save settings (kept for backwards compat). Per-row saves use the /settings/item endpoint."""
    data = request.json or {}
    try:
        if "hourly_wage_dkk" in data:
            _upsert_constant(WAGE_KEY, str(float(data["hourly_wage_dkk"] or 0)))

        for q in data.get("queues", []):
            name = q.get("name")
            if not name:
                continue
            cfg = {
                "minutes_per_item": float(q.get("minutes_per_item") or 0),
                "clicks_per_item": float(q.get("clicks_per_item") or 0),
            }
            # Don't waste rows on entirely-zero entries.
            if any(cfg.values()):
                _upsert_constant(f"{QUEUE_KEY_PREFIX}{name}", json.dumps(cfg))

        for p in data.get("processes", []):
            name = p.get("name")
            if not name:
                continue
            cfg = {
                "minutes_per_run": float(p.get("minutes_per_run") or 0),
                "clicks_per_run": float(p.get("clicks_per_run") or 0),
            }
            if any(cfg.values()):
                _upsert_constant(f"{PROCESS_KEY_PREFIX}{name}", json.dumps(cfg))

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/summary")
def summary():
    """
    Compute totals + breakdown over `days` window using the saved settings.
    Queue savings = count(DONE queue elements in window) × minutes_per_item.
    Process savings = count(DONE Jobs in window) × minutes_per_run (only non-zero).
    """
    days = request.args.get("days", 30, type=int)
    since = datetime.now() - timedelta(days=days)

    settings = _load_settings()
    wage = settings["hourly_wage_dkk"]

    breakdown = []
    total_minutes = 0.0
    total_clicks = 0.0
    total_items = 0

    # ---- Queue savings ---------------------------------------------------
    # One grouped query for all configured queues instead of one per queue.
    queue_names_with_savings = [
        qn for qn, cfg in settings["queues"].items()
        if cfg.get("minutes_per_item", 0) > 0 or cfg.get("clicks_per_item", 0) > 0
    ]
    queue_counts = {}
    if queue_names_with_savings:
        rows = (
            db.session.query(Queues.queue_name, db.func.count())
            .filter(
                Queues.queue_name.in_(queue_names_with_savings),
                Queues.status == "DONE",
                Queues.end_date >= since,
            )
            .group_by(Queues.queue_name)
            .all()
        )
        queue_counts = {qn: c for qn, c in rows}

    for qn in queue_names_with_savings:
        cfg = settings["queues"][qn]
        count = queue_counts.get(qn, 0)
        mpi = cfg.get("minutes_per_item", 0)
        cpi = cfg.get("clicks_per_item", 0)
        minutes = count * mpi
        clicks = count * cpi
        hours = minutes / 60.0
        breakdown.append({
            "name": qn, "type": "queue", "count": count,
            "minutes_saved": minutes,
            "hours_saved": round(hours, 2),
            "clicks_saved": clicks,
            "dkk_saved": round(hours * wage, 2),
        })
        total_minutes += minutes
        total_clicks += clicks
        total_items += count

    # ---- Process savings (Jobs-based) -----------------------------------
    process_names_with_savings = [
        pn for pn, cfg in settings["processes"].items()
        if cfg.get("minutes_per_run", 0) > 0 or cfg.get("clicks_per_run", 0) > 0
    ]
    process_counts = {}
    if process_names_with_savings and Jobs is not None:
        rows = (
            db.session.query(Jobs.process_name, db.func.count())
            .filter(
                Jobs.process_name.in_(process_names_with_savings),
                Jobs.status == "DONE",
                Jobs.start_time >= since,
            )
            .group_by(Jobs.process_name)
            .all()
        )
        process_counts = {pn: c for pn, c in rows}

    for pn in process_names_with_savings:
        cfg = settings["processes"][pn]
        count = process_counts.get(pn, 0)
        mpr = cfg.get("minutes_per_run", 0)
        cpr = cfg.get("clicks_per_run", 0)
        minutes = count * mpr
        clicks = count * cpr
        hours = minutes / 60.0
        breakdown.append({
            "name": pn, "type": "process", "count": count,
            "minutes_saved": minutes,
            "hours_saved": round(hours, 2),
            "clicks_saved": clicks,
            "dkk_saved": round(hours * wage, 2),
        })
        total_minutes += minutes
        total_clicks += clicks
        total_items += count

    breakdown.sort(key=lambda r: r["minutes_saved"], reverse=True)
    total_hours = total_minutes / 60.0
    return jsonify({
        "days": days,
        "hourly_wage_dkk": wage,
        "totals": {
            "items": total_items,
            "minutes_saved": round(total_minutes, 2),
            "hours_saved": round(total_hours, 2),
            "clicks_saved": round(total_clicks, 2),
            "dkk_saved": round(total_hours * wage, 2),
        },
        "breakdown": breakdown,
    })


@bp.route("/timeseries")
def timeseries():
    """
    Time-series of hours/DKK saved over the selected window.
    Daily buckets when window <= 60 days, weekly otherwise.
    """
    days = request.args.get("days", 90, type=int)
    since = datetime.now() - timedelta(days=days)
    settings = _load_settings()
    wage = settings["hourly_wage_dkk"]
    bucket_weekly = days > 60

    minutes_by_date = {}  # datetime.date -> minutes

    # Queue savings per day.
    if settings["queues"]:
        rows = (
            db.session.query(
                Queues.queue_name,
                cast(Queues.end_date, Date).label("d"),
                db.func.count().label("c"),
            )
            .filter(
                Queues.status == "DONE",
                Queues.end_date >= since,
                Queues.queue_name.in_(list(settings["queues"].keys())),
            )
            .group_by(Queues.queue_name, cast(Queues.end_date, Date))
            .all()
        )
        for qn, date, count in rows:
            mpi = settings["queues"][qn].get("minutes_per_item", 0)
            if mpi <= 0 or date is None:
                continue
            minutes_by_date[date] = minutes_by_date.get(date, 0) + count * mpi

    # Process savings per day (Jobs-based).
    if settings["processes"] and Jobs is not None:
        rows = (
            db.session.query(
                Jobs.process_name,
                cast(Jobs.start_time, Date).label("d"),
                db.func.count().label("c"),
            )
            .filter(
                Jobs.status == "DONE",
                Jobs.start_time >= since,
                Jobs.process_name.in_(list(settings["processes"].keys())),
            )
            .group_by(Jobs.process_name, cast(Jobs.start_time, Date))
            .all()
        )
        for pn, date, count in rows:
            mpr = settings["processes"][pn].get("minutes_per_run", 0)
            if mpr <= 0 or date is None:
                continue
            minutes_by_date[date] = minutes_by_date.get(date, 0) + count * mpr

    # Bucket to weeks when the range is wide.
    series = {}
    for date, minutes in minutes_by_date.items():
        if bucket_weekly:
            # Monday of this week.
            key = date - timedelta(days=date.weekday())
        else:
            key = date
        series[key] = series.get(key, 0) + minutes

    sorted_keys = sorted(series.keys())
    return jsonify({
        "labels": [k.strftime("%Y-%m-%d") for k in sorted_keys],
        "hours_saved": [round(series[k] / 60.0, 2) for k in sorted_keys],
        "dkk_saved":   [round((series[k] / 60.0) * wage, 2) for k in sorted_keys],
        "bucket": "week" if bucket_weekly else "day",
    })
