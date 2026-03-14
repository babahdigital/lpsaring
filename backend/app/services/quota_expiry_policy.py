from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional


QuotaExpiryStrategy = Literal["extend_active", "reset_from_now"]


def normalize_quota_expiry_strategy(
    raw_value: Optional[str],
    *,
    default: QuotaExpiryStrategy = "extend_active",
) -> QuotaExpiryStrategy:
    candidate = str(raw_value or "").strip().lower()
    if candidate == "reset_from_now":
        return "reset_from_now"
    if candidate == "extend_active":
        return "extend_active"
    return default


def calculate_quota_expiry_date(
    *,
    current_expiry: Optional[datetime],
    now: datetime,
    days_to_add: int,
    strategy: str | QuotaExpiryStrategy = "extend_active",
) -> datetime:
    normalized_days = max(0, int(days_to_add or 0))
    normalized_strategy = normalize_quota_expiry_strategy(strategy, default="extend_active")
    if normalized_days <= 0:
        return current_expiry if current_expiry is not None else now

    baseline = now
    if normalized_strategy == "extend_active" and current_expiry and current_expiry > now:
        baseline = current_expiry

    return baseline + timedelta(days=normalized_days)