from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.db.models import ApprovalStatus, User, UserRole
from app.infrastructure.gateways.mikrotik_client import (
    get_ip_by_mac,
    get_mikrotik_connection,
    upsert_ip_binding,
)
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.access_parity_service import collect_access_parity_report
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings
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
        "policy.mismatch.auto_debt_blocked_ip_binding",
        "policy.mismatch.auto_debt_blocked_ip_binding.devices",
        "admin.login.success",
        "admin.login.failed",
    ]
    metrics = get_metrics(metric_keys)
    reliability_signals = {
        "payment_idempotency_degraded": int(metrics.get("payment.idempotency.redis_unavailable", 0)) > 0,
        "hotspot_sync_lock_degraded": int(metrics.get("hotspot.sync.lock.degraded", 0)) > 0,
        "policy_parity_degraded": int(metrics.get("policy.mismatch.auto_debt_blocked_ip_binding", 0)) > 0,
    }
    return jsonify({"metrics": metrics, "reliability_signals": reliability_signals}), HTTPStatus.OK


@metrics_bp.route("/metrics/access-parity", methods=["GET"])
@admin_required
def get_access_parity(current_admin):
    report = collect_access_parity_report()
    if not report.get("ok", False) and report.get("reason") == "mikrotik_unavailable":
        return jsonify({"message": "MikroTik connection unavailable."}), HTTPStatus.SERVICE_UNAVAILABLE

    return jsonify(
        {
            "items": report.get("items", []),
            "summary": report.get("summary", {"users": 0, "mismatches": 0}),
        }
    ), HTTPStatus.OK


@metrics_bp.route("/metrics/access-parity/fix", methods=["POST"])
@admin_required
def fix_access_parity(current_admin):
    payload = request.get_json(silent=True) or {}

    user_id = str(payload.get("user_id") or "").strip()
    mac = str(payload.get("mac") or "").strip().upper()
    ip_address = str(payload.get("ip") or "").strip() or None

    if not user_id:
        return jsonify({"message": "user_id wajib diisi."}), HTTPStatus.BAD_REQUEST

    user = db.session.scalars(
        select(User)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
        )
        .options(selectinload(User.devices))
    ).one_or_none()

    if not user:
        return jsonify({"message": "User tidak ditemukan atau tidak eligible untuk parity fix."}), HTTPStatus.NOT_FOUND

    expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular").lower()
    address_synced = False
    binding_updated = False

    now_utc = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now_utc)
    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "") or str(user.phone_number or "")

    with get_mikrotik_connection() as api:
        if not api:
            return jsonify({"message": "MikroTik connection unavailable."}), HTTPStatus.SERVICE_UNAVAILABLE

        resolved_ip = ip_address
        if mac:
            if not resolved_ip:
                ok_ip, fetched_ip, _ip_msg = get_ip_by_mac(api, mac)
                if ok_ip and fetched_ip:
                    resolved_ip = str(fetched_ip).strip()

            ok_binding, binding_msg = upsert_ip_binding(
                api_connection=api,
                mac_address=mac,
                address=resolved_ip,
                server=getattr(user, "mikrotik_server_name", None),
                binding_type=expected_binding_type,
                comment=(
                    f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                    f"|source=admin-parity-fix|date={date_str}|time={time_str}"
                ),
            )
            if not ok_binding:
                current_app.logger.warning(
                    "Parity fix gagal upsert ip-binding user=%s mac=%s: %s",
                    user.id,
                    mac,
                    binding_msg,
                )
                return jsonify({"message": f"Gagal update ip-binding: {binding_msg}"}), HTTPStatus.BAD_GATEWAY
            binding_updated = True

        address_synced = bool(sync_address_list_for_single_user(user, client_ip=resolved_ip))

    return jsonify(
        {
            "message": "Parity fix dieksekusi.",
            "user_id": str(user.id),
            "mac": mac or None,
            "resolved_ip": resolved_ip,
            "expected_binding_type": expected_binding_type,
            "binding_updated": bool(binding_updated),
            "address_list_synced": bool(address_synced),
        }
    ), HTTPStatus.OK
