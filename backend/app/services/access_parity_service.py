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

_MISMATCH_KEYS = (
    "binding_type",
    "missing_ip_binding",
    "address_list",
    "address_list_multi_status",
    "no_authorized_device",
    "no_resolvable_ip",
    "dhcp_lease_missing",
)

_NON_PARITY_MISMATCH_KEYS = {
    "no_authorized_device",
    "dhcp_lease_missing",
}


def _empty_mismatch_types() -> dict[str, int]:
    return {key: 0 for key in _MISMATCH_KEYS}


def _is_parity_relevant_item(mismatches: list[str]) -> bool:
    mismatch_set = {str(key or "").strip() for key in mismatches if str(key or "").strip()}
    return any(key not in _NON_PARITY_MISMATCH_KEYS for key in mismatch_set)


def _normalize_ip(value: Any) -> Optional[str]:
    ip_text = str(value or "").strip()
    if not ip_text or ip_text in {"0.0.0.0", "0.0.0.0/0"}:
        return None
    return ip_text


def _should_skip_dhcp_mismatch(*, expected_binding_type: str) -> bool:
    # Hard-block policy intentionally does not require DHCP lease parity.
    return str(expected_binding_type or "").strip().lower() == "blocked"


def _has_live_host_ip_signal(*, host_ip: Optional[str], resolved_ip: Optional[str]) -> bool:
    """Return True when hotspot host table already confirms active IP signal for this MAC.

    In that state, missing DHCP lease can be expected on some router profiles/networks
    and should not be treated as parity drift.
    """
    normalized_host_ip = _normalize_ip(host_ip)
    if not normalized_host_ip:
        return False

    normalized_resolved_ip = _normalize_ip(resolved_ip)
    if not normalized_resolved_ip:
        return True

    return normalized_host_ip == normalized_resolved_ip


def _is_auto_fixable(*, mismatches: list[str], mac: Optional[str], ip_address: Optional[str]) -> bool:
    mismatch_set = set(mismatches)

    if "no_authorized_device" in mismatch_set:
        return False

    # Tanpa sinyal IP aktif, auto-fix biasanya tidak deterministik dan berisiko membuat state semu.
    if "no_resolvable_ip" in mismatch_set:
        return False

    needs_mac = {"binding_type", "missing_ip_binding", "dhcp_lease_missing"}
    if mismatch_set.intersection(needs_mac) and not mac:
        return False

    if "address_list" in mismatch_set and not ip_address and not mac:
        return False

    return True


def _build_action_plan(
    *,
    user_id: str,
    phone_number: Optional[str],
    mac: Optional[str],
    ip_address: Optional[str],
    expected_binding_type: str,
    expected_status: str,
    statuses_for_ip: list[str],
    mismatches: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    mismatch_set = set(mismatches)

    if "no_authorized_device" in mismatch_set:
        actions.append(
            {
                "action": "authorize_device_from_admin",
                "mode": "manual",
                "user_id": user_id,
                "phone_number": phone_number,
                "priority": "high",
            }
        )

    if "missing_ip_binding" in mismatch_set and mac:
        actions.append(
            {
                "action": "upsert_ip_binding_expected_type",
                "mode": "auto",
                "user_id": user_id,
                "phone_number": phone_number,
                "mac": mac,
                "expected_binding_type": expected_binding_type,
                "priority": "high",
            }
        )

    if "binding_type" in mismatch_set and mac:
        actions.append(
            {
                "action": "upsert_ip_binding_expected_type",
                "mode": "auto",
                "user_id": user_id,
                "phone_number": phone_number,
                "mac": mac,
                "expected_binding_type": expected_binding_type,
                "priority": "high",
            }
        )

    if "dhcp_lease_missing" in mismatch_set and mac:
        actions.append(
            {
                "action": "upsert_dhcp_static_lease",
                "mode": "auto",
                "user_id": user_id,
                "phone_number": phone_number,
                "mac": mac,
                "ip": ip_address,
                "priority": "high" if ip_address else "medium",
            }
        )

    if "address_list" in mismatch_set:
        actions.append(
            {
                "action": "sync_address_list_for_single_user",
                "mode": "auto",
                "user_id": user_id,
                "phone_number": phone_number,
                "ip": ip_address,
                "expected_status": expected_status,
                "priority": "high" if ip_address else "medium",
            }
        )

    if "address_list_multi_status" in mismatch_set:
        extra_statuses = [status for status in statuses_for_ip if status != expected_status]
        actions.append(
            {
                "action": "cleanup_extra_address_lists_for_ip",
                "mode": "auto",
                "user_id": user_id,
                "phone_number": phone_number,
                "ip": ip_address,
                "keep_status": expected_status,
                "remove_statuses": extra_statuses,
                "priority": "high",
            }
        )

    if "no_resolvable_ip" in mismatch_set or (not ip_address and mac):
        actions.append(
            {
                "action": "resolve_ip_from_host_or_binding",
                "mode": "manual",
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
                "mismatches_total": 0,
                "non_parity_mismatches": 0,
                "no_authorized_device_count": 0,
                "auto_fixable_items": 0,
                "mismatch_types": _empty_mismatch_types(),
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
                    "mismatches_total": 0,
                    "non_parity_mismatches": 0,
                    "no_authorized_device_count": 0,
                    "auto_fixable_items": 0,
                    "mismatch_types": _empty_mismatch_types(),
                },
            }

        ok_host, host_map, _host_msg = get_hotspot_host_usage_map(api)
        if not ok_host:
            host_map = {}

        ok_ipb, ip_binding_map, _ipb_msg = get_hotspot_ip_binding_user_map(api)
        if not ok_ipb:
            ip_binding_map = {}

        dhcp_macs: set[str] = set()
        dhcp_ips_by_mac: dict[str, set[str]] = {}
        try:
            dhcp_rows = api.get_resource("/ip/dhcp-server/lease").get() or []
        except Exception:
            dhcp_rows = []

        for row in dhcp_rows:
            mac = str(row.get("mac-address") or "").strip().upper()
            if not mac:
                continue

            status = str(row.get("status") or "").strip().lower()
            if status == "waiting":
                continue

            dhcp_macs.add(mac)
            ip_text = _normalize_ip(row.get("address"))
            if ip_text:
                dhcp_ips_by_mac.setdefault(mac, set()).add(ip_text)

        ip_to_statuses: dict[str, set[str]] = {}
        for status_key, list_name in list_names.items():
            ok_list, entries, _msg = get_firewall_address_list_entries(api, list_name)
            if not ok_list:
                continue
            for entry in entries:
                ip_addr = _normalize_ip(entry.get("address"))
                if not ip_addr:
                    continue
                bucket = ip_to_statuses.setdefault(ip_addr, set())
                bucket.add(status_key)

        items: list[dict[str, Any]] = []
        mismatch_types = _empty_mismatch_types()
        auto_fixable_items = 0
        parity_mismatch_items = 0

        for user in users:
            app_status = str(get_user_access_status(user) or "inactive")
            expected_status = "active" if app_status == "unlimited" else app_status
            expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular").strip().lower()
            expected_binding_type = expected_binding_type or "regular"

            authorized_devices = [
                device
                for device in (user.devices or [])
                if bool(getattr(device, "is_authorized", False))
                and str(getattr(device, "mac_address", "") or "").strip()
            ]

            if not authorized_devices:
                mismatch_list = ["no_authorized_device"]
                item = {
                    "user_id": str(user.id),
                    "phone_number": str(user.phone_number or ""),
                    "mac": None,
                    "ip": None,
                    "app_status": app_status,
                    "expected_status": expected_status,
                    "expected_binding_type": expected_binding_type,
                    "actual_binding_type": None,
                    "address_list_statuses": [],
                    "mismatches": mismatch_list,
                }
                item["auto_fixable"] = False
                item["parity_relevant"] = _is_parity_relevant_item(mismatch_list)
                item["action_plan"] = _build_action_plan(
                    user_id=item["user_id"],
                    phone_number=item.get("phone_number"),
                    mac=item.get("mac"),
                    ip_address=item.get("ip"),
                    expected_binding_type=expected_binding_type,
                    expected_status=expected_status,
                    statuses_for_ip=[],
                    mismatches=mismatch_list,
                )

                mismatch_types["no_authorized_device"] += 1
                if item["parity_relevant"]:
                    parity_mismatch_items += 1
                items.append(item)
                if len(items) >= max_items:
                    break
                continue

            for device in authorized_devices:
                mac = str(getattr(device, "mac_address", "") or "").strip().upper()
                if not mac:
                    continue

                ip_addr = _normalize_ip(getattr(device, "ip_address", None))
                if not ip_addr:
                    ip_addr = _normalize_ip((host_map.get(mac) or {}).get("address"))
                if not ip_addr:
                    ip_addr = _normalize_ip((ip_binding_map.get(mac) or {}).get("address"))

                binding_entry = ip_binding_map.get(mac) or {}
                has_binding = bool(binding_entry)
                actual_binding_type = str(binding_entry.get("type") or "").strip().lower() or None
                statuses_for_ip = sorted(ip_to_statuses.get(ip_addr, set())) if ip_addr else []

                mismatch_list: list[str] = []
                if not has_binding:
                    mismatch_list.append("missing_ip_binding")

                if actual_binding_type and actual_binding_type != expected_binding_type:
                    mismatch_list.append("binding_type")

                if not ip_addr:
                    mismatch_list.append("no_resolvable_ip")
                else:
                    if not statuses_for_ip or expected_status not in statuses_for_ip:
                        mismatch_list.append("address_list")
                    if len(statuses_for_ip) > 1:
                        mismatch_list.append("address_list_multi_status")

                if not _should_skip_dhcp_mismatch(expected_binding_type=expected_binding_type):
                    host_ip = _normalize_ip((host_map.get(mac) or {}).get("address"))
                    if not _has_live_host_ip_signal(host_ip=host_ip, resolved_ip=ip_addr):
                        if mac not in dhcp_macs:
                            mismatch_list.append("dhcp_lease_missing")
                        elif ip_addr and ip_addr not in dhcp_ips_by_mac.get(mac, set()):
                            mismatch_list.append("dhcp_lease_missing")

                mismatch_list = sorted(set(mismatch_list))
                if not mismatch_list:
                    continue

                for mismatch_key in mismatch_list:
                    mismatch_types[mismatch_key] = mismatch_types.get(mismatch_key, 0) + 1

                item = {
                    "user_id": str(user.id),
                    "phone_number": str(user.phone_number or ""),
                    "mac": mac,
                    "ip": ip_addr,
                    "app_status": app_status,
                    "expected_status": expected_status,
                    "expected_binding_type": expected_binding_type,
                    "actual_binding_type": actual_binding_type,
                    "address_list_statuses": statuses_for_ip,
                    "mismatches": mismatch_list,
                }
                item["parity_relevant"] = _is_parity_relevant_item(mismatch_list)
                item["auto_fixable"] = _is_auto_fixable(
                    mismatches=mismatch_list,
                    mac=item.get("mac"),
                    ip_address=item.get("ip"),
                )
                item["action_plan"] = _build_action_plan(
                    user_id=item["user_id"],
                    phone_number=item.get("phone_number"),
                    mac=item.get("mac"),
                    ip_address=item.get("ip"),
                    expected_binding_type=expected_binding_type,
                    expected_status=expected_status,
                    statuses_for_ip=statuses_for_ip,
                    mismatches=mismatch_list,
                )

                if item["auto_fixable"]:
                    auto_fixable_items += 1
                if item["parity_relevant"]:
                    parity_mismatch_items += 1

                items.append(item)

                if len(items) >= max_items:
                    break

            if len(items) >= max_items:
                break

        mismatches_total = len(items)
        non_parity_mismatch_items = max(0, mismatches_total - parity_mismatch_items)
        return {
            "ok": True,
            "items": items,
            "summary": {
                "users": len(users),
                "mismatches": parity_mismatch_items,
                "mismatches_total": mismatches_total,
                "non_parity_mismatches": non_parity_mismatch_items,
                "no_authorized_device_count": int(mismatch_types.get("no_authorized_device", 0) or 0),
                "auto_fixable_items": auto_fixable_items,
                "mismatch_types": mismatch_types,
            },
        }
