import json
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
    upsert_dhcp_static_lease,
    upsert_ip_binding,
)
from app.services import settings_service
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.access_parity_service import collect_access_parity_report
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings
from app.utils.metrics_utils import get_metrics

metrics_bp = Blueprint("admin_metrics", __name__)


def _read_cached_policy_parity_mismatch_count() -> int:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return 0

    try:
        raw = redis_client.get("policy_parity:last_report")
        if not raw:
            return 0

        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")

        payload = json.loads(str(raw))
        if not isinstance(payload, dict):
            return 0

        summary = payload.get("summary") or {}
        if not isinstance(summary, dict):
            return 0

        mismatch_count = int(summary.get("mismatches", 0) or 0)

        # Newer payloads already store actionable parity mismatches in `summary.mismatches`.
        if "mismatches_total" in summary:
            return max(0, mismatch_count)

        # Backward compatibility for older cached payloads where `mismatches` included
        # onboarding gaps (`no_authorized_device`) that should not degrade parity health.
        mismatch_types = summary.get("mismatch_types") or {}
        if isinstance(mismatch_types, dict):
            no_authorized_device_count = int(mismatch_types.get("no_authorized_device", 0) or 0)
            return max(0, mismatch_count - no_authorized_device_count)

        return max(0, mismatch_count)
    except Exception:
        return 0


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
    policy_parity_latest_mismatches = _read_cached_policy_parity_mismatch_count()
    metrics["policy.parity.latest_mismatches"] = policy_parity_latest_mismatches

    reliability_signals = {
        "payment_idempotency_degraded": int(metrics.get("payment.idempotency.redis_unavailable", 0)) > 0,
        "hotspot_sync_lock_degraded": int(metrics.get("hotspot.sync.lock.degraded", 0)) > 0,
        "policy_parity_degraded": (
            policy_parity_latest_mismatches > 0
            or int(metrics.get("policy.mismatch.auto_debt_blocked_ip_binding", 0)) > 0
        ),
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
    dhcp_synced = False
    warnings: list[str] = []

    authorized_macs = sorted(
        {
            str(getattr(device, "mac_address", "") or "").strip().upper()
            for device in (user.devices or [])
            if bool(getattr(device, "is_authorized", False))
            and str(getattr(device, "mac_address", "") or "").strip()
        }
    )
    auto_selected_mac = False
    if not mac:
        if len(authorized_macs) == 1:
            mac = authorized_macs[0]
            auto_selected_mac = True
        elif len(authorized_macs) > 1:
            return (
                jsonify({"message": "User memiliki lebih dari satu MAC authorized. Sertakan MAC spesifik untuk parity fix."}),
                HTTPStatus.BAD_REQUEST,
            )
        elif not ip_address:
            return (
                jsonify({"message": "User belum punya device authorized atau IP aktif untuk parity fix otomatis."}),
                HTTPStatus.CONFLICT,
            )

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

            dhcp_enabled = settings_service.get_setting("MIKROTIK_DHCP_STATIC_LEASE_ENABLED", "False") == "True"
            dhcp_server_name = (settings_service.get_setting("MIKROTIK_DHCP_LEASE_SERVER_NAME", "") or "").strip() or None
            if dhcp_enabled and resolved_ip and dhcp_server_name:
                ok_dhcp, dhcp_msg = upsert_dhcp_static_lease(
                    api_connection=api,
                    mac_address=mac,
                    address=resolved_ip,
                    server=dhcp_server_name,
                    comment=(
                        f"lpsaring|static-dhcp|user={username_08}|uid={user.id}|role={user.role.value}"
                        f"|source=admin-parity-fix|date={date_str}|time={time_str}"
                    ),
                )
                if ok_dhcp:
                    dhcp_synced = True
                else:
                    warning_text = f"Gagal sync DHCP static lease: {dhcp_msg}"
                    warnings.append(warning_text)
                    current_app.logger.warning(
                        "Parity fix warning DHCP static lease user=%s mac=%s ip=%s: %s",
                        user.id,
                        mac,
                        resolved_ip,
                        dhcp_msg,
                    )
            elif dhcp_enabled and not dhcp_server_name:
                warnings.append("MIKROTIK_DHCP_LEASE_SERVER_NAME kosong; DHCP static lease tidak dapat di-sync.")

        address_synced = bool(sync_address_list_for_single_user(user, client_ip=resolved_ip))

    return jsonify(
        {
            "message": "Parity fix dieksekusi.",
            "user_id": str(user.id),
            "mac": mac or None,
            "resolved_ip": resolved_ip,
            "expected_binding_type": expected_binding_type,
            "binding_updated": bool(binding_updated),
            "dhcp_synced": bool(dhcp_synced),
            "address_list_synced": bool(address_synced),
            "auto_selected_mac": bool(auto_selected_mac),
            "warnings": warnings,
        }
    ), HTTPStatus.OK
