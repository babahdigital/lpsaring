# backend/app/services/hotspot_sync_service.py
import logging
import threading
import uuid
from datetime import datetime, timezone as dt_timezone, date
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
    Transaction,
    UserDevice,
)
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_ip_by_mac,
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
    _remove_blocked_address_list,
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
)
from app.utils.block_reasons import is_auto_debt_limit_reason, build_auto_debt_limit_reason
from app.utils.metrics_utils import increment_metric

logger = logging.getLogger(__name__)

BYTES_PER_MB = 1024 * 1024
REDIS_LAST_BYTES_PREFIX = "quota:last_bytes:mac:"
REDIS_SYNC_LOCK_PREFIX = "quota:sync_lock:user:"
REDIS_GLOBAL_SYNC_LOCK_KEY = "quota:sync_lock:global"
REDIS_ACCESS_STATUS_DEDUPE_PREFIX = "wa:dedupe:access_status:"
LOCAL_GLOBAL_SYNC_LOCK_TOKEN = "__local_global_sync_lock__"
_local_global_sync_lock = threading.Lock()
_thread_local_state = threading.local()


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


def _is_valid_ip_candidate(value: Optional[str]) -> bool:
    if not value:
        return False
    ip = str(value).strip()
    if not ip:
        return False
    if ip in {"0.0.0.0", "0.0.0.0/0"}:
        return False
    return True


def _collect_candidate_ips_for_user(
    user: User,
    host_usage_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ip_binding_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    ips: List[str] = []
    seen: set[str] = set()

    def _add_ip(ip_value: Optional[str]) -> None:
        if not _is_valid_ip_candidate(ip_value):
            return
        ip_str = str(ip_value).strip()
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

    return ips


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


def _get_redis_client():
    try:
        return getattr(current_app, "redis_client_otp", None)
    except Exception:
        return None


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
) -> bool:
    list_active = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active"
    list_fup = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup"
    list_inactive = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
    list_expired = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
    list_habis = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis"
    list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
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
    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)
    comment = (
        f"lpsaring|status={status_value}|user={username_08}|role={user.role.value}|date={date_str}|time={time_str}"
    )
    other_lists = [
        name for name in (list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked) if name
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
                user_id_str = str(user.id)
                fallback_ip = None
                for entry in binding_map.values():
                    if str(entry.get("user_id")) == user_id_str:
                        ip_address = entry.get("address")
                        if ip_address:
                            fallback_ip = str(ip_address)
                            break
                if not fallback_ip:
                    device_macs = db.session.scalars(
                        select(UserDevice.mac_address)
                        .where(
                            UserDevice.user_id == user.id,
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
) -> bool:
    if not ip_address:
        return False

    list_active = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active"
    list_fup = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup"
    list_inactive = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
    list_expired = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
    list_habis = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis"
    list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
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
    comment = (
        f"lpsaring|status={status_value}"
        f"|user={username_08}"
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
    return True


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
) -> Optional[Tuple[float, float]]:
    if not user.devices:
        return None

    old_usage_mb = float(user.total_quota_used_mb or 0.0)

    delta_bytes = 0
    found = False
    now = datetime.now(dt_timezone.utc)
    for device in user.devices:
        mac = (device.mac_address or "").upper()
        if not mac:
            continue
        host_usage = host_usage_map.get(mac)
        if not host_usage:
            continue
        bytes_total = int(host_usage.get("bytes_in", 0)) + int(host_usage.get("bytes_out", 0))
        found = True

        key = f"{REDIS_LAST_BYTES_PREFIX}{mac}"
        last_bytes = None
        has_key = False
        if redis_client is not None:
            try:
                has_key = bool(redis_client.exists(key))
            except Exception:
                has_key = True
            if has_key:
                try:
                    last_bytes = int(redis_client.get(key) or 0)
                except Exception:
                    last_bytes = 0

        if last_bytes is None:
            if device.last_bytes_total is not None:
                last_bytes = int(device.last_bytes_total)
            else:
                device.last_bytes_total = bytes_total
                device.last_bytes_updated_at = now
                if redis_client is not None:
                    try:
                        redis_client.set(key, bytes_total)
                    except Exception:
                        pass
                continue

        if bytes_total >= last_bytes:
            delta_bytes += bytes_total - last_bytes
        else:
            delta_bytes += bytes_total

        device.last_bytes_total = bytes_total
        device.last_bytes_updated_at = now
        if redis_client is not None:
            try:
                redis_client.set(key, bytes_total)
            except Exception:
                pass

    if not found:
        return None

    delta_mb = delta_bytes / BYTES_PER_MB
    new_total_mb = old_usage_mb + delta_mb
    return _round_mb_value(delta_mb), _round_mb_value(new_total_mb)


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
        "failed": 0,
    }
    auto_enroll_users = 0
    auto_enroll_devices = 0

    users_to_sync = db.session.scalars(
        select(User)
        .where(
            User.is_active,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
            User.approval_status == ApprovalStatus.APPROVED,
        )
        .options(
            selectinload(User.transactions).selectinload(Transaction.package),
            selectinload(User.devices),
        )
    ).all()

    if not users_to_sync:
        return counters

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
                counters["failed"] = len(users_to_sync)
                return counters

            ok_host, host_usage_map, host_msg = get_hotspot_host_usage_map(api)
            if not ok_host:
                logger.error(f"Gagal mengambil data host Mikrotik: {host_msg}")
                counters["failed"] = len(users_to_sync)
                return counters

            ip_binding_map: Dict[str, Dict[str, Any]] = {}
            if settings_service.get_setting("AUTO_ENROLL_DEVICES_FROM_IP_BINDING", "True") == "True":
                ok_binding, binding_map, binding_msg = get_hotspot_ip_binding_user_map(api)
                if ok_binding:
                    ip_binding_map = binding_map
                else:
                    logger.warning(f"Gagal mengambil data ip-binding Mikrotik: {binding_msg}")

            for user in users_to_sync:
                try:
                    if _is_demo_user(user):
                        continue

                    if not _acquire_sync_lock(redis_client, user.id):
                        continue
                    username_08 = format_to_local_phone(user.phone_number)
                    if not username_08:
                        _release_sync_lock(redis_client, user.id)
                        continue

                    if ip_binding_map:
                        max_devices = settings_service.get_setting_as_int("MAX_DEVICES_PER_USER", 3)
                        existing_devices = len(user.devices or [])
                        available_slots = max(0, max_devices - existing_devices)
                        if available_slots > 0:
                            debug_log = settings_service.get_setting("AUTO_ENROLL_DEBUG_LOG", "False") == "True"
                            added_devices = _auto_enroll_devices_from_ip_binding(
                                user,
                                ip_binding_map,
                                host_usage_map,
                                available_slots,
                                debug_log,
                            )
                            if added_devices > 0:
                                auto_enroll_users += 1
                                auto_enroll_devices += added_devices

                    usage_update = _calculate_usage_update(user, host_usage_map, redis_client)
                    old_usage_mb = float(user.total_quota_used_mb or 0.0)
                    if usage_update:
                        delta_mb, new_total_usage_mb = usage_update
                        _update_daily_usage_log(user, delta_mb, today)
                        if abs(new_total_usage_mb - old_usage_mb) >= 0.01:
                            lock_user_quota_row(user)
                            before_state = snapshot_user_quota_state(user)
                            user.total_quota_used_mb = new_total_usage_mb
                            counters["updated_usage"] += 1
                            append_quota_mutation_event(
                                user=user,
                                source="hotspot.sync_usage",
                                before_state=before_state,
                                after_state=snapshot_user_quota_state(user),
                                idempotency_key=(f"sync_usage:{user.id}:{today.isoformat()}:{round(new_total_usage_mb,2)}")[:128],
                                event_details={
                                    "delta_mb": float(round(delta_mb, 2)),
                                    "new_total_usage_mb": float(round(new_total_usage_mb, 2)),
                                },
                            )

                    remaining_mb, remaining_percent = _calculate_remaining(user)

                    force_blocked_status = _apply_auto_debt_limit_block_state(user, source="sync_usage")
                    blocked_profile = settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"

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

                    _emit_policy_binding_mismatch_metrics(user, ip_binding_map)

                    if target_profile and user.mikrotik_profile_name != target_profile:
                        success_profile, message = set_hotspot_user_profile(
                            api_connection=api, username_or_id=username_08, new_profile_name=target_profile
                        )
                        if success_profile:
                            user.mikrotik_profile_name = target_profile
                            counters["profile_updates"] += 1
                            expired_profile = (
                                settings_service.get_setting("MIKROTIK_EXPIRED_PROFILE", "expired") or "expired"
                            )
                            habis_profile = settings_service.get_setting("MIKROTIK_HABIS_PROFILE", "habis") or "habis"
                            fup_profile = settings_service.get_setting("MIKROTIK_FUP_PROFILE", "fup") or "fup"
                            status_key = None
                            if target_profile == expired_profile:
                                status_key = "expired"
                            elif target_profile == habis_profile:
                                status_key = "habis"
                            elif target_profile == fup_profile:
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
                        ):
                            ok_any_ip = True

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
                        )

                    if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True":
                        _send_quota_notifications(user, remaining_percent, remaining_mb)
                        _send_expiry_notifications(user)

                    counters["processed"] += 1
                    _release_sync_lock(redis_client, user.id)
                except Exception as e:
                    logger.error(f"Error sinkronisasi user {user.id}: {e}", exc_info=True)
                    counters["failed"] += 1
                    _release_sync_lock(redis_client, user.id)

        if auto_enroll_devices > 0:
            logger.info(
                "Auto-enroll ringkas: users=%s devices=%s",
                auto_enroll_users,
                auto_enroll_devices,
            )

        db.session.commit()

        return counters
    finally:
        _release_global_sync_lock(redis_client, global_lock_token)


def sync_address_list_for_single_user(user: User, client_ip: Optional[str] = None) -> bool:
    """Sync address-list status for a single user based on DB counters."""
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

    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Gagal konek MikroTik untuk sync address-list single user")
            return False

        ok_any_ip = False
        ips: List[str] = []
        if client_ip and _is_valid_ip_candidate(client_ip):
            ips.append(str(client_ip).strip())
        for device in user.devices or []:
            ip_address = getattr(device, "ip_address", None)
            if ip_address and _is_valid_ip_candidate(str(ip_address)):
                ip_str = str(ip_address).strip()
                if ip_str not in ips:
                    ips.append(ip_str)

        for ip_address in ips:
            if _sync_address_list_status_for_ip(
                api,
                user,
                ip_address,
                remaining_mb,
                remaining_percent,
                is_expired,
                force_blocked=force_blocked_status,
            ):
                ok_any_ip = True

        ok_user_ip = _sync_address_list_status(
            api,
            user,
            username_08,
            remaining_mb,
            remaining_percent,
            is_expired,
            force_blocked=force_blocked_status,
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


def cleanup_inactive_users() -> Dict[str, int]:
    counters = {"deactivated": 0, "deleted": 0}
    now_utc = datetime.now(dt_timezone.utc)
    deactivate_days = settings_service.get_setting_as_int("INACTIVE_DEACTIVATE_DAYS", 45)
    delete_days = settings_service.get_setting_as_int("INACTIVE_DELETE_DAYS", 90)

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

            if days_inactive >= delete_days:
                devices = db.session.scalars(select(UserDevice).where(UserDevice.user_id == user.id)).all()
                for device in devices:
                    if device.mac_address:
                        _remove_ip_binding(device.mac_address, user.mikrotik_server_name or "all")
                    if device.ip_address:
                        _remove_blocked_address_list(device.ip_address)
                    db.session.delete(device)
                if api and username_08:
                    delete_hotspot_user(api_connection=api, username=username_08)
                db.session.delete(user)
                counters["deleted"] += 1
                continue

            if user.is_active and days_inactive >= deactivate_days:
                devices = db.session.scalars(select(UserDevice).where(UserDevice.user_id == user.id)).all()
                for device in devices:
                    if device.mac_address:
                        _remove_ip_binding(device.mac_address, user.mikrotik_server_name or "all")
                    if device.ip_address:
                        _remove_blocked_address_list(device.ip_address)
                if api and username_08:
                    delete_hotspot_user(api_connection=api, username=username_08)
                user.is_active = False
                user.mikrotik_user_exists = False
                counters["deactivated"] += 1

    if db.session.dirty or db.session.new or db.session.deleted:
        db.session.commit()

    return counters
