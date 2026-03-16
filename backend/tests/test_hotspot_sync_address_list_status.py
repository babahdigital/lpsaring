from __future__ import annotations

import ipaddress
from types import SimpleNamespace
from typing import Any, cast
import uuid

from flask import Flask

import app.services.hotspot_sync_service as svc
from app.utils.block_reasons import build_auto_debt_limit_reason


class _Role:
    def __init__(self, value: str):
        self.value = value


def _patch_settings(monkeypatch, *, fup_threshold_mb: int = 3072):
    mapping = {
        "MIKROTIK_ADDRESS_LIST_ACTIVE": "active_list",
        "MIKROTIK_ADDRESS_LIST_FUP": "fup_list",
        "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive_list",
        "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired_list",
        "MIKROTIK_ADDRESS_LIST_HABIS": "habis_list",
        "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked_list",
        "MIKROTIK_ADDRESS_LIST_UNAUTHORIZED": "unauthorized_list",
    }

    def fake_get_setting(key: str, default=None):
        return mapping.get(key, default)

    def fake_get_setting_as_int(key: str, default: int = 0) -> int:
        if key == "QUOTA_FUP_THRESHOLD_MB":
            return fup_threshold_mb
        return default

    monkeypatch.setattr(svc.settings_service, "get_setting", fake_get_setting)
    monkeypatch.setattr(svc.settings_service, "get_setting_as_int", fake_get_setting_as_int)


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


def test_sync_address_list_blocked_has_priority_and_cleans_other_lists(monkeypatch):
    _patch_settings(monkeypatch)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["username"] = username
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=True,
        role=_Role("USER"),
        phone_number="081234567890",
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=999.0,
        remaining_percent=100.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "blocked_list"

    # Ensure we pass all lists including blocked so sync can remove non-target lists.
    assert "blocked_list" in capture["other_lists"]
    assert "active_list" in capture["other_lists"]
    assert "fup_list" in capture["other_lists"]
    assert "inactive_list" in capture["other_lists"]
    assert "expired_list" in capture["other_lists"]
    assert "habis_list" in capture["other_lists"]

    assert "status=blocked" in capture["comment"]


def test_sync_address_list_non_blocked_removes_blocked_if_present(monkeypatch):
    _patch_settings(monkeypatch, fup_threshold_mb=3072)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=100.0,
        remaining_percent=10.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "fup_list"

    # Critical: blocked list is part of other_lists so it gets removed when user isn't blocked.
    assert "blocked_list" in capture["other_lists"]
    assert "status=fup" in capture["comment"]


def test_sync_address_list_status_uses_runtime_settings_without_settings_lookup(monkeypatch):
    capture = {}

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

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=4096,
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=256.0,
        remaining_percent=6.25,
        is_expired=False,
        runtime_settings=_make_runtime_settings(
            list_fup="cached_fup_list",
            list_active="cached_active_list",
            fup_threshold_mb=1024.0,
        ),
    )

    assert ok is True
    assert capture["target_list"] == "cached_fup_list"
    assert "cached_active_list" in capture["other_lists"]
    assert "status=fup" in capture["comment"]


def test_sync_address_list_auto_debt_blocked_user_uses_blocked_list(monkeypatch):
    _patch_settings(monkeypatch, fup_threshold_mb=3072)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=True,
        blocked_reason=build_auto_debt_limit_reason(debt_mb=640, limit_mb=500, source="test"),
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=0.0,
        remaining_percent=0.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "blocked_list"
    assert "status=blocked" in capture["comment"]


def test_self_heal_policy_binding_repairs_mismatch(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = True

    calls = {"count": 0, "binding_type": None}

    def _fake_upsert_ip_binding(*, api_connection, mac_address, address=None, server=None, binding_type="regular", comment=None):
        calls["count"] += 1
        calls["binding_type"] = binding_type
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_ip_binding", _fake_upsert_ip_binding)
    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=_Role("USER"),
        phone_number="081234567890",
        mikrotik_server_name="srv-user",
        devices=[
            SimpleNamespace(
                is_authorized=True,
                mac_address="DA:B2:F3:B8:94:D2",
                ip_address="172.16.3.179",
            )
        ],
    )
    ip_binding_map = {
        "DA:B2:F3:B8:94:D2": {
            "type": "bypassed",
            "address": "172.16.3.179",
        }
    }

    with app.app_context():
        healed = svc._self_heal_policy_binding_for_user(
            api=object(),
            user=cast(Any, user),
            ip_binding_map=ip_binding_map,
            host_usage_map={},
        )

    assert healed == 1
    assert calls["count"] == 1
    assert calls["binding_type"] == "regular"
    assert ip_binding_map["DA:B2:F3:B8:94:D2"]["type"] == "regular"


def test_self_heal_policy_binding_uses_runtime_settings_without_settings_lookup(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = True

    calls = []

    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")
    monkeypatch.setattr(svc, "upsert_ip_binding", lambda **_k: (True, "ok"))
    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("settings lookup should be skipped")),
    )

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
        repaired = svc._self_heal_policy_binding_for_user(
            api=object(),
            user=cast(Any, user),
            ip_binding_map=ip_binding_map,
            host_usage_map={},
            runtime_settings=_make_runtime_settings(dhcp_server_name="cached-dhcp"),
        )

    assert repaired == 1
    assert len(calls) == 1
    assert calls[0]["server"] == "cached-dhcp"


def test_self_heal_policy_binding_respects_disable_toggle(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = False

    calls = {"count": 0}

    def _fake_upsert_ip_binding(*, api_connection, mac_address, address=None, server=None, binding_type="regular", comment=None):
        calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_ip_binding", _fake_upsert_ip_binding)
    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=_Role("USER"),
        phone_number="081234567890",
        mikrotik_server_name="srv-user",
        devices=[SimpleNamespace(is_authorized=True, mac_address="DA:B2:F3:B8:94:D2", ip_address="172.16.3.179")],
    )
    ip_binding_map = {"DA:B2:F3:B8:94:D2": {"type": "bypassed"}}

    with app.app_context():
        healed = svc._self_heal_policy_binding_for_user(
            api=object(),
            user=cast(Any, user),
            ip_binding_map=ip_binding_map,
            host_usage_map={},
        )

    assert healed == 0
    assert calls["count"] == 0


def test_self_heal_policy_dhcp_uses_runtime_settings_without_settings_lookup(monkeypatch):
    repaired_calls = []

    monkeypatch.setattr(svc, "increment_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(
        svc.settings_service,
        "get_setting",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("settings lookup should be skipped")),
    )

    def _capture_upsert(**kwargs):
        repaired_calls.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_dhcp_static_lease", _capture_upsert)

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=_Role("USER"),
        phone_number="081234567890",
        devices=[
            SimpleNamespace(
                is_authorized=True,
                mac_address="DA:B2:F3:B8:94:D2",
                ip_address=None,
            )
        ],
    )

    repaired = svc._self_heal_policy_dhcp_for_user(
        api=object(),
        user=cast(Any, user),
        host_usage_map={"DA:B2:F3:B8:94:D2": {"address": "172.16.2.50"}},
        ip_binding_map={},
        dhcp_ips_by_mac={},
        runtime_settings=_make_runtime_settings(
            dhcp_static_lease_enabled=True,
            dhcp_server_name="cached-dhcp",
            hotspot_status_networks=[ipaddress.ip_network("172.16.2.0/23")],
        ),
    )

    assert repaired == 1
    assert len(repaired_calls) == 1
    assert repaired_calls[0]["server"] == "cached-dhcp"
    assert repaired_calls[0]["address"] == "172.16.2.50"


def test_sync_address_list_for_ip_skips_out_of_hotspot_cidr(monkeypatch):
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    _patch_settings(monkeypatch)

    calls = {"upsert": 0}

    def _fake_upsert_address_list_entry(*, api_connection, address, list_name, comment=None, timeout=None):
        calls["upsert"] += 1
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_address_list_entry", _fake_upsert_address_list_entry)
    monkeypatch.setattr(svc, "remove_address_list_entry", lambda **_k: (True, "ok"))

    user = SimpleNamespace(
        id=123,
        is_unlimited_user=True,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=0,
    )

    with app.app_context():
        ok = svc._sync_address_list_status_for_ip(
            api=object(),
            user=cast(Any, user),
            ip_address="10.0.99.40",
            remaining_mb=999.0,
            remaining_percent=100.0,
            is_expired=False,
        )

    assert ok is False
    assert calls["upsert"] == 0


def test_collect_candidate_ips_filters_out_of_hotspot_cidr():
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    user = SimpleNamespace(
        devices=[
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:01", ip_address="10.0.99.40", is_authorized=True),
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:02", ip_address="172.16.2.10", is_authorized=True),
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:03", ip_address=None, is_authorized=True),
        ]
    )
    host_usage_map = {
        "AA:BB:CC:DD:EE:01": {"address": "10.1.2.3"},
        "AA:BB:CC:DD:EE:03": {"address": "172.16.2.11"},
    }
    ip_binding_map = {
        "AA:BB:CC:DD:EE:01": {"address": "10.2.2.2"},
        "AA:BB:CC:DD:EE:02": {"address": "172.16.2.12"},
    }

    with app.app_context():
        ips = svc._collect_candidate_ips_for_user(
            cast(Any, user),
            host_usage_map=host_usage_map,
            ip_binding_map=ip_binding_map,
        )

    assert "10.0.99.40" not in ips
    assert "10.1.2.3" not in ips
    assert "10.2.2.2" not in ips
    assert "172.16.2.10" not in ips
    assert "172.16.2.11" in ips
    assert "172.16.2.12" in ips


def test_sync_address_list_for_ip_prunes_when_binding_guard_enabled_and_no_binding(monkeypatch):
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    _patch_settings(monkeypatch)

    calls = {"upsert": 0, "remove": 0}

    def _fake_upsert_address_list_entry(*, api_connection, address, list_name, comment=None, timeout=None):
        calls["upsert"] += 1
        return True, "ok"

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        calls["remove"] += 1
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_address_list_entry", _fake_upsert_address_list_entry)
    monkeypatch.setattr(svc, "remove_address_list_entry", _fake_remove_address_list_entry)

    user = SimpleNamespace(
        id=321,
        is_unlimited_user=False,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
        devices=[SimpleNamespace(is_authorized=True, mac_address="AA:BB:CC:DD:EE:11")],
    )

    with app.app_context():
        ok = svc._sync_address_list_status_for_ip(
            api=object(),
            user=cast(Any, user),
            ip_address="172.16.2.40",
            remaining_mb=100.0,
            remaining_percent=10.0,
            is_expired=False,
            ip_binding_map={"FF:EE:DD:CC:BB:AA": {"user_id": "999", "type": "regular"}},
            ip_binding_rows_by_mac={"FF:EE:DD:CC:BB:AA": [{"type": "regular"}]},
            enforce_binding_guard=True,
        )

    assert ok is False
    assert calls["upsert"] == 0
    # Guard melakukan prune di seluruh managed status list.
    assert calls["remove"] >= 1


def test_sync_address_list_for_ip_guard_allows_when_binding_exists(monkeypatch):
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    _patch_settings(monkeypatch)

    calls = {"upsert": 0}

    def _fake_upsert_address_list_entry(*, api_connection, address, list_name, comment=None, timeout=None):
        calls["upsert"] += 1
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_address_list_entry", _fake_upsert_address_list_entry)
    monkeypatch.setattr(svc, "remove_address_list_entry", lambda **_k: (True, "ok"))

    user = SimpleNamespace(
        id=654,
        is_unlimited_user=False,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
        devices=[SimpleNamespace(is_authorized=True, mac_address="AA:BB:CC:DD:EE:33")],
    )

    with app.app_context():
        ok = svc._sync_address_list_status_for_ip(
            api=object(),
            user=cast(Any, user),
            ip_address="172.16.2.41",
            remaining_mb=100.0,
            remaining_percent=10.0,
            is_expired=False,
            ip_binding_map={"AA:BB:CC:DD:EE:33": {"user_id": "654", "type": "regular"}},
            ip_binding_rows_by_mac={"AA:BB:CC:DD:EE:33": [{"type": "regular"}]},
            enforce_binding_guard=True,
        )

    assert ok is True
    assert calls["upsert"] == 1


def test_sync_address_list_for_ip_also_removes_unauthorized_overlap(monkeypatch):
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    _patch_settings(monkeypatch)

    removed_lists: list[str] = []

    def _fake_upsert_address_list_entry(*, api_connection, address, list_name, comment=None, timeout=None):
        return True, "ok"

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        removed_lists.append(str(list_name))
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_address_list_entry", _fake_upsert_address_list_entry)
    monkeypatch.setattr(svc, "remove_address_list_entry", _fake_remove_address_list_entry)

    user = SimpleNamespace(
        id=777,
        is_unlimited_user=True,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=0,
    )

    with app.app_context():
        ok = svc._sync_address_list_status_for_ip(
            api=object(),
            user=cast(Any, user),
            ip_address="172.16.2.88",
            remaining_mb=999.0,
            remaining_percent=100.0,
            is_expired=False,
        )

    assert ok is True
    assert "unauthorized_list" in removed_lists


def test_prune_stale_status_entries_for_user_removes_old_ips_of_same_user(monkeypatch):
    _patch_settings(monkeypatch)

    removed_calls: list[tuple[str, str]] = []

    class _FakeAddressListResource:
        def __init__(self):
            self.rows_by_list = {
                "fup_list": [
                    {
                        "address": "172.16.2.192",
                        "comment": "lpsaring|status=fup|user=083141617466|role=USER|ip=172.16.2.192",
                    },
                    {
                        "address": "172.16.2.235",
                        "comment": "lpsaring|status=fup|user=088808494715|role=USER|ip=172.16.2.235",
                    },
                ],
                "active_list": [
                    {
                        "address": "172.16.2.27",
                        "comment": "lpsaring|status=active|user=083141617466|uid=user-1|role=USER|ip=172.16.2.27",
                    }
                ],
                "inactive_list": [],
                "expired_list": [],
                "habis_list": [],
                "blocked_list": [],
            }

        def get(self, **kwargs):
            list_name = str(kwargs.get("list") or "")
            return [dict(row) for row in self.rows_by_list.get(list_name, [])]

    class _FakeApi:
        def __init__(self):
            self.address_list_resource = _FakeAddressListResource()

        def get_resource(self, path: str):
            assert path == "/ip/firewall/address-list"
            return self.address_list_resource

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        removed_calls.append((str(list_name), str(address)))
        return True, "ok"

    monkeypatch.setattr(svc, "remove_address_list_entry", _fake_remove_address_list_entry)

    user = SimpleNamespace(
        id="user-1",
        phone_number="083141617466",
    )

    removed = svc._prune_stale_status_entries_for_user(
        api=cast(Any, _FakeApi()),
        user=cast(Any, user),
        keep_ips=["172.16.2.27"],
    )

    assert removed == 1
    assert ("fup_list", "172.16.2.192") in removed_calls
    assert ("active_list", "172.16.2.27") not in removed_calls
    assert ("fup_list", "172.16.2.235") not in removed_calls


def test_snapshot_owned_status_entries_for_prune_indexes_uid_and_username(monkeypatch):
    _patch_settings(monkeypatch)

    class _FakeAddressListResource:
        def __init__(self):
            self.rows_by_list = {
                "fup_list": [
                    {
                        "address": "172.16.2.192",
                        "comment": "lpsaring|status=fup|user=083141617466|role=USER|ip=172.16.2.192",
                    },
                ],
                "active_list": [
                    {
                        "address": "172.16.2.27",
                        "comment": "lpsaring|status=active|user=083141617466|uid=user-1|role=USER|ip=172.16.2.27",
                    }
                ],
                "inactive_list": [],
                "expired_list": [],
                "habis_list": [],
                "blocked_list": [],
            }

        def get(self, **kwargs):
            list_name = str(kwargs.get("list") or "")
            return [dict(row) for row in self.rows_by_list.get(list_name, [])]

    class _FakeApi:
        def __init__(self):
            self.address_list_resource = _FakeAddressListResource()

        def get_resource(self, path: str):
            assert path == "/ip/firewall/address-list"
            return self.address_list_resource

    ok, snapshot = svc._snapshot_owned_status_entries_for_prune(
        cast(Any, _FakeApi()),
        managed_status_lists=["active_list", "fup_list"],
    )

    assert ok is True
    assert snapshot["by_user_id"] == {
        "user-1": {("active_list", "172.16.2.27")},
    }
    assert snapshot["by_username"] == {
        "083141617466": {
            ("active_list", "172.16.2.27"),
            ("fup_list", "172.16.2.192"),
        }
    }


def test_prune_stale_status_entries_for_user_uses_snapshot_without_requery(monkeypatch):
    removed_calls: list[tuple[str, str]] = []

    class _ExplodingApi:
        def get_resource(self, _path: str):
            raise AssertionError("status-list resource should not be requeried when snapshot is provided")

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        removed_calls.append((str(list_name), str(address)))
        return True, "ok"

    monkeypatch.setattr(svc, "remove_address_list_entry", _fake_remove_address_list_entry)

    user = SimpleNamespace(
        id="user-1",
        phone_number="083141617466",
    )
    snapshot = {
        "by_user_id": {
            "user-1": {
                ("active_list", "172.16.2.27"),
                ("fup_list", "172.16.2.192"),
            }
        },
        "by_username": {
            "083141617466": {
                ("active_list", "172.16.2.27"),
                ("fup_list", "172.16.2.192"),
            }
        },
    }

    removed = svc._prune_stale_status_entries_for_user(
        api=cast(Any, _ExplodingApi()),
        user=cast(Any, user),
        keep_ips=["172.16.2.27"],
        owned_status_entries_snapshot=cast(Any, snapshot),
    )

    assert removed == 1
    assert removed_calls == [("fup_list", "172.16.2.192")]


def test_collect_candidate_ips_for_user_ignores_unauthorized_devices_and_stale_db_ip(monkeypatch):
    _patch_settings(monkeypatch)

    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    user = SimpleNamespace(
        devices=[
            SimpleNamespace(
                is_authorized=True,
                mac_address="AA:BB:CC:DD:EE:01",
                ip_address="172.16.2.10",
            ),
            SimpleNamespace(
                is_authorized=False,
                mac_address="AA:BB:CC:DD:EE:02",
                ip_address="172.16.2.20",
            ),
            SimpleNamespace(
                is_authorized=True,
                mac_address="AA:BB:CC:DD:EE:03",
                ip_address="172.16.2.30",
            ),
        ]
    )

    with app.app_context():
        ips = svc._collect_candidate_ips_for_user(
            cast(Any, user),
            host_usage_map={
                "AA:BB:CC:DD:EE:01": {"address": "172.16.2.11"},
                "AA:BB:CC:DD:EE:02": {"address": "172.16.2.21"},
            },
            ip_binding_map={
                "AA:BB:CC:DD:EE:03": {"address": "172.16.2.31"},
            },
            ip_binding_rows_by_mac={
                "AA:BB:CC:DD:EE:01": [{"address": "172.16.2.12"}],
                "AA:BB:CC:DD:EE:02": [{"address": "172.16.2.22"}],
            },
        )

    assert ips == ["172.16.2.11", "172.16.2.31"]


def test_sync_address_list_for_single_user_runs_binding_and_dhcp_self_heal(monkeypatch):
    _patch_settings(monkeypatch)

    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    calls = {"binding": 0, "dhcp": 0}

    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (100.0, 100.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda _user, source=None: False)
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", lambda _api: (True, {}))

    def _fake_binding_self_heal(api, user, ip_binding_map, host_usage_map):
        calls["binding"] += 1
        return 1

    def _fake_dhcp_self_heal(api, user, *, host_usage_map, ip_binding_map, dhcp_ips_by_mac):
        calls["dhcp"] += 1
        return 1

    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", _fake_binding_self_heal)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", _fake_dhcp_self_heal)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: True)

    user = SimpleNamespace(
        id=str(uuid.uuid4()),
        is_active=True,
        approval_status=svc.ApprovalStatus.APPROVED,
        phone_number="081234567890",
        quota_expiry_date=None,
        is_unlimited_user=True,
        is_blocked=False,
        role=_Role("USER"),
        devices=[],
    )

    with app.app_context():
        ok = svc.sync_address_list_for_single_user(cast(Any, user), api_connection=object())

    assert ok is True
    assert calls == {"binding": 1, "dhcp": 1}


def test_sync_address_list_for_single_user_skips_policy_self_heal_when_disabled(monkeypatch):
    _patch_settings(monkeypatch)

    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]

    calls = {"binding": 0, "dhcp": 0, "dhcp_snapshot": 0}

    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (100.0, 100.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda _user, source=None: False)
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))

    def _fake_dhcp_snapshot(_api):
        calls["dhcp_snapshot"] += 1
        return True, {}

    def _fake_binding_self_heal(api, user, ip_binding_map, host_usage_map):
        calls["binding"] += 1
        return 1

    def _fake_dhcp_self_heal(api, user, *, host_usage_map, ip_binding_map, dhcp_ips_by_mac):
        calls["dhcp"] += 1
        return 1

    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", _fake_dhcp_snapshot)
    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", _fake_binding_self_heal)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", _fake_dhcp_self_heal)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: True)

    user = SimpleNamespace(
        id=str(uuid.uuid4()),
        is_active=True,
        approval_status=svc.ApprovalStatus.APPROVED,
        phone_number="081234567890",
        quota_expiry_date=None,
        is_unlimited_user=True,
        is_blocked=False,
        role=_Role("USER"),
        devices=[],
    )

    with app.app_context():
        ok = svc.sync_address_list_for_single_user(
            cast(Any, user),
            api_connection=object(),
            enable_policy_self_heal=False,
        )

    assert ok is True
    assert calls == {"binding": 0, "dhcp": 0, "dhcp_snapshot": 0}
