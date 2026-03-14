# backend/app/services/hotspot_sync_service.py
from dataclasses import dataclass
import logging
import math
import threading
import uuid
import ipaddress
from contextlib import nullcontext
from datetime import datetime, timezone as dt_timezone, date, timedelta
from typing import Any, Dict, List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import (
    User,
    UserRole,
    ApprovalStatus,
    DailyUsageLog,
    NotificationRecipient,
    NotificationType,
    Package,
    Transaction,
    UserDevice,
    AdminActionLog,
    AdminActionType,
)
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_ip_by_mac,
    upsert_dhcp_static_lease,
    set_hotspot_user_profile,
    delete_hotspot_user,
    sync_address_list_for_user,
    upsert_address_list_entry,
    upsert_ip_binding,
    remove_address_list_entry,
)
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.services import settings_service
from app.services.notification_service import get_notification_message
from app.services.device_management_service import (
    _remove_ip_binding,
    _ensure_static_dhcp_lease,
    register_or_update_device,
)
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.quota_mutation_ledger_service import (
    append_quota_mutation_event,
    lock_user_quota_row,
    snapshot_user_quota_state,
)
from app.utils.formatters import (
    format_to_local_phone,
    get_app_date_time_strings,
    get_app_local_datetime,
    get_phone_number_variations,
    normalize_to_e164,
    round_mb,
)
from app.utils.quota_debt import (
    compute_debt_mb,
    estimate_debt_rp_from_cheapest_package,
    format_rupiah,
)
from app.utils.block_reasons import is_auto_debt_limit_reason, build_auto_debt_limit_reason
from app.utils.metrics_utils import increment_metric

logger = logging.getLogger(__name__)

BYTES_PER_MB = 1024 * 1024
REDIS_LAST_BYTES_PREFIX = "quota:last_bytes:mac:"
REDIS_SYNC_LOCK_PREFIX = "quota:sync_lock:user:"
REDIS_GLOBAL_SYNC_LOCK_KEY = "quota:sync_lock:global"
REDIS_ACCESS_STATUS_DEDUPE_PREFIX = "wa:dedupe:access_status:"
REDIS_AUTO_DEBT_WARNING_DEDUPE_PREFIX = "wa:dedupe:auto_debt_warning:"
LOCAL_GLOBAL_SYNC_LOCK_TOKEN = "__local_global_sync_lock__"
_local_global_sync_lock = threading.Lock()
_thread_local_state = threading.local()


@dataclass(frozen=True)
class HotspotUsageSyncDbState:
    user_ids: List[uuid.UUID]


@dataclass(frozen=True)
class HotspotUsageSyncRuntimeSettings:
    auto_enroll_devices_from_ip_binding: bool
    max_devices_per_user: int
    auto_enroll_debug_log: bool
    blocked_profile: str
    expired_profile: str
    habis_profile: str
    fup_profile: str
    whatsapp_notifications_enabled: bool


@dataclass(frozen=True)
class HotspotUsageDeviceDelta:
    mac_address: str
    ip_address: Optional[str]
    label: Optional[str]
    delta_mb: float
    previous_bytes_total: int
    bytes_total: int
    host_id: Optional[str]
    uptime_seconds: Optional[int]
    source_address: Optional[str]
    to_address: Optional[str]


@dataclass(frozen=True)
class HotspotUsageRebaselineEvent:
    mac_address: str
    ip_address: Optional[str]
    label: Optional[str]
    reason: str
    previous_bytes_total: Optional[int]
    bytes_total: int
    previous_host_id: Optional[str]
    host_id: Optional[str]
    previous_uptime_seconds: Optional[int]
    uptime_seconds: Optional[int]
    source_address: Optional[str]
    to_address: Optional[str]


@dataclass(frozen=True)
class HotspotUsageUpdateResult:
    delta_mb: float
    new_total_usage_mb: float
    device_deltas: List[HotspotUsageDeviceDelta]
    rebaseline_events: List[HotspotUsageRebaselineEvent]


def _is_demo_phone_whitelisted(phone_number: Optional[str]) -> bool:
    if not phone_number:
        return False

    try:
        normalized_phone = normalize_to_e164(str(phone_number))
    except ValueError:
        return False

    allowed_raw = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(allowed_raw, list) or len(allowed_raw) == 0:
        return False

    target_variants = set(get_phone_number_variations(normalized_phone))

    for candidate in allowed_raw:
        if candidate is None:
            continue

        raw_phone = str(candidate).strip()
        if raw_phone == "":
            continue

        try:
            normalized_candidate = normalize_to_e164(raw_phone)
        except ValueError:
            continue

        candidate_variants = set(get_phone_number_variations(normalized_candidate))
        if target_variants.intersection(candidate_variants):
            return True

    return False


def _is_demo_user(user: User) -> bool:
    return _is_demo_phone_whitelisted(getattr(user, "phone_number", None))


def _load_hotspot_usage_sync_db_state() -> HotspotUsageSyncDbState:
    try:
        raw_user_ids = db.session.scalars(
            select(User.id).where(
                User.is_active,
                User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        ).all()

        return HotspotUsageSyncDbState(
            user_ids=[getattr(user_id, "id", user_id) for user_id in raw_user_ids if getattr(user_id, "id", user_id)]
        )
    finally:
        # Lepas sesi awal agar sinkronisasi tidak menahan transaksi idle
        # sepanjang operasi RouterOS dan loop per-user.
        db.session.remove()


def _load_hotspot_usage_sync_runtime_settings() -> HotspotUsageSyncRuntimeSettings:
    try:
        return HotspotUsageSyncRuntimeSettings(
            auto_enroll_devices_from_ip_binding=(
                settings_service.get_setting("AUTO_ENROLL_DEVICES_FROM_IP_BINDING", "True") == "True"
            ),
            max_devices_per_user=settings_service.get_setting_as_int("MAX_DEVICES_PER_USER", 3),
            auto_enroll_debug_log=(settings_service.get_setting("AUTO_ENROLL_DEBUG_LOG", "False") == "True"),
            blocked_profile=(settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"),
            expired_profile=(settings_service.get_setting("MIKROTIK_EXPIRED_PROFILE", "expired") or "expired"),
            habis_profile=(settings_service.get_setting("MIKROTIK_HABIS_PROFILE", "habis") or "habis"),
            fup_profile=(settings_service.get_setting("MIKROTIK_FUP_PROFILE", "fup") or "fup"),
            whatsapp_notifications_enabled=(
                settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
            ),
        )
    finally:
        # Lepas sesi settings sebelum loop per-user memulai transaksi eksplisit.
        db.session.remove()


def _load_hotspot_sync_user(user_id: uuid.UUID) -> Optional[User]:
    return db.session.scalars(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.transactions).selectinload(Transaction.package),
            selectinload(User.devices),
        )
    ).first()


def _is_valid_ip_candidate(value: Optional[str]) -> bool:
    if not value:
        return False
    ip = str(value).strip()
    if not ip:
        return False
    if ip in {"0.0.0.0", "0.0.0.0/0"}:
        return False
    return True


def _resolve_hotspot_status_networks() -> List[ipaddress._BaseNetwork]:
    cidrs = current_app.config.get("MIKROTIK_UNAUTHORIZED_CIDRS") or current_app.config.get("HOTSPOT_CLIENT_IP_CIDRS")
    if not cidrs:
        return []

    networks: List[ipaddress._BaseNetwork] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(str(cidr), strict=False))
        except Exception:
            continue
    return networks


def _is_ip_in_hotspot_status_networks(ip_text: Optional[str], networks: Optional[List[ipaddress._BaseNetwork]] = None) -> bool:
    if not _is_valid_ip_candidate(ip_text):
        return False

    ip_str = str(ip_text).strip()
    active_networks = networks if networks is not None else _resolve_hotspot_status_networks()
    if not active_networks:
        return True

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except Exception:
        return False

    return any(ip_obj in net for net in active_networks)


def _collect_candidate_ips_for_user(
    user: User,
    host_usage_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ip_binding_rows_by_mac: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[str]:
    ips: List[str] = []
    seen: set[str] = set()
    hotspot_networks = _resolve_hotspot_status_networks()

    def _add_ip(ip_value: Optional[str]) -> None:
        if not _is_valid_ip_candidate(ip_value):
            return
        ip_str = str(ip_value).strip()
        if not _is_ip_in_hotspot_status_networks(ip_str, hotspot_networks):
            return
        if ip_str in seen:
            return
        seen.add(ip_str)
        ips.append(ip_str)

    for device in user.devices or []:
        if getattr(device, "ip_address", None):
            _add_ip(str(device.ip_address))

        mac = (getattr(device, "mac_address", None) or "").upper().strip()
        if not mac:
            continue

        if host_usage_map:
            _add_ip(host_usage_map.get(mac, {}).get("address"))
        if ip_binding_map:
            _add_ip(ip_binding_map.get(mac, {}).get("address"))
        # Fallback: raw ip-binding rows (tidak memerlukan komentar UID).
        # Berguna saat device sedang offline dan device.ip_address belum diset.
        if ip_binding_rows_by_mac:
            for row in ip_binding_rows_by_mac.get(mac, []):
                _add_ip(row.get("address"))

    return ips


def _normalize_binding_type(value: Any) -> str:
    binding_type = str(value or "").strip().lower()
    return binding_type or "regular"


def _binding_type_matches_policy(actual_type: Any, expected_type: str) -> bool:
    normalized_actual = _normalize_binding_type(actual_type)
    normalized_expected = _normalize_binding_type(expected_type)

    if normalized_expected == "blocked":
        return normalized_actual == "blocked"

    return normalized_actual != "blocked"


def _snapshot_ip_binding_rows_by_mac(api: Any) -> Tuple[bool, Dict[str, List[Dict[str, Any]]]]:
    if not api:
        return False, {}

    try:
        rows = api.get_resource("/ip/hotspot/ip-binding").get() or []
    except Exception as exc:
        logger.warning("Gagal mengambil snapshot ip-binding raw: %s", exc)
        return False, {}

    by_mac: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        mac = str(row.get("mac-address") or "").strip().upper()
        if not mac:
            continue

        normalized_row = {
            "type": _normalize_binding_type(row.get("type")),
            "address": str(row.get("address") or "").strip(),
            "comment": row.get("comment"),
        }
        by_mac.setdefault(mac, []).append(normalized_row)

    return True, by_mac


def _snapshot_dhcp_ips_by_mac(api: Any) -> Tuple[bool, Dict[str, set[str]]]:
    if not api:
        return False, {}

    try:
        rows = api.get_resource("/ip/dhcp-server/lease").get() or []
    except Exception as exc:
        logger.warning("Gagal mengambil snapshot DHCP lease raw: %s", exc)
        return False, {}

    by_mac: Dict[str, set[str]] = {}
    for row in rows:
        mac = str(row.get("mac-address") or "").strip().upper()
        if not mac:
            continue

        status = str(row.get("status") or "").strip().lower()
        if status == "waiting":
            continue

        ip_text = str(row.get("address") or "").strip()
        if not _is_valid_ip_candidate(ip_text):
            continue

        by_mac.setdefault(mac, set()).add(ip_text)

    return True, by_mac


def _resolve_managed_status_lists() -> List[str]:
    list_active = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active"
    list_fup = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup"
    list_inactive = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
    list_expired = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
    list_habis = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis"
    list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
    list_unauthorized = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized") or "unauthorized"

    unique_lists: List[str] = []
    for list_name in [list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked]:
        if not list_name:
            continue
        if list_name == list_unauthorized:
            continue
        if list_name in unique_lists:
            continue
        unique_lists.append(list_name)

    return unique_lists


def _remove_managed_status_entries_for_ip(api: object, ip_address: str) -> None:
    if not api or not _is_valid_ip_candidate(ip_address):
        return

    for list_name in _resolve_managed_status_lists():
        remove_address_list_entry(api_connection=api, address=str(ip_address).strip(), list_name=list_name)


def _comment_has_tag_value(comment_text: str, tag_name: str, expected_value: str) -> bool:
    if not comment_text or not tag_name or not expected_value:
        return False

    token = f"|{tag_name}={expected_value}|"
    if token in comment_text:
        return True

    trailing_token = f"|{tag_name}={expected_value}"
    return comment_text.endswith(trailing_token)


def _is_status_entry_owned_by_user(comment: Any, *, user_id: str, username_08: str) -> bool:
    comment_text = str(comment or "").strip()
    if "lpsaring|status=" not in comment_text:
        return False

    if user_id and _comment_has_tag_value(comment_text, "uid", user_id):
        return True

    if username_08 and _comment_has_tag_value(comment_text, "user", username_08):
        return True

    return False


def _prune_stale_status_entries_for_user(api: object, user: User, keep_ips: Optional[List[str]] = None) -> int:
    if not api or not user:
        return 0

    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "")
    if not username_08:
        return 0

    user_id = str(getattr(user, "id", "") or "").strip()
    keep_ip_set = {
        str(ip).strip()
        for ip in (keep_ips or [])
        if _is_valid_ip_candidate(str(ip or "").strip())
    }

    resource_getter = getattr(api, "get_resource", None)
    if not callable(resource_getter):
        return 0

    try:
        resource = resource_getter("/ip/firewall/address-list")
    except Exception as exc:
        logger.debug("Skip prune stale status-list per-user karena gagal ambil resource: %s", exc)
        return 0

    rows_getter = getattr(resource, "get", None)
    if not callable(rows_getter):
        return 0

    removed = 0
    for list_name in _resolve_managed_status_lists():
        try:
            rows = rows_getter(list=list_name) or []
        except Exception:
            continue

        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            address = str(row.get("address") or "").strip()
            if not _is_valid_ip_candidate(address):
                continue
            if address in keep_ip_set:
                continue

            if not _is_status_entry_owned_by_user(
                row.get("comment"),
                user_id=user_id,
                username_08=username_08,
            ):
                continue

            ok_remove, _remove_msg = remove_address_list_entry(
                api_connection=api,
                address=address,
                list_name=list_name,
            )
            if ok_remove:
                removed += 1

    if removed > 0:
        logger.info(
            "Prune stale status-list per-user: user=%s phone=%s removed=%s keep_ips=%s",
            user_id,
            username_08,
            removed,
            sorted(keep_ip_set),
        )

    return removed


def _has_policy_binding_for_user(
    user: User,
    *,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]],
    ip_binding_rows_by_mac: Optional[Dict[str, List[Dict[str, Any]]]],
) -> bool:
    if not user:
        return False

    if not ip_binding_map and not ip_binding_rows_by_mac:
        # Fail-open when snapshot tidak tersedia (mis. router sementara error)
        # agar tidak memicu pembersihan agresif yang salah.
        return True

    expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular").strip().lower() or "regular"
    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "")
    user_tokens = {
        str(getattr(user, "id", "") or "").strip(),
        str(username_08 or "").strip(),
    }
    user_tokens = {token for token in user_tokens if token}

    authorized_macs = {
        str(getattr(device, "mac_address", "") or "").strip().upper()
        for device in (user.devices or [])
        if bool(getattr(device, "is_authorized", False)) and str(getattr(device, "mac_address", "") or "").strip()
    }

    if ip_binding_rows_by_mac:
        for mac in authorized_macs:
            for row in ip_binding_rows_by_mac.get(mac, []):
                if _binding_type_matches_policy(row.get("type"), expected_binding_type):
                    return True

    if ip_binding_map:
        for mac, entry in ip_binding_map.items():
            if mac and str(mac).strip().upper() in authorized_macs:
                if _binding_type_matches_policy(entry.get("type"), expected_binding_type):
                    return True

            token = str(entry.get("user_id") or "").strip()
            if token and token in user_tokens:
                if _binding_type_matches_policy(entry.get("type"), expected_binding_type):
                    return True

    return False


def _get_thresholds_from_env(key: str, default: List[int]) -> List[int]:
    values = settings_service.get_setting(key, None)
    if values is None:
        return default
    try:
        if isinstance(values, str):
            parsed = settings_service.get_setting(key, None)
            if parsed is None:
                return default
            # values bisa berupa "[20,10,5]" atau "20,10,5"
            if parsed.strip().startswith("["):
                return [int(v) for v in parsed.strip("[]").split(",") if v.strip()]
            return [int(v) for v in parsed.split(",") if v.strip()]
    except Exception:
        return default
    return default


def _calculate_remaining(user: User) -> Tuple[float, float]:
    purchased_mb = float(user.total_quota_purchased_mb or 0.0)
    used_mb = float(user.total_quota_used_mb or 0.0)
    remaining_mb = max(0.0, purchased_mb - used_mb)
    remaining_percent = 0.0
    if purchased_mb > 0:
        remaining_percent = round((remaining_mb / purchased_mb) * 100, 2)
    return float(round_mb(remaining_mb)), remaining_percent


def _resolve_auto_quota_debt_for_limit(user: User) -> float:
    """Resolve auto debt used by immediate QUOTA_DEBT_LIMIT_MB policy."""
    try:
        return float(getattr(user, "quota_debt_auto_mb", 0) or 0.0)
    except Exception:
        return float(compute_debt_mb(float(user.total_quota_purchased_mb or 0.0), float(user.total_quota_used_mb or 0.0)))


def _is_auto_debt_blocked(user: User) -> bool:
    if not bool(getattr(user, "is_blocked", False)):
        return False
    reason = getattr(user, "blocked_reason", "")
    return is_auto_debt_limit_reason(reason)


def _emit_policy_binding_mismatch_metrics(user: User, ip_binding_map: Optional[Dict[str, Dict[str, Any]]]) -> None:
    if not ip_binding_map:
        return
    if not _is_auto_debt_blocked(user):
        return

    expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "").strip().lower()
    if expected_binding_type != "regular":
        increment_metric("policy.mismatch.auto_debt_expected_non_regular")
        return

    mismatch_count = 0
    for device in user.devices or []:
        mac = str(getattr(device, "mac_address", "") or "").strip().upper()
        if not mac:
            continue
        binding_entry = ip_binding_map.get(mac)
        if not binding_entry:
            continue
        actual_binding_type = str(binding_entry.get("type") or "").strip().lower()
        if actual_binding_type == "blocked":
            mismatch_count += 1

    if mismatch_count > 0:
        increment_metric("policy.mismatch.auto_debt_blocked_ip_binding")
        increment_metric("policy.mismatch.auto_debt_blocked_ip_binding.devices", mismatch_count)


def _self_heal_policy_binding_for_user(
    api: object,
    user: User,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]],
    host_usage_map: Optional[Dict[str, Dict[str, Any]]],
) -> int:
    if not api or not user or not ip_binding_map:
        return 0

    enabled_cfg = current_app.config.get("ENABLE_POLICY_BINDING_SELF_HEAL", "True")
    enabled_raw = str(enabled_cfg).strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return 0

    expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular").strip().lower()
    if not expected_binding_type:
        return 0

    now_utc = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now_utc)
    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "") or str(
        getattr(user, "phone_number", "") or ""
    )

    repaired = 0
    for device in user.devices or []:
        if not bool(getattr(device, "is_authorized", False)):
            continue

        mac = str(getattr(device, "mac_address", "") or "").strip().upper()
        if not mac:
            continue

        current_entry = ip_binding_map.get(mac) or {}
        actual_binding_type = str(current_entry.get("type") or "").strip().lower()
        if actual_binding_type == expected_binding_type:
            continue

        ip_addr = str(getattr(device, "ip_address", "") or "").strip()
        if not ip_addr and host_usage_map:
            ip_addr = str((host_usage_map.get(mac) or {}).get("address") or "").strip()

        ok, msg = upsert_ip_binding(
            api_connection=api,
            mac_address=mac,
            address=ip_addr or None,
            server=getattr(user, "mikrotik_server_name", None),
            binding_type=expected_binding_type,
            comment=(
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source=sync-self-heal|date={date_str}|time={time_str}"
            ),
        )
        if ok:
            repaired += 1
            increment_metric("policy.binding_self_heal.repaired")
            entry = ip_binding_map.setdefault(mac, {})
            entry["type"] = expected_binding_type
            if ip_addr:
                entry["address"] = ip_addr

            if ip_addr:
                dhcp_server_name = (
                    settings_service.get_setting("MIKROTIK_DHCP_LEASE_SERVER_NAME", "") or ""
                ).strip() or None
                _ensure_static_dhcp_lease(
                    mac_address=mac,
                    ip_address=ip_addr,
                    comment=(
                        f"lpsaring|static-dhcp|user={username_08}|uid={user.id}|role={user.role.value}"
                        f"|source=sync-self-heal|date={date_str}|time={time_str}"
                    ),
                    server=dhcp_server_name,
                )
        else:
            increment_metric("policy.binding_self_heal.failed")
            logger.warning(
                "Policy self-heal gagal update ip-binding user=%s mac=%s expected=%s: %s",
                user.id,
                mac,
                expected_binding_type,
                msg,
            )

    return repaired


def _self_heal_policy_dhcp_for_user(
    api: object,
    user: User,
    *,
    host_usage_map: Optional[Dict[str, Dict[str, Any]]],
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]],
    dhcp_ips_by_mac: Optional[Dict[str, set[str]]],
) -> int:
    if not api or not user or dhcp_ips_by_mac is None:
        return 0

    enabled_cfg = settings_service.get_setting("MIKROTIK_DHCP_STATIC_LEASE_ENABLED", "False")
    if str(enabled_cfg or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return 0

    dhcp_server_name = (settings_service.get_setting("MIKROTIK_DHCP_LEASE_SERVER_NAME", "") or "").strip()
    if not dhcp_server_name:
        return 0

    hotspot_networks = _resolve_hotspot_status_networks()
    now_utc = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now_utc)
    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "") or str(
        getattr(user, "phone_number", "") or ""
    )

    repaired = 0
    for device in user.devices or []:
        if not bool(getattr(device, "is_authorized", False)):
            continue

        mac = str(getattr(device, "mac_address", "") or "").strip().upper()
        if not mac:
            continue

        candidate_ips: List[str] = []

        device_ip = str(getattr(device, "ip_address", "") or "").strip()
        if device_ip:
            candidate_ips.append(device_ip)

        if host_usage_map:
            host_ip = str((host_usage_map.get(mac) or {}).get("address") or "").strip()
            if host_ip:
                candidate_ips.append(host_ip)

        if ip_binding_map:
            binding_ip = str((ip_binding_map.get(mac) or {}).get("address") or "").strip()
            if binding_ip:
                candidate_ips.append(binding_ip)

        resolved_ip = None
        for ip_text in candidate_ips:
            if not _is_valid_ip_candidate(ip_text):
                continue
            if not _is_ip_in_hotspot_status_networks(ip_text, hotspot_networks):
                continue
            resolved_ip = ip_text
            break

        if not resolved_ip:
            continue

        existing_ips = dhcp_ips_by_mac.get(mac, set())
        if resolved_ip in existing_ips:
            continue

        # Jangan coba upsert jika IP sudah dipakai MAC lain — ADD akan gagal dengan
        # "already have static lease with this IP address" karena MikroTik tidak mengizinkan
        # dua lease berbeda memiliki IP yang sama.
        if any(resolved_ip in ips for other_mac, ips in dhcp_ips_by_mac.items() if other_mac != mac):
            logger.debug(
                "Policy DHCP self-heal: IP %s sudah dipakai MAC lain di snapshot DHCP — skip user=%s mac=%s",
                resolved_ip,
                user.id,
                mac,
            )
            continue

        ok, msg = upsert_dhcp_static_lease(
            api_connection=api,
            mac_address=mac,
            address=resolved_ip,
            server=dhcp_server_name,
            comment=(
                f"lpsaring|static-dhcp|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source=sync-dhcp-self-heal|date={date_str}|time={time_str}"
            ),
        )
        if ok:
            repaired += 1
            increment_metric("policy.dhcp_self_heal.repaired")
            dhcp_ips_by_mac.setdefault(mac, set()).add(resolved_ip)
        else:
            increment_metric("policy.dhcp_self_heal.failed")
            # IP_CONFLICT: IP sudah dipakai lease lain (snapshot stale) — bukan error kritis.
            if msg.startswith("IP_CONFLICT:"):
                logger.debug(
                    "Policy DHCP self-heal: IP conflict (snapshot stale) user=%s mac=%s ip=%s: %s",
                    user.id,
                    mac,
                    resolved_ip,
                    msg,
                )
            else:
                logger.warning(
                    "Policy DHCP self-heal gagal upsert lease user=%s mac=%s ip=%s: %s",
                    user.id,
                    mac,
                    resolved_ip,
                    msg,
                )

    return repaired


def _apply_auto_debt_limit_block_state(user: User, source: str = "sync_usage") -> bool:
    """Apply auto debt threshold policy and return whether blocked list/profile should be forced.

    Policy:
    - If auto debt >= QUOTA_DEBT_LIMIT_MB: set app blocked with debt-limit reason.
    - If previously auto-debt-blocked and now below limit (or limit disabled): unblock.
    - Unlimited/KOMANDAN are excluded from this threshold enforcement.
    """
    is_auto_blocked = _is_auto_debt_blocked(user)
    before_state = snapshot_user_quota_state(user)

    def _record_policy_transition(action: str, details: dict[str, Any]) -> None:
        append_quota_mutation_event(
            user=user,
            source=f"policy.block_transition:{source}",
            before_state=before_state,
            after_state=snapshot_user_quota_state(user),
            event_details={"action": action, **details},
        )

    if bool(getattr(user, "is_unlimited_user", False)) or getattr(user, "role", None) == UserRole.KOMANDAN:
        if is_auto_blocked:
            user.is_blocked = False
            user.blocked_reason = None
            user.blocked_at = None
            user.blocked_by_id = None
            _record_policy_transition("unblock_auto_debt_exempt", {"reason": "unlimited_or_komandan"})
        # Jaga auto_debt_offset_mb agar raw_debt tidak terakumulasi selama user unlimited/KOMANDAN.
        # Tanpa ini, saat status unlimited dicabut, user tiba-tiba punya debt besar.
        _raw_auto_debt = max(0.0,
            float(getattr(user, "total_quota_used_mb", 0) or 0)
            - float(getattr(user, "total_quota_purchased_mb", 0) or 0)
            - float(getattr(user, "auto_debt_offset_mb", 0) or 0))
        if _raw_auto_debt >= 1.0:
            user.auto_debt_offset_mb = (
                int(getattr(user, "auto_debt_offset_mb", 0) or 0)
                + math.ceil(_raw_auto_debt)
            )
        return False

    limit_mb = float(settings_service.get_setting_as_int("QUOTA_DEBT_LIMIT_MB", 0) or 0)
    if limit_mb <= 0:
        if is_auto_blocked:
            user.is_blocked = False
            user.blocked_reason = None
            user.blocked_at = None
            user.blocked_by_id = None
            _record_policy_transition("unblock_auto_debt_limit_disabled", {"limit_mb": float(limit_mb)})
        return False

    auto_debt_mb = float(_resolve_auto_quota_debt_for_limit(user) or 0.0)
    reached_limit = auto_debt_mb >= limit_mb

    if not reached_limit:
        _send_auto_debt_limit_warning_notification(user, debt_mb=float(auto_debt_mb), limit_mb=float(limit_mb))

    if reached_limit:
        if not bool(getattr(user, "is_blocked", False)):
            user.is_blocked = True
            user.blocked_reason = build_auto_debt_limit_reason(
                debt_mb=auto_debt_mb,
                limit_mb=int(limit_mb),
                source=source,
            )
            if getattr(user, "blocked_at", None) is None:
                user.blocked_at = datetime.now(dt_timezone.utc)
            user.blocked_by_id = None
            _record_policy_transition(
                "block_auto_debt_limit",
                {
                    "debt_mb": float(auto_debt_mb),
                    "limit_mb": float(limit_mb),
                },
            )
            _send_auto_debt_limit_block_notification(user, debt_mb=float(auto_debt_mb), limit_mb=float(limit_mb))
        return True

    if is_auto_blocked:
        user.is_blocked = False
        user.blocked_reason = None
        user.blocked_at = None
        user.blocked_by_id = None
        _record_policy_transition(
            "unblock_auto_debt_below_limit",
            {
                "debt_mb": float(auto_debt_mb),
                "limit_mb": float(limit_mb),
            },
        )
    return False


def _resolve_target_profile(user: User, remaining_mb: float, remaining_percent: float, is_expired: bool) -> str:
    active_profile = (
        settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE", None)
        or settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
        or "default"
    )
    fup_profile = settings_service.get_setting("MIKROTIK_FUP_PROFILE", "fup") or "fup"
    habis_profile = settings_service.get_setting("MIKROTIK_HABIS_PROFILE", "habis") or "habis"
    unlimited_profile = settings_service.get_setting("MIKROTIK_UNLIMITED_PROFILE", "unlimited") or "unlimited"
    expired_profile = settings_service.get_setting("MIKROTIK_EXPIRED_PROFILE", "expired") or "expired"
    fup_threshold_mb = float(settings_service.get_setting_as_int("QUOTA_FUP_THRESHOLD_MB", 3072) or 3072)

    if is_expired:
        return expired_profile
    if user.is_unlimited_user:
        return unlimited_profile
    if (user.total_quota_purchased_mb or 0) <= 0 and not is_expired:
        return habis_profile
    if remaining_mb <= 0:
        return habis_profile
    if float(getattr(user, "total_quota_purchased_mb", 0) or 0) > fup_threshold_mb and remaining_mb <= fup_threshold_mb:
        return fup_profile
    return active_profile


def _update_daily_usage_log(user: User, delta_mb: float, today: date) -> bool:
    if delta_mb <= 0:
        return False

    daily_log = db.session.scalar(
        select(DailyUsageLog).where(DailyUsageLog.user_id == user.id, DailyUsageLog.log_date == today)
    )
    if daily_log:
        daily_log.usage_mb = float(daily_log.usage_mb or 0.0) + float(delta_mb)
    else:
        daily_log = DailyUsageLog()
        daily_log.user_id = user.id
        daily_log.log_date = today
        daily_log.usage_mb = float(delta_mb)
        db.session.add(daily_log)
    return True


def _select_reference_package_for_debt_mb(debt_mb: float) -> Package | None:
    try:
        normalized_debt_mb = float(debt_mb or 0)
    except Exception:
        normalized_debt_mb = 0.0

    if normalized_debt_mb <= 0:
        return None

    reference_packages = (
        db.session.query(Package)
        .filter(Package.is_active.is_(True))
        .filter(Package.data_quota_gb.isnot(None))
        .filter(Package.data_quota_gb > 0)
        .filter(Package.price.isnot(None))
        .filter(Package.price > 0)
        .order_by(Package.data_quota_gb.asc(), Package.price.asc())
        .all()
    )

    if not reference_packages:
        return None

    debt_gb = normalized_debt_mb / 1024.0
    for package in reference_packages:
        try:
            if float(package.data_quota_gb or 0) >= debt_gb:
                return package
        except Exception:
            continue

    return reference_packages[-1]


def _build_auto_debt_limit_notification_payload(user: User, *, debt_mb: float, limit_mb: float) -> Dict[str, str]:
    reference_package = _select_reference_package_for_debt_mb(debt_mb)
    base_package_name = str(getattr(reference_package, "name", "") or "") or "-"
    estimated_debt = estimate_debt_rp_from_cheapest_package(
        debt_mb=float(debt_mb or 0),
        cheapest_package_price_rp=int(getattr(reference_package, "price", 0) or 0) if reference_package else 0,
        cheapest_package_quota_gb=float(getattr(reference_package, "data_quota_gb", 0) or 0) if reference_package else 0,
        cheapest_package_name=base_package_name,
    )
    estimate_rp = estimated_debt.estimated_rp_rounded
    estimate_rp_text = format_rupiah(int(estimate_rp)) if isinstance(estimate_rp, int) else "-"
    debt_mb_text = str(int(round(float(debt_mb or 0))))
    limit_mb_text = str(int(round(float(limit_mb or 0))))

    return {
        "full_name": str(getattr(user, "full_name", "") or "Pengguna"),
        "phone_number": str(getattr(user, "phone_number", "") or "").strip(),
        "debt_mb": debt_mb_text,
        "estimated_rp": estimate_rp_text,
        "base_package_name": base_package_name,
        "limit_mb": limit_mb_text,
    }


def _get_quota_debt_limit_subscribed_admins() -> List[User]:
    recipients_query = (
        select(User)
        .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
        .where(
            NotificationRecipient.notification_type == NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED,
            User.is_active.is_(True),
        )
    )
    return list(db.session.scalars(recipients_query).all())


def _send_auto_debt_limit_admin_notifications(*, user: User, template_key: str, payload: Dict[str, str]) -> None:
    if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
        return

    for admin in _get_quota_debt_limit_subscribed_admins():
        admin_phone = str(getattr(admin, "phone_number", "") or "").strip()
        if not admin_phone:
            continue

        try:
            message = get_notification_message(template_key, payload)
            sent = bool(send_whatsapp_message(admin_phone, message))
            if not sent:
                logger.warning(
                    "Gagal mengirim WA %s ke admin=%s utk user=%s",
                    template_key,
                    getattr(admin, "id", None),
                    getattr(user, "id", None),
                )
        except Exception:
            logger.warning(
                "Exception saat mengirim WA %s ke admin=%s utk user=%s",
                template_key,
                getattr(admin, "id", None),
                getattr(user, "id", None),
                exc_info=True,
            )


def _send_auto_debt_limit_block_notification(user: User, *, debt_mb: float, limit_mb: float) -> None:
    if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
        return

    payload = _build_auto_debt_limit_notification_payload(user, debt_mb=debt_mb, limit_mb=limit_mb)
    phone_number = payload.get("phone_number", "")
    if not phone_number:
        return

    try:
        message = get_notification_message("user_quota_debt_blocked", payload)
        sent = bool(send_whatsapp_message(phone_number, message))
        if not sent:
            logger.warning(
                "Gagal mengirim WA auto debt-limit block untuk user=%s phone=%s debt_mb=%s limit_mb=%s",
                getattr(user, "id", None),
                phone_number,
                payload.get("debt_mb", "0"),
                payload.get("limit_mb", "0"),
            )
    except Exception:
        logger.warning(
            "Exception saat mengirim WA auto debt-limit block untuk user=%s phone=%s",
            getattr(user, "id", None),
            phone_number,
            exc_info=True,
        )

    _send_auto_debt_limit_admin_notifications(user=user, template_key="admin_quota_debt_blocked", payload=payload)


def _get_redis_client():
    try:
        return getattr(current_app, "redis_client_otp", None)
    except Exception:
        return None


def _resolve_auto_debt_warning_threshold(limit_mb: float) -> float:
    try:
        configured_warning_mb = float(settings_service.get_setting_as_int("QUOTA_DEBT_WARNING_MB", 0) or 0)
    except Exception:
        configured_warning_mb = 0.0

    candidate = configured_warning_mb if configured_warning_mb > 0 else math.floor(float(limit_mb or 0) * 0.8)
    upper_bound = max(0.0, float(limit_mb or 0) - 1.0)
    if upper_bound <= 0:
        return 0.0
    return float(min(max(1.0, float(candidate or 0)), upper_bound))


def _send_auto_debt_limit_warning_notification(user: User, *, debt_mb: float, limit_mb: float) -> None:
    if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
        return

    payload = _build_auto_debt_limit_notification_payload(user, debt_mb=debt_mb, limit_mb=limit_mb)
    phone_number = payload.get("phone_number", "")
    if not phone_number:
        return

    warning_threshold = _resolve_auto_debt_warning_threshold(limit_mb)
    if warning_threshold <= 0 or debt_mb < warning_threshold or debt_mb >= limit_mb:
        return

    redis_client = _get_redis_client()
    warning_key = f"limit={int(round(limit_mb))}:warn={int(round(warning_threshold))}"
    if not _should_send_auto_debt_warning_notification(redis_client, user_id=user.id, warning_key=warning_key):
        return

    payload["warning_threshold_mb"] = str(int(round(warning_threshold)))

    try:
        message = get_notification_message("user_quota_debt_warning", payload)
        sent = bool(send_whatsapp_message(phone_number, message))
        if not sent:
            logger.warning(
                "Gagal mengirim WA auto debt-limit warning untuk user=%s phone=%s debt_mb=%s threshold_mb=%s",
                getattr(user, "id", None),
                phone_number,
                payload.get("debt_mb", "0"),
                payload.get("warning_threshold_mb", "0"),
            )
    except Exception:
        logger.warning(
            "Exception saat mengirim WA auto debt-limit warning untuk user=%s phone=%s",
            getattr(user, "id", None),
            phone_number,
            exc_info=True,
        )

    _send_auto_debt_limit_admin_notifications(user=user, template_key="admin_quota_debt_warning", payload=payload)


def _acquire_global_sync_lock(redis_client, ttl_seconds: int = 180) -> tuple[bool, str]:
    """Cegah overlap `sync_hotspot_usage_and_profiles`.

    Tanpa lock global, Celery Beat bisa men-trigger task tiap menit sementara run sebelumnya belum selesai.
    Ini bisa memicu notifikasi WhatsApp status berulang (spam) dan update profile/address-list berulang.
    """
    if redis_client is None:
        increment_metric("hotspot.sync.lock.degraded")
        acquired = _local_global_sync_lock.acquire(blocking=False)
        return acquired, (LOCAL_GLOBAL_SYNC_LOCK_TOKEN if acquired else "")
    try:
        ttl_seconds = int(ttl_seconds)
    except Exception:
        ttl_seconds = 180
    if ttl_seconds <= 0:
        ttl_seconds = 180

    token = str(uuid.uuid4())
    try:
        ok = bool(redis_client.set(REDIS_GLOBAL_SYNC_LOCK_KEY, token, ex=ttl_seconds, nx=True))
    except Exception:
        increment_metric("hotspot.sync.lock.degraded")
        acquired = _local_global_sync_lock.acquire(blocking=False)
        return acquired, (LOCAL_GLOBAL_SYNC_LOCK_TOKEN if acquired else "")
    return ok, token


def _release_global_sync_lock(redis_client, token: str) -> None:
    if token == LOCAL_GLOBAL_SYNC_LOCK_TOKEN:
        try:
            _local_global_sync_lock.release()
        except Exception:
            pass
        return

    if redis_client is None:
        return
    if not token:
        return
    try:
        current_token = redis_client.get(REDIS_GLOBAL_SYNC_LOCK_KEY)
        if isinstance(current_token, (bytes, bytearray)):
            current_token = current_token.decode("utf-8", errors="ignore")
        if str(current_token or "") == str(token):
            redis_client.delete(REDIS_GLOBAL_SYNC_LOCK_KEY)
    except Exception:
        return


def _should_send_access_status_notification(redis_client, *, user_id: uuid.UUID, status_key: str) -> bool:
    """Dedupe notifikasi status akses (FUP/Habis/Expired) untuk mencegah spam.

    Fokus pada idempotensi: jika task overlap/retry, pesan yang sama jangan dikirim berkali-kali.
    """
    if redis_client is None:
        return True
    status = (status_key or "").strip().lower()
    if not status:
        return True

    try:
        ttl_seconds = int(current_app.config.get("WHATSAPP_ACCESS_STATUS_DEDUPE_SECONDS", 6 * 3600))
    except Exception:
        ttl_seconds = 6 * 3600
    if ttl_seconds <= 0:
        return True

    key = f"{REDIS_ACCESS_STATUS_DEDUPE_PREFIX}{status}:{user_id}"
    try:
        return bool(redis_client.set(key, "1", ex=ttl_seconds, nx=True))
    except Exception:
        return True


def _should_send_auto_debt_warning_notification(redis_client, *, user_id: uuid.UUID, warning_key: str) -> bool:
    if redis_client is None:
        return True

    suffix = str(warning_key or "").strip().lower()
    if not suffix:
        return True

    try:
        ttl_seconds = int(current_app.config.get("WHATSAPP_AUTO_DEBT_WARNING_DEDUPE_SECONDS", 6 * 3600))
    except Exception:
        ttl_seconds = 6 * 3600
    if ttl_seconds <= 0:
        return True

    key = f"{REDIS_AUTO_DEBT_WARNING_DEDUPE_PREFIX}{suffix}:{user_id}"
    try:
        return bool(redis_client.set(key, "1", ex=ttl_seconds, nx=True))
    except Exception:
        return True


def _acquire_sync_lock(redis_client, user_id: uuid.UUID, ttl_seconds: int = 60) -> bool:
    lock_key = _get_user_advisory_lock_key(user_id)

    if redis_client is None:
        increment_metric("hotspot.sync.lock.degraded")
        return _try_acquire_db_sync_lock(lock_key)

    key = f"{REDIS_SYNC_LOCK_PREFIX}{user_id}"
    try:
        return bool(redis_client.set(key, "1", ex=ttl_seconds, nx=True))
    except Exception:
        increment_metric("hotspot.sync.lock.degraded")
        return _try_acquire_db_sync_lock(lock_key)


def _release_sync_lock(redis_client, user_id: uuid.UUID) -> None:
    lock_key = _get_user_advisory_lock_key(user_id)

    if redis_client is None:
        _release_db_sync_lock(lock_key)
        return

    key = f"{REDIS_SYNC_LOCK_PREFIX}{user_id}"
    try:
        redis_client.delete(key)
    except Exception:
        pass

    _release_db_sync_lock(lock_key)


def _get_thread_local_db_lock_set() -> set[int]:
    held = getattr(_thread_local_state, "db_sync_lock_keys", None)
    if held is None:
        held = set()
        _thread_local_state.db_sync_lock_keys = held
    return held


def _get_user_advisory_lock_key(user_id: uuid.UUID) -> int:
    try:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return int(user_uuid.int % ((1 << 63) - 1))
    except Exception:
        return abs(hash(str(user_id))) % ((1 << 63) - 1)


def _is_postgresql_engine() -> bool:
    try:
        bind = db.session.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        return str(dialect_name).strip().lower() == "postgresql"
    except Exception:
        return False


def _try_acquire_db_sync_lock(lock_key: int) -> bool:
    if not _is_postgresql_engine():
        return False

    try:
        acquired = bool(db.session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": int(lock_key)}).scalar())
    except Exception:
        return False

    if acquired:
        _get_thread_local_db_lock_set().add(int(lock_key))
    return acquired


def _release_db_sync_lock(lock_key: int) -> None:
    held = _get_thread_local_db_lock_set()
    if int(lock_key) not in held:
        return

    if _is_postgresql_engine():
        try:
            db.session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": int(lock_key)})
        except Exception:
            return

    held.discard(int(lock_key))


def _round_mb_value(value: float) -> float:
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return float(value)


def _send_quota_notifications(user: User, remaining_percent: float, remaining_mb: float) -> None:
    if user.is_unlimited_user:
        return
    if not user.total_quota_purchased_mb or user.total_quota_purchased_mb <= 0:
        return

    template_key = "komandan_quota_low" if user.role == UserRole.KOMANDAN else "user_quota_low"

    # Notifikasi low-quota berbasis sisa kuota (MB). Default: 500MB.
    thresholds = sorted(_get_thresholds_from_env("QUOTA_NOTIFY_REMAINING_MB", [500]), reverse=True)
    thresholds = [t for t in thresholds if isinstance(t, int) and t > 0]
    if not thresholds:
        return
    last_level = user.last_quota_notification_level

    # Backward compatibility: sebelumnya last_level menyimpan persen (<= 100).
    # Jika sekarang threshold berbasis MB (umumnya > 100), reset agar notifikasi bisa jalan lagi.
    if last_level is not None and isinstance(last_level, int) and last_level <= 100 and max(thresholds) > 100:
        last_level = None

    for threshold in thresholds:
        if remaining_mb <= float(threshold) and (last_level is None or last_level > threshold):
            message = get_notification_message(
                template_key,
                {
                    "full_name": user.full_name,
                    "remaining_percent": remaining_percent,
                    "remaining_mb": remaining_mb,
                },
            )
            if send_whatsapp_message(user.phone_number, message):
                user.last_quota_notification_level = threshold
                user.last_low_quota_notif_at = datetime.now(dt_timezone.utc)
            break


def _send_expiry_notifications(user: User) -> None:
    if user.is_unlimited_user:
        return
    if not user.quota_expiry_date:
        return
    if not user.total_quota_purchased_mb or user.total_quota_purchased_mb <= 0:
        return

    template_key = "komandan_quota_expiry_warning" if user.role == UserRole.KOMANDAN else "user_quota_expiry_warning"

    now_local = get_app_local_datetime()
    expiry_local = get_app_local_datetime(user.quota_expiry_date)
    remaining_days = (expiry_local - now_local).days
    if remaining_days < 0:
        return

    thresholds = sorted(_get_thresholds_from_env("QUOTA_EXPIRY_NOTIFY_DAYS", [7, 3, 1]), reverse=True)
    last_level = user.last_expiry_notification_level

    for threshold in thresholds:
        if remaining_days <= threshold and (last_level is None or last_level > threshold):
            message = get_notification_message(
                template_key,
                {
                    "full_name": user.full_name,
                    "remaining_days": threshold,
                },
            )
            if send_whatsapp_message(user.phone_number, message):
                user.last_expiry_notification_level = threshold
                user.last_expiry_notif_at = datetime.now(dt_timezone.utc)
            break


def _send_access_status_notification(
    user: User,
    status_key: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
        return
    if not user.phone_number:
        return

    template_map = {
        "expired": "user_access_expired",
        "fup": "user_access_fup",
        "habis": "user_access_habis",
    }
    template_key = template_map.get(status_key)
    if not template_key:
        return

    redis_client = _get_redis_client()
    if not _should_send_access_status_notification(redis_client, user_id=user.id, status_key=status_key):
        return

    payload = {
        "full_name": user.full_name,
        **(context or {}),
    }
    try:
        message = get_notification_message(template_key, payload)
        send_whatsapp_message(user.phone_number, message)
    except Exception:
        logger.warning("Gagal mengirim notifikasi status '%s' untuk user %s.", status_key, user.id)


def _sync_address_list_status(
    api: object,
    user: User,
    username_08: str,
    remaining_mb: float,
    remaining_percent: float,
    is_expired: bool,
    force_blocked: bool = False,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ip_binding_rows_by_mac: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    enforce_binding_guard: bool = False,
) -> bool:
    if enforce_binding_guard and not _has_policy_binding_for_user(
        user,
        ip_binding_map=ip_binding_map,
        ip_binding_rows_by_mac=ip_binding_rows_by_mac,
    ):
        logger.info(
            "Skip sync address-list by username tanpa ip-binding policy-compatible: user=%s phone=%s",
            getattr(user, "id", None),
            username_08,
        )
        for ip_address in _collect_candidate_ips_for_user(user, ip_binding_map=ip_binding_map, ip_binding_rows_by_mac=ip_binding_rows_by_mac):
            _remove_managed_status_entries_for_ip(api, ip_address)
        return False

    list_active = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active"
    list_fup = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup"
    list_inactive = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
    list_expired = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
    list_habis = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis"
    list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
    list_unauthorized = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized") or "unauthorized"
    fup_threshold_mb = float(settings_service.get_setting_as_int("QUOTA_FUP_THRESHOLD_MB", 3072) or 3072)

    target_list = None
    blocked_for_list = bool(force_blocked or bool(getattr(user, "is_blocked", False)))

    if blocked_for_list:
        target_list = list_blocked
    elif is_expired:
        target_list = list_expired
    elif remaining_mb <= 0 and not user.is_unlimited_user:
        target_list = list_habis
    elif user.is_unlimited_user:
        target_list = list_active
    elif (
        float(getattr(user, "total_quota_purchased_mb", 0) or 0) > fup_threshold_mb and remaining_mb <= fup_threshold_mb
    ):
        target_list = list_fup
    else:
        target_list = list_active

    if blocked_for_list:
        status_value = "blocked"
    elif is_expired:
        status_value = "expired"
    elif user.is_unlimited_user:
        status_value = "unlimited"
    elif remaining_mb <= 0:
        status_value = "habis"
    elif (
        float(getattr(user, "total_quota_purchased_mb", 0) or 0) > fup_threshold_mb and remaining_mb <= fup_threshold_mb
    ):
        status_value = "fup"
    else:
        status_value = "active"
    user_id_raw = getattr(user, "id", None)
    user_uid = str(user_id_raw).strip() if user_id_raw is not None else ""
    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)
    comment = (
        f"lpsaring|status={status_value}|user={username_08}|uid={user_uid or 'unknown'}|role={user.role.value}|date={date_str}|time={time_str}"
    )
    other_lists = [
        name
        for name in (list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked, list_unauthorized)
        if name
    ]
    ok, msg = sync_address_list_for_user(
        api_connection=api,
        username=username_08,
        target_list=target_list,
        other_lists=other_lists or None,
        comment=comment,
    )
    if not ok:
        logger.debug(f"Gagal sync address-list untuk {username_08}: {msg}")
        if msg in ("IP belum tersedia untuk user", "IP tidak ditemukan"):
            ok_binding, binding_map, _msg = get_hotspot_ip_binding_user_map(api)
            if ok_binding:
                user_id_str = user_uid
                fallback_ip = None
                if user_id_str:
                    for entry in binding_map.values():
                        if str(entry.get("user_id")) == user_id_str:
                            ip_address = entry.get("address")
                            if ip_address:
                                fallback_ip = str(ip_address)
                                break
                if not fallback_ip and user_id_raw is not None:
                    device_macs = db.session.scalars(
                        select(UserDevice.mac_address)
                        .where(
                            UserDevice.user_id == user_id_raw,
                            UserDevice.is_authorized.is_(True),
                        )
                        .order_by(UserDevice.last_seen_at.desc())
                    ).all()
                    for mac in device_macs:
                        if not mac:
                            continue
                        entry = binding_map.get(str(mac).upper())
                        if entry and entry.get("address"):
                            fallback_ip = str(entry.get("address"))
                            break
                        ok_ip, ip_from_mac, _ip_msg = get_ip_by_mac(api, str(mac).upper())
                        if ok_ip and ip_from_mac:
                            fallback_ip = str(ip_from_mac)
                            break
                if fallback_ip:
                    return _sync_address_list_status_for_ip(
                        api,
                        user,
                        fallback_ip,
                        remaining_mb,
                        remaining_percent,
                        is_expired,
                        force_blocked=force_blocked,
                        ip_binding_map=ip_binding_map,
                        ip_binding_rows_by_mac=ip_binding_rows_by_mac,
                        enforce_binding_guard=enforce_binding_guard,
                    )
        return False
    return ok


def _sync_address_list_status_for_ip(
    api: object,
    user: User,
    ip_address: str,
    remaining_mb: float,
    remaining_percent: float,
    is_expired: bool,
    force_blocked: bool = False,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ip_binding_rows_by_mac: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    enforce_binding_guard: bool = False,
) -> bool:
    if not ip_address:
        return False

    hotspot_networks = _resolve_hotspot_status_networks()
    if not _is_ip_in_hotspot_status_networks(ip_address, hotspot_networks):
        logger.info("Skip sync address-list untuk IP di luar hotspot CIDR: user=%s ip=%s", user.id, ip_address)
        return False

    if enforce_binding_guard and not _has_policy_binding_for_user(
        user,
        ip_binding_map=ip_binding_map,
        ip_binding_rows_by_mac=ip_binding_rows_by_mac,
    ):
        _remove_managed_status_entries_for_ip(api, ip_address)
        logger.info(
            "Prune stale status-list (tanpa ip-binding policy-compatible): user=%s ip=%s",
            getattr(user, "id", None),
            ip_address,
        )
        return False

    list_active = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active"
    list_fup = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup"
    list_inactive = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
    list_expired = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
    list_habis = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis"
    list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
    list_unauthorized = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized") or "unauthorized"
    fup_threshold_mb = float(settings_service.get_setting_as_int("QUOTA_FUP_THRESHOLD_MB", 3072) or 3072)

    target_list = None
    blocked_for_list = bool(force_blocked or bool(getattr(user, "is_blocked", False)))

    if blocked_for_list:
        target_list = list_blocked
    elif is_expired:
        target_list = list_expired
    elif remaining_mb <= 0 and not user.is_unlimited_user:
        target_list = list_habis
    elif user.is_unlimited_user:
        target_list = list_active
    elif (
        float(getattr(user, "total_quota_purchased_mb", 0) or 0) > fup_threshold_mb and remaining_mb <= fup_threshold_mb
    ):
        target_list = list_fup
    else:
        target_list = list_active

    username_08 = format_to_local_phone(user.phone_number)
    if blocked_for_list:
        status_value = "blocked"
    elif is_expired:
        status_value = "expired"
    elif user.is_unlimited_user:
        status_value = "unlimited"
    elif remaining_mb <= 0:
        status_value = "habis"
    elif (
        float(getattr(user, "total_quota_purchased_mb", 0) or 0) > fup_threshold_mb and remaining_mb <= fup_threshold_mb
    ):
        status_value = "fup"
    else:
        status_value = "active"
    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)
    user_id_raw = getattr(user, "id", None)
    user_uid = str(user_id_raw).strip() if user_id_raw is not None else ""
    comment = (
        f"lpsaring|status={status_value}"
        f"|user={username_08}"
        f"|uid={user_uid or 'unknown'}"
        f"|role={user.role.value}"
        f"|ip={ip_address}"
        f"|date={date_str}"
        f"|time={time_str}"
    )

    if not target_list:
        return False

    ok, msg = upsert_address_list_entry(api_connection=api, address=ip_address, list_name=target_list, comment=comment)
    if not ok:
        logger.debug(f"Gagal upsert address-list untuk IP {ip_address}: {msg}")
        return False

    for list_name in [list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked]:
        if list_name and list_name != target_list:
            remove_address_list_entry(api_connection=api, address=ip_address, list_name=list_name)

    # Source-level guard: status-managed IP must never remain in unauthorized list.
    if list_unauthorized and list_unauthorized != target_list:
        remove_address_list_entry(api_connection=api, address=ip_address, list_name=list_unauthorized)

    return True


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _update_device_usage_baseline(
    *,
    device: UserDevice,
    now: datetime,
    bytes_total: int,
    host_id: Optional[str],
    uptime_seconds: Optional[int],
    redis_client,
    redis_key: str,
) -> None:
    device.last_bytes_total = int(bytes_total)
    device.last_bytes_updated_at = now
    device.last_hotspot_host_id = host_id
    device.last_hotspot_uptime_seconds = uptime_seconds

    if redis_client is not None:
        try:
            redis_client.set(redis_key, bytes_total)
        except Exception:
            pass


def _serialize_usage_device_delta(item: HotspotUsageDeviceDelta) -> Dict[str, Any]:
    return {
        "mac_address": item.mac_address,
        "ip_address": item.ip_address,
        "label": item.label,
        "delta_mb": _round_mb_value(item.delta_mb),
        "previous_bytes_total": int(item.previous_bytes_total),
        "bytes_total": int(item.bytes_total),
        "host_id": item.host_id,
        "uptime_seconds": item.uptime_seconds,
        "source_address": item.source_address,
        "to_address": item.to_address,
    }


def _serialize_usage_rebaseline_event(item: HotspotUsageRebaselineEvent) -> Dict[str, Any]:
    return {
        "mac_address": item.mac_address,
        "ip_address": item.ip_address,
        "label": item.label,
        "reason": item.reason,
        "previous_bytes_total": item.previous_bytes_total,
        "bytes_total": int(item.bytes_total),
        "previous_host_id": item.previous_host_id,
        "host_id": item.host_id,
        "previous_uptime_seconds": item.previous_uptime_seconds,
        "uptime_seconds": item.uptime_seconds,
        "source_address": item.source_address,
        "to_address": item.to_address,
    }


def _sum_host_usage_for_user(user: User, host_usage_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, int]]:
    if not user.devices:
        return None
    total_in = 0
    total_out = 0
    found = False
    for device in user.devices:
        mac = (device.mac_address or "").upper()
        if not mac:
            continue
        host_usage = host_usage_map.get(mac)
        if not host_usage:
            continue
        total_in += int(host_usage.get("bytes_in", 0))
        total_out += int(host_usage.get("bytes_out", 0))
        found = True
    if not found:
        return None
    return {"bytes_in": total_in, "bytes_out": total_out}


def _calculate_usage_update(
    user: User,
    host_usage_map: Dict[str, Dict[str, Any]],
    redis_client,
) -> Optional[HotspotUsageUpdateResult]:
    if not user.devices:
        return None

    old_usage_mb = float(user.total_quota_used_mb or 0.0)

    delta_bytes = 0
    found = False
    now = datetime.now(dt_timezone.utc)
    device_deltas: List[HotspotUsageDeviceDelta] = []
    rebaseline_events: List[HotspotUsageRebaselineEvent] = []

    for device in user.devices:
        mac = (device.mac_address or "").upper()
        if not mac:
            continue

        host_usage = host_usage_map.get(mac)
        if not host_usage:
            continue

        bytes_total = int(host_usage.get("bytes_in", 0)) + int(host_usage.get("bytes_out", 0))
        host_id = str(host_usage.get("host_id") or "").strip() or None
        uptime_seconds = _safe_int(host_usage.get("uptime_seconds"))
        found = True

        key = f"{REDIS_LAST_BYTES_PREFIX}{mac}"
        redis_last_bytes = None
        has_key = False
        if redis_client is not None:
            try:
                has_key = bool(redis_client.exists(key))
            except Exception:
                has_key = True
            if has_key:
                try:
                    redis_last_bytes = int(redis_client.get(key) or 0)
                except Exception:
                    redis_last_bytes = 0

        db_last_bytes = int(device.last_bytes_total) if device.last_bytes_total is not None else None
        if redis_last_bytes is not None and db_last_bytes is not None:
            last_bytes = max(redis_last_bytes, db_last_bytes)
        elif redis_last_bytes is not None:
            last_bytes = redis_last_bytes
        else:
            last_bytes = db_last_bytes

        if last_bytes is None:
            _update_device_usage_baseline(
                device=device,
                now=now,
                bytes_total=bytes_total,
                host_id=host_id,
                uptime_seconds=uptime_seconds,
                redis_client=redis_client,
                redis_key=key,
            )
            continue

        previous_host_id = str(getattr(device, "last_hotspot_host_id", "") or "").strip() or None
        previous_uptime_seconds = _safe_int(getattr(device, "last_hotspot_uptime_seconds", None))

        rebaseline_reasons: List[str] = []
        if host_id and previous_host_id and host_id != previous_host_id:
            rebaseline_reasons.append("host_row_changed")
        if (
            previous_uptime_seconds is not None
            and uptime_seconds is not None
            and uptime_seconds + 5 < previous_uptime_seconds
        ):
            rebaseline_reasons.append("uptime_regressed")
        if bytes_total < last_bytes:
            rebaseline_reasons.append("counter_regressed")

        if rebaseline_reasons:
            rebaseline_events.append(
                HotspotUsageRebaselineEvent(
                    mac_address=mac,
                    ip_address=str(getattr(device, "ip_address", "") or "").strip() or None,
                    label=str(getattr(device, "label", "") or "").strip() or None,
                    reason="+".join(rebaseline_reasons),
                    previous_bytes_total=int(last_bytes),
                    bytes_total=int(bytes_total),
                    previous_host_id=previous_host_id,
                    host_id=host_id,
                    previous_uptime_seconds=previous_uptime_seconds,
                    uptime_seconds=uptime_seconds,
                    source_address=str(host_usage.get("source_address") or "").strip() or None,
                    to_address=str(host_usage.get("to_address") or "").strip() or None,
                )
            )
            _update_device_usage_baseline(
                device=device,
                now=now,
                bytes_total=bytes_total,
                host_id=host_id,
                uptime_seconds=uptime_seconds,
                redis_client=redis_client,
                redis_key=key,
            )
            continue

        current_delta_bytes = max(0, int(bytes_total - last_bytes))
        delta_bytes += current_delta_bytes
        if current_delta_bytes > 0:
            device_deltas.append(
                HotspotUsageDeviceDelta(
                    mac_address=mac,
                    ip_address=str(getattr(device, "ip_address", "") or "").strip() or None,
                    label=str(getattr(device, "label", "") or "").strip() or None,
                    delta_mb=current_delta_bytes / BYTES_PER_MB,
                    previous_bytes_total=int(last_bytes),
                    bytes_total=int(bytes_total),
                    host_id=host_id,
                    uptime_seconds=uptime_seconds,
                    source_address=str(host_usage.get("source_address") or "").strip() or None,
                    to_address=str(host_usage.get("to_address") or "").strip() or None,
                )
            )

        _update_device_usage_baseline(
            device=device,
            now=now,
            bytes_total=bytes_total,
            host_id=host_id,
            uptime_seconds=uptime_seconds,
            redis_client=redis_client,
            redis_key=key,
        )

    if not found:
        return None

    delta_mb = delta_bytes / BYTES_PER_MB
    new_total_mb = old_usage_mb + delta_mb
    return HotspotUsageUpdateResult(
        delta_mb=_round_mb_value(delta_mb),
        new_total_usage_mb=_round_mb_value(new_total_mb),
        device_deltas=device_deltas,
        rebaseline_events=rebaseline_events,
    )


def _auto_enroll_devices_from_ip_binding(
    user: User,
    ip_binding_map: Dict[str, Dict[str, Any]],
    host_usage_map: Dict[str, Dict[str, Any]],
    max_enroll: int,
    debug_log: bool = False,
) -> int:
    if not ip_binding_map:
        return 0
    existing_macs = {((d.mac_address or "").upper()) for d in (user.devices or [])}
    added = 0
    for mac, entry in ip_binding_map.items():
        if entry.get("user_id") != str(user.id):
            continue
        if mac in existing_macs:
            continue
        ip_address = entry.get("address") or host_usage_map.get(mac, {}).get("address")
        ok, msg, device = register_or_update_device(user, ip_address, None, client_mac=mac)
        if debug_log:
            logger.info(
                "Auto-enroll debug: user_id=%s mac=%s ip=%s ok=%s msg=%s",
                user.id,
                mac,
                ip_address,
                ok,
                msg,
            )
        if ok and device is not None:
            added += 1
            existing_macs.add(mac)
        if added >= max_enroll:
            break
    return added


def sync_hotspot_usage_and_profiles() -> Dict[str, int]:
    counters = {
        "processed": 0,
        "updated_usage": 0,
        "profile_updates": 0,
        "binding_self_healed": 0,
        "dhcp_self_healed": 0,
        "failed": 0,
    }
    auto_enroll_users = 0
    auto_enroll_devices = 0

    db_state = _load_hotspot_usage_sync_db_state()
    user_ids = db_state.user_ids

    if not user_ids:
        return counters

    runtime_settings = _load_hotspot_usage_sync_runtime_settings()

    today = get_app_local_datetime().date()
    redis_client = _get_redis_client()

    # Lock global untuk mencegah overlap antar-run.
    # NOTE: ttl diset konservatif; kalau run panjang, Beat akan skip run berikutnya.
    lock_ttl = int(current_app.config.get("QUOTA_SYNC_GLOBAL_LOCK_SECONDS", 180) or 180)
    global_lock_ok, global_lock_token = _acquire_global_sync_lock(redis_client, ttl_seconds=lock_ttl)
    if not global_lock_ok:
        logger.info("Skip sync_hotspot_usage_and_profiles: global lock active")
        return counters

    try:
        with get_mikrotik_connection() as api:
            if not api:
                logger.error("Gagal mendapatkan koneksi MikroTik untuk sinkronisasi kuota.")
                counters["failed"] = len(user_ids)
                return counters

            ok_host, host_usage_map, host_msg = get_hotspot_host_usage_map(api)
            if not ok_host:
                logger.error(f"Gagal mengambil data host Mikrotik: {host_msg}")
                counters["failed"] = len(user_ids)
                return counters

            ip_binding_map: Dict[str, Dict[str, Any]] = {}
            ok_binding_map, binding_map, binding_msg = get_hotspot_ip_binding_user_map(api)
            if ok_binding_map:
                ip_binding_map = binding_map
            else:
                logger.warning(f"Gagal mengambil data ip-binding Mikrotik: {binding_msg}")

            ok_binding_rows, ip_binding_rows_by_mac = _snapshot_ip_binding_rows_by_mac(api)
            if not ok_binding_rows:
                logger.warning("Binding guard dinonaktifkan sementara karena snapshot ip-binding raw gagal.")
            binding_guard_enabled = bool(ok_binding_rows)

            ok_dhcp_snapshot, dhcp_ips_by_mac_snapshot = _snapshot_dhcp_ips_by_mac(api)
            dhcp_ips_by_mac: Optional[Dict[str, set[str]]] = dhcp_ips_by_mac_snapshot if ok_dhcp_snapshot else None
            if not ok_dhcp_snapshot:
                logger.warning("Policy DHCP self-heal dinonaktifkan sementara karena snapshot DHCP lease raw gagal.")

            if runtime_settings.auto_enroll_devices_from_ip_binding:
                if not ip_binding_map and ok_binding_map:
                    ip_binding_map = binding_map

            for user_id in user_ids:
                lock_acquired = False
                try:
                    with db.session.begin():
                        user = _load_hotspot_sync_user(user_id)
                        if user is None:
                            continue

                        if _is_demo_user(user):
                            continue

                        if not _acquire_sync_lock(redis_client, user_id):
                            continue
                        lock_acquired = True

                        username_08 = format_to_local_phone(user.phone_number)
                        if not username_08:
                            continue

                        if ip_binding_map:
                            max_devices = runtime_settings.max_devices_per_user
                            existing_devices = len(user.devices or [])
                            available_slots = max(0, max_devices - existing_devices)
                            if available_slots > 0:
                                added_devices = _auto_enroll_devices_from_ip_binding(
                                    user,
                                    ip_binding_map,
                                    host_usage_map,
                                    available_slots,
                                    runtime_settings.auto_enroll_debug_log,
                                )
                                if added_devices > 0:
                                    auto_enroll_users += 1
                                    auto_enroll_devices += added_devices

                        usage_update = _calculate_usage_update(user, host_usage_map, redis_client)
                        old_usage_mb = float(user.total_quota_used_mb or 0.0)
                        if usage_update:
                            delta_mb = float(usage_update.delta_mb or 0.0)
                            new_total_usage_mb = float(usage_update.new_total_usage_mb or old_usage_mb)
                            _update_daily_usage_log(user, delta_mb, today)

                            if usage_update.rebaseline_events:
                                rebaseline_state = snapshot_user_quota_state(user)
                                append_quota_mutation_event(
                                    user=user,
                                    source="hotspot.sync_rebaseline",
                                    before_state=rebaseline_state,
                                    after_state=rebaseline_state,
                                    event_details={
                                        "rebaseline_events": [
                                            _serialize_usage_rebaseline_event(item)
                                            for item in usage_update.rebaseline_events
                                        ],
                                    },
                                )

                            # Jangan update total_quota_used_mb untuk unlimited users.
                            # Daily log tetap dicatat di atas untuk keperluan grafik pemakaian.
                            if (
                                not bool(getattr(user, "is_unlimited_user", False))
                                and abs(new_total_usage_mb - old_usage_mb) >= 0.01
                            ):
                                lock_user_quota_row(user)
                                before_state = snapshot_user_quota_state(user)
                                user.total_quota_used_mb = new_total_usage_mb
                                counters["updated_usage"] += 1
                                append_quota_mutation_event(
                                    user=user,
                                    source="hotspot.sync_usage",
                                    before_state=before_state,
                                    after_state=snapshot_user_quota_state(user),
                                    idempotency_key=(f"sync_usage:{user_id}:{today.isoformat()}:{round(new_total_usage_mb,2)}")[:128],
                                    event_details={
                                        "delta_mb": float(round(delta_mb, 2)),
                                        "new_total_usage_mb": float(round(new_total_usage_mb, 2)),
                                        "device_deltas": [
                                            _serialize_usage_device_delta(item)
                                            for item in usage_update.device_deltas
                                        ],
                                    },
                                )

                        remaining_mb, remaining_percent = _calculate_remaining(user)

                        force_blocked_status = _apply_auto_debt_limit_block_state(user, source="sync_usage")
                        blocked_profile = runtime_settings.blocked_profile

                        # Quota-debt hard block is NOT applied to:
                        # - unlimited users
                        # - KOMANDAN role
                        if (
                            bool(getattr(user, "is_unlimited_user", False))
                            or getattr(user, "role", None) == UserRole.KOMANDAN
                        ):
                            now_local = get_app_local_datetime()
                            expiry_local = (
                                get_app_local_datetime(user.quota_expiry_date) if user.quota_expiry_date else None
                            )
                            is_expired = bool(expiry_local and expiry_local < now_local)
                            target_profile = _resolve_target_profile(user, remaining_mb, remaining_percent, is_expired)

                        else:
                            now_local = get_app_local_datetime()
                            expiry_local = (
                                get_app_local_datetime(user.quota_expiry_date) if user.quota_expiry_date else None
                            )
                            is_expired = bool(expiry_local and expiry_local < now_local)
                            target_profile = _resolve_target_profile(user, remaining_mb, remaining_percent, is_expired)

                        if bool(getattr(user, "is_blocked", False)):
                            target_profile = blocked_profile
                            if _is_auto_debt_blocked(user):
                                force_blocked_status = True

                        healed_count = _self_heal_policy_binding_for_user(
                            api,
                            user,
                            ip_binding_map=ip_binding_map,
                            host_usage_map=host_usage_map,
                        )
                        if healed_count > 0:
                            counters["binding_self_healed"] += healed_count

                        dhcp_healed_count = _self_heal_policy_dhcp_for_user(
                            api,
                            user,
                            host_usage_map=host_usage_map,
                            ip_binding_map=ip_binding_map,
                            dhcp_ips_by_mac=dhcp_ips_by_mac,
                        )
                        if dhcp_healed_count > 0:
                            counters["dhcp_self_healed"] += dhcp_healed_count

                        _emit_policy_binding_mismatch_metrics(user, ip_binding_map)

                        if target_profile and user.mikrotik_profile_name != target_profile:
                            success_profile, message = set_hotspot_user_profile(
                                api_connection=api, username_or_id=username_08, new_profile_name=target_profile
                            )
                            if success_profile:
                                user.mikrotik_profile_name = target_profile
                                counters["profile_updates"] += 1
                                status_key = None
                                if target_profile == runtime_settings.expired_profile:
                                    status_key = "expired"
                                elif target_profile == runtime_settings.habis_profile:
                                    status_key = "habis"
                                elif target_profile == runtime_settings.fup_profile:
                                    status_key = "fup"

                                if status_key:
                                    expiry_date = None
                                    if user.quota_expiry_date:
                                        exp_date_str, exp_time_str = get_app_date_time_strings(user.quota_expiry_date)
                                        expiry_date = f"{exp_date_str} {exp_time_str}".strip()
                                    _send_access_status_notification(
                                        user,
                                        status_key,
                                        {
                                            "remaining_mb": remaining_mb,
                                            "remaining_percent": remaining_percent,
                                            "expiry_date": expiry_date or "-",
                                        },
                                    )
                            else:
                                logger.warning(f"Gagal update profil Mikrotik {username_08}: {message}")

                        # Sinkronkan address-list untuk semua IP yang terdeteksi (multi-device/IP).
                        candidate_ips = _collect_candidate_ips_for_user(
                            user,
                            host_usage_map=host_usage_map,
                            ip_binding_map=ip_binding_map,
                            ip_binding_rows_by_mac=ip_binding_rows_by_mac,
                        )
                        ok_any_ip = False
                        for ip_address in candidate_ips:
                            if _sync_address_list_status_for_ip(
                                api,
                                user,
                                ip_address,
                                remaining_mb,
                                remaining_percent,
                                is_expired,
                                force_blocked=force_blocked_status,
                                ip_binding_map=ip_binding_map,
                                ip_binding_rows_by_mac=ip_binding_rows_by_mac,
                                enforce_binding_guard=binding_guard_enabled,
                            ):
                                ok_any_ip = True

                        _prune_stale_status_entries_for_user(api, user, keep_ips=candidate_ips)

                        # Fallback: gunakan resolusi IP by-username (active/host) bila belum ada IP yang valid.
                        if not ok_any_ip:
                            _sync_address_list_status(
                                api,
                                user,
                                username_08,
                                remaining_mb,
                                remaining_percent,
                                is_expired,
                                force_blocked=force_blocked_status,
                                ip_binding_map=ip_binding_map,
                                ip_binding_rows_by_mac=ip_binding_rows_by_mac,
                                enforce_binding_guard=binding_guard_enabled,
                            )

                        if runtime_settings.whatsapp_notifications_enabled:
                            _send_quota_notifications(user, remaining_percent, remaining_mb)
                            _send_expiry_notifications(user)

                        counters["processed"] += 1
                except Exception as e:
                    logger.error("Error sinkronisasi user %s: %s", user_id, e, exc_info=True)
                    counters["failed"] += 1
                finally:
                    db.session.remove()
                    if lock_acquired:
                        _release_sync_lock(redis_client, user_id)

        if auto_enroll_devices > 0:
            logger.info(
                "Auto-enroll ringkas: users=%s devices=%s",
                auto_enroll_users,
                auto_enroll_devices,
            )

        return counters
    finally:
        _release_global_sync_lock(redis_client, global_lock_token)


def sync_address_list_for_single_user(user: User, client_ip: Optional[str] = None, api_connection: Optional[Any] = None) -> bool:
    """Sync address-list status for a single user based on DB counters.

    Pass ``api_connection`` to reuse an already-open MikroTik connection
    instead of opening a new one (avoids nested connections during webhook
    processing, which contributes to >120 s operation times).
    """
    if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return False
    if _is_demo_user(user):
        return False

    username_08 = format_to_local_phone(user.phone_number)
    if not username_08:
        return False

    remaining_mb, remaining_percent = _calculate_remaining(user)
    now_local = get_app_local_datetime()
    expiry_local = get_app_local_datetime(user.quota_expiry_date) if user.quota_expiry_date else None
    is_expired = bool(expiry_local and expiry_local < now_local)
    force_blocked_status = _apply_auto_debt_limit_block_state(user, source="sync_single")

    _ctx = nullcontext(api_connection) if api_connection is not None else get_mikrotik_connection()
    with _ctx as api:
        if not api:
            logger.warning("Gagal konek MikroTik untuk sync address-list single user")
            return False

        ok_binding_map, ip_binding_map, _binding_msg = get_hotspot_ip_binding_user_map(api)
        if not ok_binding_map:
            ip_binding_map = {}

        ok_host_map, host_usage_map, _host_msg = get_hotspot_host_usage_map(api)
        if not ok_host_map:
            host_usage_map = {}

        ok_binding_rows, ip_binding_rows_by_mac = _snapshot_ip_binding_rows_by_mac(api)
        binding_guard_enabled = bool(ok_binding_rows)

        ok_any_ip = False
        ips: List[str] = []
        hotspot_networks = _resolve_hotspot_status_networks()

        if client_ip and _is_ip_in_hotspot_status_networks(client_ip, hotspot_networks):
            ips.append(str(client_ip).strip())

        for ip_address in _collect_candidate_ips_for_user(
            user,
            host_usage_map=host_usage_map,
            ip_binding_map=ip_binding_map,
            ip_binding_rows_by_mac=ip_binding_rows_by_mac,
        ):
            if ip_address not in ips:
                ips.append(ip_address)

        for ip_address in ips:
            if _sync_address_list_status_for_ip(
                api,
                user,
                ip_address,
                remaining_mb,
                remaining_percent,
                is_expired,
                force_blocked=force_blocked_status,
                ip_binding_map=ip_binding_map,
                ip_binding_rows_by_mac=ip_binding_rows_by_mac,
                enforce_binding_guard=binding_guard_enabled,
            ):
                ok_any_ip = True

        _prune_stale_status_entries_for_user(api, user, keep_ips=ips)

        ok_user_ip = _sync_address_list_status(
            api,
            user,
            username_08,
            remaining_mb,
            remaining_percent,
            is_expired,
            force_blocked=force_blocked_status,
            ip_binding_map=ip_binding_map,
            ip_binding_rows_by_mac=ip_binding_rows_by_mac,
            enforce_binding_guard=binding_guard_enabled,
        )
        return bool(ok_any_ip or ok_user_ip)


def resolve_target_profile_for_user(user: User) -> str:
    """Resolve MikroTik profile for a single user using the same rules as the periodic sync.

    This is used by actions like quota injection so profile changes (ex: leaving FUP) can be applied immediately.
    """
    _apply_auto_debt_limit_block_state(user, source="resolve_profile")
    remaining_mb, remaining_percent = _calculate_remaining(user)
    if bool(getattr(user, "is_blocked", False)):
        return settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"
    now_local = get_app_local_datetime()
    expiry_local = get_app_local_datetime(user.quota_expiry_date) if user.quota_expiry_date else None
    is_expired = bool(expiry_local and expiry_local < now_local)
    return _resolve_target_profile(user, remaining_mb, remaining_percent, is_expired)


def _log_system_cleanup_action(user: "User", reason: str, action: str) -> None:
    """Catat aksi cleanup sistem ke AdminActionLog (admin_id=None = system action)."""
    try:
        action_type_map = {
            "hard_delete": AdminActionType.MANUAL_USER_DELETE,
            "deactivate": AdminActionType.DEACTIVATE_USER,
            "unapproved_delete": AdminActionType.REJECT_USER,
        }
        action_type = action_type_map.get(action, AdminActionType.DEACTIVATE_USER)
        log_entry = AdminActionLog()
        log_entry.admin_id = None
        log_entry.target_user_id = user.id
        log_entry.action_type = action_type
        log_entry.details = str({
                "source": "cleanup_inactive_users (system)",
                "action": action,
                "reason": reason,
                "user_phone": user.phone_number,
                "user_name": user.full_name,
            })
        db.session.add(log_entry)
    except Exception as e:
        current_app.logger.warning("cleanup: gagal catat audit log untuk user %s: %s", user.phone_number, e)


def cleanup_inactive_users() -> Dict[str, int]:
    """Bersihkan user tidak aktif berdasarkan criteria kuota + waktu login.

    'Tidak aktif' = quota_expiry_date sudah habis (atau tidak pernah punya kuota)
                    DAN last_login_at melebihi threshold.

    User dengan quota_expiry_date di masa depan TIDAK akan disentuh,
    meskipun tidak pernah login ke portal — mereka masih pelanggan aktif.
    """
    counters = {
        "deleted": 0,
        "deactivated": 0,
        "delete_skipped_guard": 0,
        "delete_skipped_active_quota": 0,
        "unapproved_deleted": 0,
    }
    now_utc = datetime.now(dt_timezone.utc)

    deactivate_enabled = settings_service.get_setting_as_bool("INACTIVE_DEACTIVATE_ENABLED", False)
    deactivate_days = settings_service.get_setting_as_int("INACTIVE_DEACTIVATE_DAYS", 45)
    delete_enabled = settings_service.get_setting_as_bool("INACTIVE_AUTO_DELETE_ENABLED", False)
    delete_days = settings_service.get_setting_as_int("INACTIVE_DELETE_DAYS", 90)
    # Safety cap: default 5 agar tidak hapus massal sekaligus
    delete_max_per_run = settings_service.get_setting_as_int("INACTIVE_DELETE_MAX_PER_RUN", 5)
    unapproved_delete_days = settings_service.get_setting_as_int("UNAPPROVED_AUTO_DELETE_DAYS", 30)

    if not delete_enabled:
        current_app.logger.info(
            "cleanup_inactive_users: hard delete dinonaktifkan (INACTIVE_AUTO_DELETE_ENABLED=False)."
        )
    if not deactivate_enabled:
        current_app.logger.info(
            "cleanup_inactive_users: deactivate dinonaktifkan (INACTIVE_DEACTIVATE_ENABLED=False)."
        )

    # --- BAGIAN 1: User approved (USER/KOMANDAN) ---
    users = db.session.scalars(
        select(User).where(
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
            User.approval_status == ApprovalStatus.APPROVED,
        )
    ).all()

    with get_mikrotik_connection() as api:
        for user in users:
            last_activity = user.last_login_at or user.created_at
            if not last_activity:
                continue

            days_inactive = (now_utc - last_activity).days
            username_08 = format_to_local_phone(user.phone_number)

            # Guard utama: jangan sentuh user yang masih punya kuota aktif
            has_active_quota = (
                user.quota_expiry_date is not None
                and user.quota_expiry_date > now_utc
            )

            # --- Path: HARD DELETE ---
            if days_inactive >= delete_days:
                if has_active_quota:
                    counters["delete_skipped_active_quota"] += 1
                    current_app.logger.info(
                        "cleanup_inactive: SKIP delete %s — kuota masih aktif hingga %s (inactive %d hari)",
                        user.phone_number, user.quota_expiry_date, days_inactive,
                    )
                    continue

                can_delete = delete_enabled and (
                    delete_max_per_run <= 0 or counters["deleted"] < delete_max_per_run
                )
                if can_delete:
                    devices = db.session.scalars(
                        select(UserDevice).where(UserDevice.user_id == user.id)
                    ).all()
                    for device in devices:
                        if device.mac_address:
                            _remove_ip_binding(device.mac_address, user.mikrotik_server_name or "all", api_connection=api)
                        if device.ip_address:
                            _remove_managed_status_entries_for_ip(api, device.ip_address)
                        db.session.delete(device)
                    if api and username_08:
                        delete_hotspot_user(api_connection=api, username=username_08)
                    current_app.logger.warning(
                        "cleanup_inactive: HARD DELETE %s (phone=%s, inactive=%d hari, quota_expiry=%s)",
                        user.full_name, user.phone_number, days_inactive, user.quota_expiry_date,
                    )
                    _log_system_cleanup_action(
                        user,
                        reason=f"Tidak aktif {days_inactive} hari, kuota habis sejak {user.quota_expiry_date}",
                        action="hard_delete",
                    )
                    db.session.delete(user)
                    counters["deleted"] += 1
                    continue

                counters["delete_skipped_guard"] += 1
                continue

            # --- Path: DEACTIVATE (soft) ---
            if deactivate_enabled and user.is_active and days_inactive >= deactivate_days:
                if has_active_quota:
                    continue

                devices = db.session.scalars(
                    select(UserDevice).where(UserDevice.user_id == user.id)
                ).all()
                for device in devices:
                    if device.mac_address:
                        _remove_ip_binding(device.mac_address, user.mikrotik_server_name or "all", api_connection=api)
                    if device.ip_address:
                        _remove_managed_status_entries_for_ip(api, device.ip_address)
                if api and username_08:
                    delete_hotspot_user(api_connection=api, username=username_08)
                current_app.logger.info(
                    "cleanup_inactive: DEACTIVATE %s (phone=%s, inactive=%d hari)",
                    user.full_name, user.phone_number, days_inactive,
                )
                _log_system_cleanup_action(
                    user,
                    reason=f"Tidak aktif {days_inactive} hari, kuota habis/kosong",
                    action="deactivate",
                )
                user.is_active = False
                user.mikrotik_user_exists = False
                counters["deactivated"] += 1

    # --- BAGIAN 2: User belum di-approve terlalu lama ---
    if unapproved_delete_days > 0:
        cutoff = now_utc - timedelta(days=unapproved_delete_days)
        unapproved_users = db.session.scalars(
            select(User).where(
                User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
                User.approval_status == ApprovalStatus.PENDING_APPROVAL,
                User.created_at < cutoff,
            )
        ).all()

        with get_mikrotik_connection() as api2:
            for user in unapproved_users:
                username_08 = format_to_local_phone(user.phone_number)
                devices = db.session.scalars(
                    select(UserDevice).where(UserDevice.user_id == user.id)
                ).all()
                for device in devices:
                    if device.mac_address:
                        _remove_ip_binding(device.mac_address, user.mikrotik_server_name or "all", api_connection=api2)
                    if device.ip_address:
                        _remove_managed_status_entries_for_ip(api2, device.ip_address)
                    db.session.delete(device)
                if api2 and username_08:
                    delete_hotspot_user(api_connection=api2, username=username_08)
                days_pending = (now_utc - user.created_at).days if user.created_at else 0
                current_app.logger.warning(
                    "cleanup_unapproved: DELETE %s (phone=%s, status=%s, %d hari sejak daftar)",
                    user.full_name, user.phone_number, user.approval_status.value, days_pending,
                )
                _log_system_cleanup_action(
                    user,
                    reason=f"Tidak di-approve dalam {days_pending} hari (status: {user.approval_status.value})",
                    action="unapproved_delete",
                )
                db.session.delete(user)
                counters["unapproved_deleted"] += 1

    if db.session.dirty or db.session.new or db.session.deleted:
        db.session.commit()

    current_app.logger.info("cleanup_inactive_users selesai: %s", counters)
    return counters
