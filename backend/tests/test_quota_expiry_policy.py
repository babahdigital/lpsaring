from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.quota_expiry_policy import calculate_quota_expiry_date, normalize_quota_expiry_strategy


def test_normalize_quota_expiry_strategy_defaults_to_extend_active():
    assert normalize_quota_expiry_strategy(None) == "extend_active"
    assert normalize_quota_expiry_strategy("unknown") == "extend_active"


def test_calculate_quota_expiry_date_extend_active_preserves_active_future_expiry():
    now = datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc)
    current_expiry = now + timedelta(days=20)

    result = calculate_quota_expiry_date(
        current_expiry=current_expiry,
        now=now,
        days_to_add=30,
        strategy="extend_active",
    )

    assert result == current_expiry + timedelta(days=30)


def test_calculate_quota_expiry_date_reset_from_now_ignores_active_future_expiry():
    now = datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc)
    current_expiry = now + timedelta(days=46)

    result = calculate_quota_expiry_date(
        current_expiry=current_expiry,
        now=now,
        days_to_add=30,
        strategy="reset_from_now",
    )

    assert result == now + timedelta(days=30)