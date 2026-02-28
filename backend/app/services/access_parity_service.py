from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserRole
from app.infrastructure.gateways.mikrotik_client import (
    get_firewall_address_list_entries,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_mikrotik_connection,
)
from app.services import settings_service
from app.services.access_policy_service import get_user_access_status, resolve_allowed_binding_type_for_user


def _build_action_plan(
    *,
    user_id: str,
    phone_number: Optional[str],
    mac: str,
    ip_address: Optional[str],
    expected_binding_type: str,
    expected_status: str,
    statuses_for_ip: list[str],
    mismatches: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    if "binding_type" in mismatches:
        actions.append(
            {
                "action": "upsert_ip_binding_expected_type",
                "user_id": user_id,
                "phone_number": phone_number,
                "mac": mac,
                "expected_binding_type": expected_binding_type,
                "priority": "high",
            }
        )

    if "address_list" in mismatches:
        actions.append(
            {
                "action": "sync_address_list_for_single_user",
                "user_id": user_id,
                "phone_number": phone_number,
                "ip": ip_address,
                "expected_status": expected_status,
                "priority": "high" if ip_address else "medium",
            }
        )

    if "address_list_multi_status" in mismatches:
        extra_statuses = [status for status in statuses_for_ip if status != expected_status]
        actions.append(
            {
                "action": "cleanup_extra_address_lists_for_ip",
                "user_id": user_id,
                "phone_number": phone_number,
                "ip": ip_address,
                "keep_status": expected_status,
                "remove_statuses": extra_statuses,
                "priority": "high",
            }
        )

    if not ip_address:
        actions.append(
            {
                "action": "resolve_ip_from_host_or_binding",
                "user_id": user_id,
                "phone_number": phone_number,
                "mac": mac,
                "priority": "medium",
            }
        )

    return actions


def collect_access_parity_report(*, max_items: int = 500) -> dict[str, Any]:
    users = db.session.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
        )
        .options(selectinload(User.devices))
    ).all()

    if not users:
        return {
            "ok": True,
            "items": [],
            "summary": {
                "users": 0,
                "mismatches": 0,
                "mismatch_types": {
                    "binding_type": 0,
                    "address_list": 0,
                    "address_list_multi_status": 0,
                },
            },
        }

    list_names = {
        "active": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active",
        "fup": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup",
        "habis": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis",
        "expired": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired",
        "inactive": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive",
        "blocked": settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked",
    }

    with get_mikrotik_connection() as api:
        if not api:
            return {
                "ok": False,
                "reason": "mikrotik_unavailable",
                "items": [],
                "summary": {
                    "users": len(users),
                    "mismatches": 0,
                    "mismatch_types": {
                        "binding_type": 0,
                        "address_list": 0,
                        "address_list_multi_status": 0,
                    },
                },
            }

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

        items: list[dict[str, Any]] = []
        mismatch_types = {
            "binding_type": 0,
            "address_list": 0,
            "address_list_multi_status": 0,
        }

        for user in users:
            app_status = str(get_user_access_status(user) or "inactive")
            expected_status = "active" if app_status == "unlimited" else app_status
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

                if ip_addr and statuses_for_ip and expected_status not in statuses_for_ip:
                    mismatches.append("address_list")

                if len(statuses_for_ip) > 1:
                    mismatches.append("address_list_multi_status")

                if not mismatches:
                    continue

                for mismatch_key in set(mismatches):
                    mismatch_types[mismatch_key] = mismatch_types.get(mismatch_key, 0) + 1

                item = {
                    "user_id": str(user.id),
                    "phone_number": user.phone_number,
                    "mac": mac,
                    "ip": ip_addr or None,
                    "app_status": app_status,
                    "expected_status": expected_status,
                    "expected_binding_type": expected_binding_type,
                    "actual_binding_type": actual_binding_type,
                    "address_list_statuses": statuses_for_ip,
                    "mismatches": sorted(set(mismatches)),
                }
                item["action_plan"] = _build_action_plan(
                    user_id=item["user_id"],
                    phone_number=item.get("phone_number"),
                    mac=mac,
                    ip_address=item.get("ip"),
                    expected_binding_type=str(expected_binding_type).lower(),
                    expected_status=expected_status,
                    statuses_for_ip=statuses_for_ip,
                    mismatches=item["mismatches"],
                )
                items.append(item)

                if len(items) >= max_items:
                    break

            if len(items) >= max_items:
                break

        return {
            "ok": True,
            "items": items,
            "summary": {
                "users": len(users),
                "mismatches": len(items),
                "mismatch_types": mismatch_types,
            },
        }
