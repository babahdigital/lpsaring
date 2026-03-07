from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import click
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserDevice
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services import settings_service
from app.utils.formatters import format_to_local_phone, get_phone_number_variations

UID_RE = re.compile(r"(?:^|[|\s])uid=([^|\s]+)")
USER_RE = re.compile(r"(?:^|[|\s])user=([^|\s]+)")


def _normalize_binding_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "regular"


def _extract_uid(comment: Any) -> str:
    text = str(comment or "")
    match = UID_RE.search(text)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _extract_user_token(comment: Any) -> str:
    text = str(comment or "")
    match = USER_RE.search(text)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _resolve_managed_lists() -> Dict[str, str]:
    return {
        "active": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active").strip(),
        "fup": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup").strip(),
        "inactive": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive").strip(),
        "expired": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired").strip(),
        "habis": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis").strip(),
        "blocked": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked").strip(),
        "unauthorized": str(
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized") or "unauthorized"
        ).strip(),
    }


def _is_valid_ip_candidate(value: str) -> bool:
    ip = str(value or "").strip()
    if not ip:
        return False
    if ip in {"0.0.0.0", "0.0.0.0/0"}:
        return False
    return True


def _append_sample(bucket: List[Dict[str, Any]], item: Dict[str, Any], sample_size: int) -> None:
    if len(bucket) >= sample_size:
        return
    bucket.append(item)


def _first_ip_from_set(values: Set[str]) -> str:
    for ip in sorted(values):
        if _is_valid_ip_candidate(ip):
            return ip
    return ""


def _build_user_indexes() -> Tuple[Dict[str, User], Dict[str, str], Dict[str, Set[str]], Set[str]]:
    users = db.session.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
        )
    ).all()

    users_by_uid: Dict[str, User] = {}
    uid_by_phone_variant: Dict[str, str] = {}
    authorized_macs_by_uid: Dict[str, Set[str]] = defaultdict(set)
    unlimited_uids: Set[str] = set()

    for user in users:
        uid = str(user.id)
        users_by_uid[uid] = user

        if bool(getattr(user, "is_unlimited_user", False)):
            unlimited_uids.add(uid)

        raw_phone = str(getattr(user, "phone_number", "") or "").strip()
        phone_tokens: Set[str] = set()
        phone_08 = format_to_local_phone(raw_phone)
        if phone_08:
            phone_tokens.add(phone_08)

        try:
            for value in get_phone_number_variations(raw_phone):
                if value:
                    phone_tokens.add(str(value).strip())
        except Exception:
            pass

        for token in phone_tokens:
            if token:
                uid_by_phone_variant[token] = uid

    rows = db.session.execute(
        select(UserDevice.user_id, UserDevice.mac_address).where(UserDevice.is_authorized.is_(True))
    ).all()
    for user_id, mac in rows:
        uid = str(user_id)
        mac_norm = str(mac or "").strip().upper()
        if mac_norm:
            authorized_macs_by_uid[uid].add(mac_norm)

    return users_by_uid, uid_by_phone_variant, authorized_macs_by_uid, unlimited_uids


def _build_binding_indexes(ip_binding_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    token_any: Set[str] = set()
    token_nonblocked: Set[str] = set()
    token_blocked: Set[str] = set()

    mac_any: Set[str] = set()
    mac_nonblocked: Set[str] = set()
    mac_blocked: Set[str] = set()

    ip_any: Set[str] = set()
    ip_nonblocked: Set[str] = set()
    ip_blocked: Set[str] = set()

    mac_to_ips_any: Dict[str, Set[str]] = defaultdict(set)
    mac_to_ips_nonblocked: Dict[str, Set[str]] = defaultdict(set)
    mac_to_ips_blocked: Dict[str, Set[str]] = defaultdict(set)

    for row in ip_binding_rows:
        binding_type = _normalize_binding_type(row.get("type"))
        is_blocked = binding_type == "blocked"

        uid = _extract_uid(row.get("comment"))
        user_token = _extract_user_token(row.get("comment"))
        mac = str(row.get("mac-address") or "").strip().upper()
        ip_address = str(row.get("address") or "").strip()

        for token in [uid, user_token]:
            if not token:
                continue
            token_any.add(token)
            if is_blocked:
                token_blocked.add(token)
            else:
                token_nonblocked.add(token)

        if mac:
            mac_any.add(mac)
            if is_blocked:
                mac_blocked.add(mac)
            else:
                mac_nonblocked.add(mac)

            if _is_valid_ip_candidate(ip_address):
                mac_to_ips_any[mac].add(ip_address)
                if is_blocked:
                    mac_to_ips_blocked[mac].add(ip_address)
                else:
                    mac_to_ips_nonblocked[mac].add(ip_address)

        if _is_valid_ip_candidate(ip_address):
            ip_any.add(ip_address)
            if is_blocked:
                ip_blocked.add(ip_address)
            else:
                ip_nonblocked.add(ip_address)

    return {
        "token_any": token_any,
        "token_nonblocked": token_nonblocked,
        "token_blocked": token_blocked,
        "mac_any": mac_any,
        "mac_nonblocked": mac_nonblocked,
        "mac_blocked": mac_blocked,
        "ip_any": ip_any,
        "ip_nonblocked": ip_nonblocked,
        "ip_blocked": ip_blocked,
        "mac_to_ips_any": dict(mac_to_ips_any),
        "mac_to_ips_nonblocked": dict(mac_to_ips_nonblocked),
        "mac_to_ips_blocked": dict(mac_to_ips_blocked),
    }


def _build_dhcp_indexes(dhcp_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    mac_any: Set[str] = set()
    ip_any: Set[str] = set()
    mac_to_ips_any: Dict[str, Set[str]] = defaultdict(set)

    bound_rows = 0
    static_rows = 0

    for row in dhcp_rows:
        mac = str(row.get("mac-address") or "").strip().upper()
        ip_address = str(row.get("address") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        dynamic_raw = str(row.get("dynamic") or "").strip().lower()

        if status == "bound":
            bound_rows += 1

        is_dynamic = dynamic_raw in {"true", "yes", "1"}
        if not is_dynamic:
            static_rows += 1

        if mac:
            mac_any.add(mac)

        if _is_valid_ip_candidate(ip_address):
            ip_any.add(ip_address)
            if mac:
                mac_to_ips_any[mac].add(ip_address)

    return {
        "mac_any": mac_any,
        "ip_any": ip_any,
        "mac_to_ips_any": dict(mac_to_ips_any),
        "bound_rows": bound_rows,
        "static_rows": static_rows,
    }


def _resolve_user_uid(
    uid_token: str,
    user_token: str,
    users_by_uid: Dict[str, User],
    uid_by_phone_variant: Dict[str, str],
) -> str:
    if uid_token and uid_token in users_by_uid:
        return uid_token
    if user_token and user_token in uid_by_phone_variant:
        return uid_by_phone_variant[user_token]
    return ""


def _has_binding_for_row(
    *,
    address: str,
    list_name: str,
    uid_token: str,
    user_token: str,
    resolved_uid: str,
    mac_hint: str,
    binding_indexes: Dict[str, Any],
    authorized_macs_by_uid: Dict[str, Set[str]],
    blocked_list_name: str,
) -> bool:
    require_blocked = bool(blocked_list_name and list_name == blocked_list_name)

    if require_blocked:
        token_set = binding_indexes["token_blocked"]
        mac_set = binding_indexes["mac_blocked"]
        ip_set = binding_indexes["ip_blocked"]
    else:
        token_set = binding_indexes["token_nonblocked"]
        mac_set = binding_indexes["mac_nonblocked"]
        ip_set = binding_indexes["ip_nonblocked"]

    if uid_token and uid_token in token_set:
        return True
    if user_token and user_token in token_set:
        return True
    if mac_hint and mac_hint in mac_set:
        return True

    if resolved_uid:
        for mac in authorized_macs_by_uid.get(resolved_uid, set()):
            if mac in mac_set:
                return True

    if _is_valid_ip_candidate(address) and address in ip_set:
        return True

    return False


def _has_any_binding_for_unauthorized_row(
    *,
    address: str,
    uid_token: str,
    user_token: str,
    resolved_uid: str,
    mac_hint: str,
    binding_indexes: Dict[str, Any],
    authorized_macs_by_uid: Dict[str, Set[str]],
) -> bool:
    if uid_token and uid_token in binding_indexes["token_any"]:
        return True
    if user_token and user_token in binding_indexes["token_any"]:
        return True
    if mac_hint and mac_hint in binding_indexes["mac_any"]:
        return True
    if _is_valid_ip_candidate(address) and address in binding_indexes["ip_any"]:
        return True

    if resolved_uid:
        for mac in authorized_macs_by_uid.get(resolved_uid, set()):
            if mac in binding_indexes["mac_any"]:
                return True

    return False


def _is_expected_missing_dhcp_for_blocked_row(
    *,
    list_name: str,
    blocked_list_name: str,
    has_binding: bool,
) -> bool:
    if not blocked_list_name:
        return False
    if str(list_name or "").strip() != str(blocked_list_name or "").strip():
        return False
    return bool(has_binding)


def _calculate_status_overlap_metrics(
    *,
    status_lists_by_ip: Dict[str, Set[str]],
    unauthorized_ips: Set[str],
    list_names: Dict[str, str],
    sample_size: int,
) -> Dict[str, Any]:
    fup_list_name = list_names.get("fup", "")
    active_list_name = list_names.get("active", "")
    blocked_list_name = list_names.get("blocked", "")

    status_multi_overlap_ips = sorted(
        ip for ip, lists in status_lists_by_ip.items() if _is_valid_ip_candidate(ip) and len(lists) > 1
    )
    status_multi_overlap_samples = [
        {
            "address": ip,
            "lists": sorted(status_lists_by_ip.get(ip, set())),
        }
        for ip in status_multi_overlap_ips[:sample_size]
    ]

    fup_overlap_active_ips = sorted(
        ip
        for ip, lists in status_lists_by_ip.items()
        if _is_valid_ip_candidate(ip) and fup_list_name in lists and active_list_name in lists
    )
    fup_overlap_blocked_ips = sorted(
        ip
        for ip, lists in status_lists_by_ip.items()
        if _is_valid_ip_candidate(ip) and fup_list_name in lists and blocked_list_name in lists
    )
    fup_overlap_unauthorized_ips = sorted(
        ip
        for ip in unauthorized_ips
        if _is_valid_ip_candidate(ip) and fup_list_name in status_lists_by_ip.get(ip, set())
    )

    return {
        "status_multi_overlap_ips": status_multi_overlap_ips,
        "status_multi_overlap_samples": status_multi_overlap_samples,
        "fup_overlap_active_ips": fup_overlap_active_ips,
        "fup_overlap_blocked_ips": fup_overlap_blocked_ips,
        "fup_overlap_unauthorized_ips": fup_overlap_unauthorized_ips,
    }


@click.command("audit-hotspot-parity")
@click.option(
    "--output",
    default="/tmp/lpsaring_addrlist_binding_parity_dryrun.json",
    show_default=True,
    help="File output JSON hasil audit.",
)
@click.option("--sample-size", default=20, show_default=True, type=int)
@click.option("--managed-only/--include-all", default=True, show_default=True)
@click.option("--fail-on-drift/--no-fail-on-drift", default=False, show_default=True)
@with_appcontext
def audit_hotspot_parity_command(
    output: str,
    sample_size: int,
    managed_only: bool,
    fail_on_drift: bool,
) -> None:
    """Audit holistik parity status-list, ip-binding, unauthorized overlap, dan DHCP lease."""

    if sample_size <= 0:
        raise click.ClickException("sample-size harus > 0")

    list_names = _resolve_managed_lists()
    unauthorized_list = list_names["unauthorized"]
    blocked_list = list_names["blocked"]

    managed_status_lists = {
        list_names["active"],
        list_names["fup"],
        list_names["inactive"],
        list_names["expired"],
        list_names["habis"],
        list_names["blocked"],
    }
    managed_status_lists = {name for name in managed_status_lists if name and name != unauthorized_list}

    users_by_uid, uid_by_phone_variant, authorized_macs_by_uid, unlimited_uids = _build_user_indexes()

    status_summary = {
        list_name: {
            "total": 0,
            "with_binding": 0,
            "without_binding": 0,
            "with_dhcp_lease": 0,
            "without_dhcp_lease": 0,
            "without_dhcp_expected_blocked": 0,
            "overlap_unauthorized": 0,
        }
        for list_name in sorted(managed_status_lists)
    }

    samples: Dict[str, List[Dict[str, Any]]] = {
        "status_without_binding": [],
        "status_without_dhcp": [],
        "status_without_dhcp_expected_blocked": [],
        "status_multi_overlap": [],
        "unauthorized_overlap": [],
        "unauthorized_with_binding": [],
        "authorized_mac_without_binding": [],
        "authorized_mac_without_dhcp": [],
        "binding_dhcp_ip_mismatch": [],
        "unlimited_without_binding": [],
    }

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException("Gagal konek MikroTik")

        address_list_rows = api.get_resource("/ip/firewall/address-list").get() or []
        ip_binding_rows = api.get_resource("/ip/hotspot/ip-binding").get() or []
        dhcp_lease_rows = api.get_resource("/ip/dhcp-server/lease").get() or []

    binding_indexes = _build_binding_indexes(ip_binding_rows)
    dhcp_indexes = _build_dhcp_indexes(dhcp_lease_rows)

    unauthorized_rows = [
        row
        for row in address_list_rows
        if str(row.get("list") or "").strip() == unauthorized_list
    ]
    unauthorized_ips = {
        str(row.get("address") or "").strip()
        for row in unauthorized_rows
        if _is_valid_ip_candidate(str(row.get("address") or ""))
    }

    scanned_status_rows = 0
    managed_status_rows = 0
    status_ips: Set[str] = set()
    status_lists_by_ip: Dict[str, Set[str]] = defaultdict(set)
    all_status_without_binding = 0

    for row in address_list_rows:
        list_name = str(row.get("list") or "").strip()
        if list_name not in managed_status_lists:
            continue

        scanned_status_rows += 1
        comment = str(row.get("comment") or "")
        if managed_only and "lpsaring|status=" not in comment:
            continue

        managed_status_rows += 1
        address = str(row.get("address") or "").strip()
        if _is_valid_ip_candidate(address):
            status_ips.add(address)
            status_lists_by_ip[address].add(list_name)

        uid_token = _extract_uid(comment)
        user_token = _extract_user_token(comment)
        mac_hint = str(row.get("mac-address") or "").strip().upper()
        resolved_uid = _resolve_user_uid(uid_token, user_token, users_by_uid, uid_by_phone_variant)

        has_binding = _has_binding_for_row(
            address=address,
            list_name=list_name,
            uid_token=uid_token,
            user_token=user_token,
            resolved_uid=resolved_uid,
            mac_hint=mac_hint,
            binding_indexes=binding_indexes,
            authorized_macs_by_uid=authorized_macs_by_uid,
            blocked_list_name=blocked_list,
        )

        has_dhcp = _is_valid_ip_candidate(address) and address in dhcp_indexes["ip_any"]
        is_overlap_unauthorized = _is_valid_ip_candidate(address) and address in unauthorized_ips

        row_summary = status_summary[list_name]
        row_summary["total"] += 1

        if has_binding:
            row_summary["with_binding"] += 1
        else:
            row_summary["without_binding"] += 1
            all_status_without_binding += 1
            _append_sample(
                samples["status_without_binding"],
                {
                    "list": list_name,
                    "address": address,
                    "uid": uid_token,
                    "user": user_token,
                    "resolved_uid": resolved_uid,
                },
                sample_size,
            )

        if has_dhcp:
            row_summary["with_dhcp_lease"] += 1
        else:
            if _is_expected_missing_dhcp_for_blocked_row(
                list_name=list_name,
                blocked_list_name=blocked_list,
                has_binding=has_binding,
            ):
                row_summary["without_dhcp_expected_blocked"] += 1
                _append_sample(
                    samples["status_without_dhcp_expected_blocked"],
                    {
                        "list": list_name,
                        "address": address,
                        "uid": uid_token,
                        "user": user_token,
                        "resolved_uid": resolved_uid,
                    },
                    sample_size,
                )
            else:
                row_summary["without_dhcp_lease"] += 1
                _append_sample(
                    samples["status_without_dhcp"],
                    {
                        "list": list_name,
                        "address": address,
                        "uid": uid_token,
                        "user": user_token,
                        "resolved_uid": resolved_uid,
                    },
                    sample_size,
                )

        if is_overlap_unauthorized:
            row_summary["overlap_unauthorized"] += 1
            _append_sample(
                samples["unauthorized_overlap"],
                {
                    "list": list_name,
                    "address": address,
                    "uid": uid_token,
                    "user": user_token,
                    "resolved_uid": resolved_uid,
                },
                sample_size,
            )

    unauthorized_with_binding = 0
    unauthorized_with_known_user = 0

    for row in unauthorized_rows:
        address = str(row.get("address") or "").strip()
        comment = str(row.get("comment") or "")
        uid_token = _extract_uid(comment)
        user_token = _extract_user_token(comment)
        mac_hint = str(row.get("mac-address") or "").strip().upper()
        resolved_uid = _resolve_user_uid(uid_token, user_token, users_by_uid, uid_by_phone_variant)

        if resolved_uid:
            unauthorized_with_known_user += 1

        has_any_binding = _has_any_binding_for_unauthorized_row(
            address=address,
            uid_token=uid_token,
            user_token=user_token,
            resolved_uid=resolved_uid,
            mac_hint=mac_hint,
            binding_indexes=binding_indexes,
            authorized_macs_by_uid=authorized_macs_by_uid,
        )
        if has_any_binding:
            unauthorized_with_binding += 1
            _append_sample(
                samples["unauthorized_with_binding"],
                {
                    "address": address,
                    "uid": uid_token,
                    "user": user_token,
                    "resolved_uid": resolved_uid,
                },
                sample_size,
            )

    overlap_ips = sorted(ip for ip in unauthorized_ips if ip in status_ips)

    status_overlap_metrics = _calculate_status_overlap_metrics(
        status_lists_by_ip=status_lists_by_ip,
        unauthorized_ips=unauthorized_ips,
        list_names=list_names,
        sample_size=sample_size,
    )
    status_multi_overlap_ips = status_overlap_metrics["status_multi_overlap_ips"]
    fup_overlap_active_ips = status_overlap_metrics["fup_overlap_active_ips"]
    fup_overlap_blocked_ips = status_overlap_metrics["fup_overlap_blocked_ips"]
    fup_overlap_unauthorized_ips = status_overlap_metrics["fup_overlap_unauthorized_ips"]
    for item in status_overlap_metrics["status_multi_overlap_samples"]:
        _append_sample(samples["status_multi_overlap"], item, sample_size)

    authorized_macs: Set[str] = set()
    for macs in authorized_macs_by_uid.values():
        authorized_macs.update(macs)

    authorized_with_binding = 0
    authorized_with_dhcp = 0
    binding_dhcp_ip_mismatch = 0

    for mac in sorted(authorized_macs):
        has_binding = mac in binding_indexes["mac_any"]
        has_dhcp = mac in dhcp_indexes["mac_any"]

        if has_binding:
            authorized_with_binding += 1
        else:
            _append_sample(
                samples["authorized_mac_without_binding"],
                {"mac": mac},
                sample_size,
            )

        if has_dhcp:
            authorized_with_dhcp += 1
        else:
            _append_sample(
                samples["authorized_mac_without_dhcp"],
                {"mac": mac},
                sample_size,
            )

        if has_binding and has_dhcp:
            binding_ip = _first_ip_from_set(binding_indexes["mac_to_ips_any"].get(mac, set()))
            dhcp_ip = _first_ip_from_set(dhcp_indexes["mac_to_ips_any"].get(mac, set()))
            if binding_ip and dhcp_ip and binding_ip != dhcp_ip:
                binding_dhcp_ip_mismatch += 1
                _append_sample(
                    samples["binding_dhcp_ip_mismatch"],
                    {
                        "mac": mac,
                        "binding_ip": binding_ip,
                        "dhcp_ip": dhcp_ip,
                    },
                    sample_size,
                )

    unlimited_with_binding = 0
    unlimited_without_binding = 0

    scoped_unlimited_uids = {uid for uid in unlimited_uids if bool(authorized_macs_by_uid.get(uid, set()))}
    scoped_unlimited_with_binding = 0
    scoped_unlimited_without_binding = 0

    for uid in sorted(unlimited_uids):
        has_binding = uid in binding_indexes["token_nonblocked"]
        if not has_binding:
            for mac in authorized_macs_by_uid.get(uid, set()):
                if mac in binding_indexes["mac_nonblocked"]:
                    has_binding = True
                    break

        if has_binding:
            unlimited_with_binding += 1
        else:
            unlimited_without_binding += 1

        if uid in scoped_unlimited_uids:
            if has_binding:
                scoped_unlimited_with_binding += 1
            else:
                scoped_unlimited_without_binding += 1
                user = users_by_uid.get(uid)
                _append_sample(
                    samples["unlimited_without_binding"],
                    {
                        "uid": uid,
                        "phone": str(getattr(user, "phone_number", "") or "") if user else "",
                    },
                    sample_size,
                )

    critical_lists = [
        list_names["active"],
        list_names["fup"],
        list_names["habis"],
        list_names["blocked"],
    ]
    critical_without_binding_total = 0
    for list_name in critical_lists:
        if list_name in status_summary:
            critical_without_binding_total += int(status_summary[list_name]["without_binding"])

    blocked_without_dhcp_expected_total = 0
    if blocked_list in status_summary:
        blocked_without_dhcp_expected_total = int(
            status_summary.get(blocked_list, {}).get("without_dhcp_expected_blocked", 0)
        )

    report: Dict[str, Any] = {
        "generated_at_utc": datetime.now(dt_timezone.utc).isoformat(),
        "options": {
            "managed_only": managed_only,
            "sample_size": sample_size,
        },
        "list_names": list_names,
        "totals": {
            "address_list_rows": len(address_list_rows),
            "ip_binding_rows": len(ip_binding_rows),
            "dhcp_lease_rows": len(dhcp_lease_rows),
            "status_rows_scanned": scanned_status_rows,
            "status_rows_managed": managed_status_rows,
        },
        "status_summary": status_summary,
        "unauthorized": {
            "total_rows": len(unauthorized_rows),
            "unique_ips": len(unauthorized_ips),
            "overlap_with_status_count": len(overlap_ips),
            "overlap_with_status_sample_ips": overlap_ips[:sample_size],
            "rows_with_binding_count": unauthorized_with_binding,
            "rows_with_known_user_count": unauthorized_with_known_user,
        },
        "status_overlap": {
            "multi_status_ip_count": len(status_multi_overlap_ips),
            "multi_status_sample_ips": status_multi_overlap_ips[:sample_size],
            "fup_with_active_count": len(fup_overlap_active_ips),
            "fup_with_active_sample_ips": fup_overlap_active_ips[:sample_size],
            "fup_with_blocked_count": len(fup_overlap_blocked_ips),
            "fup_with_blocked_sample_ips": fup_overlap_blocked_ips[:sample_size],
            "fup_with_unauthorized_count": len(fup_overlap_unauthorized_ips),
            "fup_with_unauthorized_sample_ips": fup_overlap_unauthorized_ips[:sample_size],
        },
        "dhcp_alignment": {
            "authorized_db_macs": len(authorized_macs),
            "authorized_with_ip_binding": authorized_with_binding,
            "authorized_without_ip_binding": len(authorized_macs) - authorized_with_binding,
            "authorized_with_dhcp_lease": authorized_with_dhcp,
            "authorized_without_dhcp_lease": len(authorized_macs) - authorized_with_dhcp,
            "binding_dhcp_ip_mismatch": binding_dhcp_ip_mismatch,
            "dhcp_bound_rows": int(dhcp_indexes["bound_rows"]),
            "dhcp_static_rows": int(dhcp_indexes["static_rows"]),
        },
        "unlimited_alignment": {
            "all_unlimited_users": {
                "total": len(unlimited_uids),
                "with_binding": unlimited_with_binding,
                "without_binding": unlimited_without_binding,
            },
            "scoped_unlimited_users_with_authorized_device": {
                "total": len(scoped_unlimited_uids),
                "with_binding": scoped_unlimited_with_binding,
                "without_binding": scoped_unlimited_without_binding,
            },
        },
        "policy_focus": {
            "critical_lists": critical_lists,
            "critical_without_binding_total": critical_without_binding_total,
            "all_status_without_binding_total": all_status_without_binding,
            "blocked_without_dhcp_expected_total": blocked_without_dhcp_expected_total,
            "unauthorized_must_not_duplicate_status_count": len(overlap_ips),
            "status_multi_list_overlap_count": len(status_multi_overlap_ips),
            "fup_overlap_active_count": len(fup_overlap_active_ips),
            "fup_overlap_blocked_count": len(fup_overlap_blocked_ips),
            "fup_overlap_unauthorized_count": len(fup_overlap_unauthorized_ips),
        },
        "samples": samples,
    }

    output_path = Path(output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    except Exception as exc:
        raise click.ClickException(f"Gagal menulis output JSON ke {output}: {exc}") from exc

    click.echo(
        " ".join(
            [
                f"output_json={output}",
                f"status_without_binding={all_status_without_binding}",
                f"critical_without_binding={critical_without_binding_total}",
                f"unauthorized_overlap={len(overlap_ips)}",
                f"status_multi_overlap={len(status_multi_overlap_ips)}",
                f"fup_overlap_active={len(fup_overlap_active_ips)}",
                f"fup_overlap_blocked={len(fup_overlap_blocked_ips)}",
                f"fup_overlap_unauthorized={len(fup_overlap_unauthorized_ips)}",
                f"unauthorized_with_binding={unauthorized_with_binding}",
                f"authorized_mac_without_binding={len(authorized_macs) - authorized_with_binding}",
                f"authorized_mac_without_dhcp={len(authorized_macs) - authorized_with_dhcp}",
                f"binding_dhcp_ip_mismatch={binding_dhcp_ip_mismatch}",
                f"unlimited_without_binding_scoped={scoped_unlimited_without_binding}",
            ]
        )
    )

    if fail_on_drift:
        violations = {
            "critical_without_binding_total": critical_without_binding_total,
            "all_status_without_binding_total": all_status_without_binding,
            "unauthorized_overlap": len(overlap_ips),
            "status_multi_overlap": len(status_multi_overlap_ips),
            "fup_overlap_active": len(fup_overlap_active_ips),
            "fup_overlap_blocked": len(fup_overlap_blocked_ips),
            "fup_overlap_unauthorized": len(fup_overlap_unauthorized_ips),
            "unauthorized_with_binding": unauthorized_with_binding,
            "unlimited_without_binding_scoped": scoped_unlimited_without_binding,
            "authorized_mac_without_binding": len(authorized_macs) - authorized_with_binding,
            "authorized_mac_without_dhcp": len(authorized_macs) - authorized_with_dhcp,
            "binding_dhcp_ip_mismatch": binding_dhcp_ip_mismatch,
        }
        failed = {key: value for key, value in violations.items() if int(value) > 0}
        if failed:
            details = ", ".join([f"{k}={v}" for k, v in failed.items()])
            raise click.ClickException(f"Audit hotspot parity menemukan drift: {details}")
