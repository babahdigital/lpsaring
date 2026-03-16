from __future__ import annotations

import ipaddress
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


def _make_runtime_settings(**overrides):
    values = {
        "auto_enroll_devices_from_ip_binding": False,
        "max_devices_per_user": 3,
        "auto_enroll_debug_log": False,
        "active_profile": "profile-active",
        "blocked_profile": "profile-blocked",
        "expired_profile": "profile-expired",
        "habis_profile": "profile-habis",
        "fup_profile": "profile-fup",
        "unlimited_profile": "profile-unlimited",
        "whatsapp_notifications_enabled": True,
        "managed_status_lists": [
            "active_list",
            "fup_list",
            "inactive_list",
            "expired_list",
            "habis_list",
            "blocked_list",
        ],
        "list_active": "active_list",
        "list_fup": "fup_list",
        "list_inactive": "inactive_list",
        "list_expired": "expired_list",
        "list_habis": "habis_list",
        "list_blocked": "blocked_list",
        "list_unauthorized": "unauthorized_list",
        "fup_threshold_mb": 3072.0,
        "hotspot_status_networks": [ipaddress.ip_network("172.16.2.0/23")],
        "dhcp_static_lease_enabled": False,
        "dhcp_server_name": None,
        "quota_debt_limit_mb": 500.0,
        "quota_notify_remaining_mb_thresholds": [500],
        "quota_expiry_notify_days_thresholds": [7, 3, 1],
    }
    values.update(overrides)
    return svc.HotspotUsageSyncRuntimeSettings(**values)


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


def test_resolve_target_profile_uses_runtime_settings_without_settings_lookup(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("settings lookup should be skipped")),
    )
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("settings lookup should be skipped")),
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        total_quota_purchased_mb=4096,
        total_quota_used_mb=0,
    )

    result = svc._resolve_target_profile(
        user=user,
        remaining_mb=256.0,
        remaining_percent=6.25,
        is_expired=False,
        runtime_settings=_make_runtime_settings(
            active_profile="cached-active",
            fup_profile="cached-fup",
            fup_threshold_mb=1024.0,
        ),
    )

    assert result == "cached-fup"


def test_apply_auto_debt_limit_block_state_sets_block_when_limit_reached(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else default,
    )

    notifications = []

    monkeypatch.setattr(
        svc,
        "_send_auto_debt_limit_block_notification",
        lambda user, *, debt_mb, limit_mb: notifications.append((user, debt_mb, limit_mb)),
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
    assert notifications == [(user, 650.0, 500.0)]


def test_apply_auto_debt_limit_block_state_uses_runtime_settings_without_settings_lookup(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("settings lookup should be skipped")),
    )

    warnings = []

    monkeypatch.setattr(
        svc,
        "_send_auto_debt_limit_warning_notification",
        lambda user, *, debt_mb, limit_mb: warnings.append((user, debt_mb, limit_mb)),
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        role=None,
        is_blocked=False,
        blocked_reason=None,
        blocked_at=None,
        blocked_by_id=None,
        quota_debt_auto_mb=420.0,
    )

    forced = svc._apply_auto_debt_limit_block_state(
        user,
        source="test",
        runtime_settings=_make_runtime_settings(quota_debt_limit_mb=500.0),
    )

    assert forced is False
    assert user.is_blocked is False
    assert warnings == [(user, 420.0, 500.0)]


def test_apply_auto_debt_limit_block_state_unblocks_previous_auto_block_below_limit(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else default,
    )
    monkeypatch.setattr(svc, "_send_auto_debt_limit_warning_notification", lambda *args, **kwargs: None)

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


def test_apply_auto_debt_limit_block_state_skips_duplicate_notification_for_existing_block(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else default,
    )

    notifications = []

    monkeypatch.setattr(
        svc,
        "_send_auto_debt_limit_block_notification",
        lambda user, *, debt_mb, limit_mb: notifications.append((user, debt_mb, limit_mb)),
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        role=None,
        is_blocked=True,
        blocked_reason="manual_admin_block|reason=test",
        blocked_at=datetime.now(timezone.utc),
        blocked_by_id=None,
        quota_debt_auto_mb=900.0,
    )

    forced = svc._apply_auto_debt_limit_block_state(user, source="test")

    assert forced is True
    assert notifications == []


def test_apply_auto_debt_limit_block_state_sends_warning_before_block(monkeypatch):
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 500 if key == "QUOTA_DEBT_LIMIT_MB" else (400 if key == "QUOTA_DEBT_WARNING_MB" else default),
    )

    warnings = []
    blocks = []

    monkeypatch.setattr(
        svc,
        "_send_auto_debt_limit_warning_notification",
        lambda user, *, debt_mb, limit_mb: warnings.append((user, debt_mb, limit_mb)),
    )
    monkeypatch.setattr(
        svc,
        "_send_auto_debt_limit_block_notification",
        lambda user, *, debt_mb, limit_mb: blocks.append((user, debt_mb, limit_mb)),
    )

    user = SimpleNamespace(
        is_unlimited_user=False,
        role=None,
        is_blocked=False,
        blocked_reason=None,
        blocked_at=None,
        blocked_by_id=None,
        quota_debt_auto_mb=420.0,
    )

    forced = svc._apply_auto_debt_limit_block_state(user, source="test")

    assert forced is False
    assert user.is_blocked is False
    assert warnings == [(user, 420.0, 500.0)]
    assert blocks == []


def test_self_heal_policy_binding_also_enforces_static_dhcp_lease(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = "True"

    calls = []
    api = object()

    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")
    monkeypatch.setattr(svc, "upsert_ip_binding", lambda **_k: (True, "ok"))
    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(svc.settings_service, "get_setting", lambda k, d=None: "Klien" if k == "MIKROTIK_DHCP_LEASE_SERVER_NAME" else d)

    def _capture_lease(**kwargs):
        calls.append(kwargs)
        return True

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
        repaired = svc._self_heal_policy_binding_for_user(
            api=api,
            user=user,
            ip_binding_map=ip_binding_map,
            host_usage_map={},
            dhcp_ips_by_mac={},
        )

    assert repaired == 1
    assert len(calls) == 1
    assert calls[0]["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert calls[0]["ip_address"] == "172.16.2.10"
    assert calls[0]["server"] == "Klien"
    assert calls[0]["api_connection"] is api
    assert "uid=user-1" in calls[0]["comment"]


def test_self_heal_policy_binding_skips_static_dhcp_when_ip_missing(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = "True"

    calls = []

    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")
    monkeypatch.setattr(svc, "upsert_ip_binding", lambda **_k: (True, "ok"))
    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(svc.settings_service, "get_setting", lambda *_a, **_k: "Klien")
    monkeypatch.setattr(svc, "_ensure_static_dhcp_lease", lambda **kwargs: calls.append(kwargs) or True)

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
