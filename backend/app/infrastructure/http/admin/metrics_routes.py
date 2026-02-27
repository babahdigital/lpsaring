from http import HTTPStatus

from flask import Blueprint, jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.db.models import ApprovalStatus, User, UserRole
from app.infrastructure.gateways.mikrotik_client import (
    get_firewall_address_list_entries,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_mikrotik_connection,
)
from app.services import settings_service
from app.services.access_policy_service import get_user_access_status, resolve_allowed_binding_type_for_user
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
    users = db_users = db.session.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
        )
        .options(selectinload(User.devices))
    ).all()

    if not users:
        return jsonify({"items": [], "summary": {"users": 0, "mismatches": 0}}), HTTPStatus.OK

    list_names = {
        "active": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active",
        "fup": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup",
        "habis": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis",
        "expired": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired",
        "inactive": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive",
        "blocked": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked",
    }
    items: list[dict] = []

    with get_mikrotik_connection() as api:
        if not api:
            return jsonify({"message": "MikroTik connection unavailable."}), HTTPStatus.SERVICE_UNAVAILABLE

        ok_host, host_map, _host_msg = get_hotspot_host_usage_map(api)
        if not ok_host:
            host_map = {}

        ok_ipb, ip_binding_map, _ipb_msg = get_hotspot_ip_binding_user_map(api)
        if not ok_ipb:
            ip_binding_map = {}

        ip_to_statuses: dict[str, set[str]] = {}
        for status_key, list_name in list_names.items():
            ok_list, entries, _msg = get_firewall_address_list_entries(api, list_name)
            if not ok_list:
                continue
            for entry in entries:
                ip_addr = str(entry.get("address") or "").strip()
                if not ip_addr:
                    continue
                bucket = ip_to_statuses.setdefault(ip_addr, set())
                bucket.add(status_key)

        for user in users:
            app_status = str(get_user_access_status(user) or "inactive")
            expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular")

            for device in user.devices or []:
                mac = str(getattr(device, "mac_address", "") or "").strip().upper()
                if not mac:
                    continue

                ip_addr = str(getattr(device, "ip_address", "") or "").strip()
                if not ip_addr:
                    ip_addr = str(host_map.get(mac, {}).get("address") or "").strip()

                binding_entry = ip_binding_map.get(mac) or {}
                actual_binding_type = str(binding_entry.get("type") or "").strip().lower() or None

                statuses_for_ip = sorted(ip_to_statuses.get(ip_addr, set())) if ip_addr else []

                mismatches: list[str] = []
                if actual_binding_type and actual_binding_type != str(expected_binding_type).lower():
                    mismatches.append("binding_type")

                if ip_addr and statuses_for_ip:
                    canonical_app_status = "active" if app_status == "unlimited" else app_status
                    if canonical_app_status not in statuses_for_ip:
                        mismatches.append("address_list")

                if len(statuses_for_ip) > 1:
                    mismatches.append("address_list_multi_status")

                if mismatches:
                    items.append(
                        {
                            "user_id": str(user.id),
                            "phone_number": user.phone_number,
                            "mac": mac,
                            "ip": ip_addr or None,
                            "app_status": app_status,
                            "expected_binding_type": expected_binding_type,
                            "actual_binding_type": actual_binding_type,
                            "address_list_statuses": statuses_for_ip,
                            "mismatches": sorted(set(mismatches)),
                        }
                    )

    return jsonify(
        {
            "items": items,
            "summary": {
                "users": len(db_users),
                "mismatches": len(items),
            },
        }
    ), HTTPStatus.OK
