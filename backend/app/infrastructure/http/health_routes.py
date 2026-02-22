from http import HTTPStatus

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text

from app.extensions import db
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection

health_bp = Blueprint("health", __name__, url_prefix="/api/health")


@health_bp.route("", methods=["GET"])
@health_bp.route("/", methods=["GET"])
def health_check():
    checks = {
        "database": False,
        "redis": False,
        "mikrotik": False,
    }

    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        redis_client = getattr(current_app, "redis_client_otp", None)
        if redis_client is not None:
            redis_client.ping()
            checks["redis"] = True
    except Exception:
        checks["redis"] = False

    try:
        with get_mikrotik_connection() as api:
            if api is not None:
                try:
                    api.get_resource("/system/identity").get()
                    checks["mikrotik"] = True
                except Exception:
                    checks["mikrotik"] = False
    except Exception:
        checks["mikrotik"] = False

    overall_ok = all(checks.values())
    status = "ok" if overall_ok else "degraded"
    return jsonify({"status": status, "checks": checks}), HTTPStatus.OK
