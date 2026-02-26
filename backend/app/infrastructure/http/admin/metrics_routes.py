from http import HTTPStatus

from flask import Blueprint, jsonify

from app.infrastructure.http.decorators import admin_required
from app.utils.metrics_utils import get_metrics

metrics_bp = Blueprint("admin_metrics", __name__)


@metrics_bp.route("/metrics", methods=["GET"])
@admin_required
def get_admin_metrics(current_admin):
    metric_keys = [
        "otp.request.success",
        "otp.request.failed",
        "otp.verify.success",
        "otp.verify.failed",
        "payment.success",
        "payment.failed",
        "payment.webhook.duplicate",
        "payment.idempotency.redis_unavailable",
        "hotspot.sync.lock.degraded",
        "admin.login.success",
        "admin.login.failed",
    ]
    metrics = get_metrics(metric_keys)
    reliability_signals = {
        "payment_idempotency_degraded": int(metrics.get("payment.idempotency.redis_unavailable", 0)) > 0,
        "hotspot_sync_lock_degraded": int(metrics.get("hotspot.sync.lock.degraded", 0)) > 0,
    }
    return jsonify({"metrics": metrics, "reliability_signals": reliability_signals}), HTTPStatus.OK
