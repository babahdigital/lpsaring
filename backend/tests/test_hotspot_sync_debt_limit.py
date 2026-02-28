from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from flask import Flask

import app.services.hotspot_sync_service as svc
from app.utils.block_reasons import AUTO_DEBT_LIMIT_PREFIX, build_auto_debt_limit_reason


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


def test_resolve_target_profile_uses_habis_when_purchased_zero(monkeypatch):
    mapping = {
        "MIKROTIK_ACTIVE_PROFILE": "profile-active",
        "MIKROTIK_FUP_PROFILE": "profile-fup",
        "MIKROTIK_HABIS_PROFILE": "profile-habis",
        "MIKROTIK_UNLIMITED_PROFILE": "profile-unlimited",
        "MIKROTIK_EXPIRED_PROFILE": "profile-expired",
    }

    monkeypatch.setattr(svc.settings_service, "get_setting", lambda key, default=None: mapping.get(key, default))
    monkeypatch.setattr(svc.settings_service, "get_setting_as_int", lambda *_a, **_k: 3072)

    user = SimpleNamespace(
        is_unlimited_user=False,
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
    )

    result = svc._resolve_target_profile(
        user=user,
        remaining_mb=0.0,
        remaining_percent=0.0,
        is_expired=False,
    )

    assert result == "profile-habis"


def test_apply_auto_debt_limit_block_state_sets_block_when_limit_reached(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else default,
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        role=None,
        is_blocked=False,
        blocked_reason=None,
        blocked_at=None,
        blocked_by_id=None,
        quota_debt_auto_mb=650.0,
    )

    forced = svc._apply_auto_debt_limit_block_state(user, source="test")

    assert forced is True
    assert user.is_blocked is True
    assert str(user.blocked_reason).startswith(AUTO_DEBT_LIMIT_PREFIX)


def test_apply_auto_debt_limit_block_state_unblocks_previous_auto_block_below_limit(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else default,
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        role=None,
        is_blocked=True,
        blocked_reason=build_auto_debt_limit_reason(debt_mb=700, limit_mb=500, source="sync_usage"),
        blocked_at=datetime.now(timezone.utc),
        blocked_by_id=None,
        quota_debt_auto_mb=120.0,
    )

    forced = svc._apply_auto_debt_limit_block_state(user, source="test")

    assert forced is False
    assert user.is_blocked is False
    assert user.blocked_reason is None
    assert user.blocked_at is None


def test_self_heal_policy_binding_also_enforces_static_dhcp_lease(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = "True"

    calls = []

    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")
    monkeypatch.setattr(svc, "upsert_ip_binding", lambda **_k: (True, "ok"))
    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(svc.settings_service, "get_setting", lambda k, d=None: "Klien" if k == "MIKROTIK_DHCP_LEASE_SERVER_NAME" else d)

    def _capture_lease(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(svc, "_ensure_static_dhcp_lease", _capture_lease)

    user = SimpleNamespace(
        id="user-1",
        role=SimpleNamespace(value="USER"),
        phone_number="+628123456789",
        mikrotik_server_name="srv-user",
        devices=[SimpleNamespace(is_authorized=True, mac_address="AA:BB:CC:DD:EE:FF", ip_address="172.16.2.10")],
    )

    ip_binding_map = {"AA:BB:CC:DD:EE:FF": {"type": "blocked", "address": "172.16.2.10"}}

    with app.app_context():
        repaired = svc._self_heal_policy_binding_for_user(api=object(), user=user, ip_binding_map=ip_binding_map, host_usage_map={})

    assert repaired == 1
    assert len(calls) == 1
    assert calls[0]["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert calls[0]["ip_address"] == "172.16.2.10"
    assert calls[0]["server"] == "Klien"
    assert "uid=user-1" in calls[0]["comment"]


def test_self_heal_policy_binding_skips_static_dhcp_when_ip_missing(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = "True"

    calls = []

    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")
    monkeypatch.setattr(svc, "upsert_ip_binding", lambda **_k: (True, "ok"))
    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(svc.settings_service, "get_setting", lambda *_a, **_k: "Klien")
    monkeypatch.setattr(svc, "_ensure_static_dhcp_lease", lambda **kwargs: calls.append(kwargs))

    user = SimpleNamespace(
        id="user-2",
        role=SimpleNamespace(value="USER"),
        phone_number="+628123456780",
        mikrotik_server_name="srv-user",
        devices=[SimpleNamespace(is_authorized=True, mac_address="AA:BB:CC:DD:EE:00", ip_address=None)],
    )

    ip_binding_map = {"AA:BB:CC:DD:EE:00": {"type": "blocked"}}

    with app.app_context():
        repaired = svc._self_heal_policy_binding_for_user(api=object(), user=user, ip_binding_map=ip_binding_map, host_usage_map={})

    assert repaired == 1
    assert calls == []
