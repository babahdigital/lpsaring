from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import app.services.hotspot_sync_service as svc


class _ExplosiveDebt:
    @property
    def quota_debt_auto_mb(self):
        raise RuntimeError("boom")


class _DebtUser(_ExplosiveDebt):
    total_quota_purchased_mb = 1024
    total_quota_used_mb = 2048


def test_resolve_auto_quota_debt_for_limit_prefers_auto_debt_property():
    user = SimpleNamespace(quota_debt_auto_mb=640.5)

    result = svc._resolve_auto_quota_debt_for_limit(user)

    assert result == 640.5


def test_resolve_auto_quota_debt_for_limit_fallback_uses_usage_delta_only():
    user = _DebtUser()

    result = svc._resolve_auto_quota_debt_for_limit(user)

    assert result == 1024.0


def test_unlimited_user_with_expired_time_uses_expired_profile(monkeypatch):
    mapping = {
        "MIKROTIK_INACTIVE_PROFILE": "profile-inactive",
        "MIKROTIK_ACTIVE_PROFILE": "profile-active",
        "MIKROTIK_FUP_PROFILE": "profile-fup",
        "MIKROTIK_HABIS_PROFILE": "profile-habis",
        "MIKROTIK_UNLIMITED_PROFILE": "profile-unlimited",
        "MIKROTIK_EXPIRED_PROFILE": "profile-expired",
    }

    monkeypatch.setattr(svc.settings_service, "get_setting", lambda key, default=None: mapping.get(key, default))
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 3072 if key == "QUOTA_FUP_THRESHOLD_MB" else default,
    )

    user = SimpleNamespace(
        is_unlimited_user=True,
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
        quota_expiry_date=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    result = svc._resolve_target_profile(
        user=user,
        remaining_mb=0.0,
        remaining_percent=0.0,
        is_expired=True,
    )

    assert result == "profile-expired"
