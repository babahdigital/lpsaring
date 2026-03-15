from __future__ import annotations

from datetime import datetime, timezone
import uuid
from types import SimpleNamespace

from app.services.user_management import user_profile


def test_apply_manual_debt_advance_credit_updates_purchase_and_logs(monkeypatch):
    previous_expiry = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
    now_value = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
    normalized_expiry = datetime(2026, 4, 14, 9, 30, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id=uuid.uuid4(),
        total_quota_purchased_mb=1024,
        total_quota_used_mb=2048.0,
        auto_debt_offset_mb=0,
        manual_debt_mb=5120,
        is_blocked=False,
        blocked_reason=None,
        is_unlimited_user=False,
        quota_expiry_date=previous_expiry,
    )
    admin = SimpleNamespace(id=uuid.uuid4())
    captured: dict[str, object] = {}

    def _snapshot(target_user):
        return {
            "total_quota_purchased_mb": int(target_user.total_quota_purchased_mb or 0),
            "total_quota_used_mb": float(target_user.total_quota_used_mb or 0.0),
            "manual_debt_mb": int(target_user.manual_debt_mb or 0),
        }

    def _consume(*, user, admin_actor, injected_mb, source):
        assert injected_mb == 20480
        assert source == "admin_debt_advance_pkg"
        return 512, 19968

    def _append_event(**kwargs):
        captured.update(kwargs)

    def _calculate_expiry(*, current_expiry, now, days_to_add, strategy):
        assert current_expiry == previous_expiry
        assert now == now_value
        assert days_to_add == 30
        assert strategy == "reset_from_now"
        return normalized_expiry

    monkeypatch.setattr(user_profile, "snapshot_user_quota_state", _snapshot)
    monkeypatch.setattr(
        user_profile.debt_service,
        "consume_injected_mb_for_auto_debt_only",
        _consume,
    )
    monkeypatch.setattr(user_profile, "get_app_local_datetime", lambda *_args, **_kwargs: now_value)
    monkeypatch.setattr(user_profile, "calculate_quota_expiry_date", _calculate_expiry)
    monkeypatch.setattr(user_profile, "append_quota_mutation_event", _append_event)

    paid_auto_mb, remaining_credit_mb = user_profile._apply_manual_debt_advance_credit(
        user=user,
        admin_actor=admin,
        credit_mb=20480,
        source="admin_debt_advance_pkg",
        days_to_add=30,
        grant_label="Paket Debt 20 GB",
        grant_reference="pkg-debt-20",
    )

    assert paid_auto_mb == 512
    assert remaining_credit_mb == 19968
    assert user.total_quota_purchased_mb == 1024 + 19968
    assert user.quota_expiry_date == normalized_expiry
    assert captured["source"] == "quota.debt_advance:admin_debt_advance_pkg"
    assert captured["event_details"] == {
        "credit_mb": 20480,
        "paid_auto_debt_mb": 512,
        "net_added_mb": 19968,
        "added_days": 30,
        "grant_label": "Paket Debt 20 GB",
        "grant_reference": "pkg-debt-20",
        "previous_expiry_at": previous_expiry.isoformat(),
        "normalized_expiry_at": normalized_expiry.isoformat(),
    }