from __future__ import annotations

from typing import Iterable, Set

from flask import current_app

from app.services import settings_service
from app.utils.formatters import get_app_local_datetime


VALID_ACCESS_STATUSES = {
    "active",
    "fup",
    "unlimited",
    "habis",
    "expired",
    "blocked",
    "inactive",
}

DEFAULT_BYPASS_STATUSES = {"active", "fup", "unlimited"}


def is_network_hard_block_required(user) -> bool:
    if user is None:
        return False
    if not bool(getattr(user, "is_blocked", False)):
        return False

    reason = str(getattr(user, "blocked_reason", "") or "").strip().lower()

    # Auto debt block: tetap blocked di level aplikasi, tetapi network tidak hard-block.
    if reason.startswith("quota_debt_limit|") or reason.startswith("quota_auto_debt_limit|"):
        return False

    # Default untuk blok lain (manual admin, end-of-month manual debt, dsb): hard-block aktif.
    return True


def _normalize_statuses(values: Iterable[str]) -> Set[str]:
    result: Set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized in VALID_ACCESS_STATUSES:
            result.add(normalized)
    return result


def _parse_statuses_from_text(raw_value: str) -> Set[str]:
    text = raw_value.strip()
    if not text:
        return set()

    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    parts = [part.strip().strip('"').strip("'") for part in text.split(",")]
    return _normalize_statuses(parts)


def get_hotspot_bypass_statuses() -> Set[str]:
    raw_setting = settings_service.get_setting("HOTSPOT_BYPASS_STATUSES", None)

    if isinstance(raw_setting, str):
        parsed = _parse_statuses_from_text(raw_setting)
        if parsed:
            return parsed

    config_value = current_app.config.get("HOTSPOT_BYPASS_STATUSES", None)
    if isinstance(config_value, list):
        parsed = _normalize_statuses(config_value)
        if parsed:
            return parsed
    if isinstance(config_value, str):
        parsed = _parse_statuses_from_text(config_value)
        if parsed:
            return parsed

    return set(DEFAULT_BYPASS_STATUSES)


def get_user_access_status(user) -> str:
    if user is None:
        return "inactive"

    if bool(getattr(user, "is_blocked", False)):
        return "blocked"

    approval_status = getattr(user, "approval_status", None)
    approval_status_value = getattr(approval_status, "value", approval_status)
    if (not bool(getattr(user, "is_active", False))) or approval_status_value != "APPROVED":
        return "inactive"

    if bool(getattr(user, "is_unlimited_user", False)):
        return "unlimited"

    purchased_mb = float(getattr(user, "total_quota_purchased_mb", 0) or 0.0)
    used_mb = float(getattr(user, "total_quota_used_mb", 0) or 0.0)
    remaining_mb = max(0.0, purchased_mb - used_mb)

    expiry_date = getattr(user, "quota_expiry_date", None)
    if expiry_date is not None:
        now_local = get_app_local_datetime()
        expiry_local = get_app_local_datetime(expiry_date)
        if expiry_local < now_local:
            return "expired"

    if purchased_mb <= 0 or remaining_mb <= 0:
        return "habis"

    fup_threshold_mb = float(settings_service.get_setting_as_int("QUOTA_FUP_THRESHOLD_MB", 3072) or 3072)
    if purchased_mb > fup_threshold_mb and remaining_mb <= fup_threshold_mb:
        return "fup"

    return "active"


def should_bypass_hotspot_login(user) -> bool:
    user_status = get_user_access_status(user)
    bypass_statuses = get_hotspot_bypass_statuses()
    return user_status in bypass_statuses


def is_hotspot_login_required(user) -> bool:
    return not should_bypass_hotspot_login(user)


def resolve_allowed_binding_type_for_user(user) -> str:
    if get_user_access_status(user) == "blocked" and is_network_hard_block_required(user):
        return "blocked"
    if get_user_access_status(user) == "blocked":
        return "regular"
    if should_bypass_hotspot_login(user):
        return "bypassed"
    return "regular"
