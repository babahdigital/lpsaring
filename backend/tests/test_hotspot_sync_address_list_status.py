from __future__ import annotations

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
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:01", ip_address="10.0.99.40"),
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:02", ip_address="172.16.2.10"),
            SimpleNamespace(mac_address="AA:BB:CC:DD:EE:03", ip_address=None),
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
    assert "172.16.2.10" in ips
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
