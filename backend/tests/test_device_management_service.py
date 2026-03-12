from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

from flask import Flask

import app.services.device_management_service as dms
from app.services.device_management_service import normalize_mac, reset_user_network_on_logout


def test_normalize_mac_handles_none():
    assert normalize_mac(None) is None


def test_normalize_mac_normalizes_common_formats():
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"


def test_normalize_mac_decodes_percent_encoded():
    assert normalize_mac("AA%3ABB%3ACC%3ADD%3AEE%3AFF") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("AA%253ABB%253ACC%253ADD%253AEE%253AFF") == "AA:BB:CC:DD:EE:FF"


def test_reset_user_network_on_logout_cleans_all_network_artifacts(monkeypatch):
    user = SimpleNamespace(id="u-1", phone_number="08123456789", mikrotik_server_name="all")
    devices = [
        SimpleNamespace(mac_address="aa:bb:cc:dd:ee:ff", ip_address="10.10.10.2"),
        SimpleNamespace(mac_address="11:22:33:44:55:66", ip_address="10.10.10.3"),
    ]

    monkeypatch.setattr(dms, "_is_mikrotik_operations_enabled", lambda: True)
    monkeypatch.setattr(
        dms,
        "_get_settings",
        lambda: {
            "mikrotik_server_default": "all",
            "dhcp_lease_server_name": "dhcp1",
        },
    )
    monkeypatch.setattr(dms, "format_to_local_phone", lambda _v: "08123456789")
    monkeypatch.setattr(
        dms,
        "db",
        SimpleNamespace(session=SimpleNamespace(scalars=lambda *_a, **_k: SimpleNamespace(all=lambda: devices))),
    )

    calls = {
        "ip_binding": 0,
        "dhcp": 0,
        "host": 0,
        "arp": 0,
        "address_list": 0,
    }

    @contextmanager
    def _fake_conn():
        class _FakeResource:
            def get(self):
                return []

            def remove(self, **_kwargs):
                return None

        class _FakeApi:
            def get_resource(self, _path):
                return _FakeResource()

        yield _FakeApi()

    monkeypatch.setattr(dms, "get_mikrotik_connection", _fake_conn)

    def _remove_ip_binding(*, api_connection, mac_address, server):
        assert api_connection is not None
        assert server == "all"
        calls["ip_binding"] += 1
        return True, "ok"

    def _remove_dhcp_lease(*, api_connection, mac_address, server):
        assert api_connection is not None
        assert server == "dhcp1"
        calls["dhcp"] += 1
        return True, "ok"

    def _remove_hotspot_host_entries(*, api_connection, mac_address=None, address=None, username=None):
        assert api_connection is not None
        calls["host"] += 1
        return True, "ok", 1

    def _remove_arp_entries(*, api_connection, mac_address=None, address=None):
        assert api_connection is not None
        calls["arp"] += 1
        return True, "ok", 1

    monkeypatch.setattr(dms, "remove_ip_binding", _remove_ip_binding)
    monkeypatch.setattr(dms, "remove_dhcp_lease", _remove_dhcp_lease)
    monkeypatch.setattr(dms, "remove_hotspot_host_entries", _remove_hotspot_host_entries)
    monkeypatch.setattr(dms, "remove_arp_entries", _remove_arp_entries)
    monkeypatch.setattr(dms, "_remove_managed_address_lists", lambda _ip: calls.__setitem__("address_list", calls["address_list"] + 1))
    monkeypatch.setattr(dms.settings_service, "get_setting", lambda _key, default=None: default)

    summary = reset_user_network_on_logout(cast(Any, user))

    assert summary["devices_seen"] == 2
    assert summary["ip_binding_removed"] == 2
    assert summary["dhcp_removed"] == 2
    assert summary["host_removed"] == 3
    assert summary["arp_removed"] == 2
    assert summary["address_list_cleaned"] == 2
    assert summary["failures"] == 0
    assert calls["ip_binding"] == 2
    assert calls["dhcp"] == 2
    assert calls["host"] == 3
    assert calls["arp"] == 2
    assert calls["address_list"] == 2


def test_reset_user_network_on_logout_disabled_mikrotik(monkeypatch):
    user = SimpleNamespace(id="u-1", phone_number="08123456789", mikrotik_server_name="all")
    monkeypatch.setattr(dms, "_is_mikrotik_operations_enabled", lambda: False)

    summary = reset_user_network_on_logout(cast(Any, user))

    assert summary["mikrotik_ops_enabled"] is False
    assert summary["devices_seen"] == 0


def test_apply_device_binding_for_login_ip_binding_disabled_calls_post_auth_ops(monkeypatch):
    """Ketika ip_binding_enabled=False, _apply_post_auth_mikrotik_ops tetap harus dipanggil
    (unconditional) untuk membersihkan address-list & hotspot host tanpa perlu cek unauthorized list dulu."""
    app = Flask(__name__)
    user = SimpleNamespace(
        id="u-2",
        phone_number="+628123456789",
        role=SimpleNamespace(value="USER"),
        mikrotik_server_name="srv-user",
    )
    device = SimpleNamespace(
        mac_address="AA:BB:CC:DD:EE:FF",
        ip_address="172.16.2.10",
        is_authorized=True,
        authorized_at=None,
    )

    monkeypatch.setattr(
        dms,
        "_get_settings",
        lambda: {
            "ip_binding_enabled": False,
            "ip_binding_type_allowed": "regular",
            "ip_binding_type_blocked": "blocked",
            "ip_binding_fail_open": False,
            "dhcp_static_lease_enabled": False,
            "dhcp_lease_server_name": "",
            "device_auto_replace_enabled": False,
            "max_devices": 3,
            "require_explicit": False,
            "device_stale_days": 30,
            "mikrotik_server_default": "all",
            "global_mac_claim_transfer_enabled": False,
        },
    )
    monkeypatch.setattr(dms, "_resolve_binding_ip", lambda *_a, **_k: ("172.16.2.10", "client_ip", "ok"))
    monkeypatch.setattr(dms, "register_or_update_device", lambda *_a, **_k: (True, "Device terdaftar", device))
    monkeypatch.setattr(
        dms,
        "db",
        SimpleNamespace(session=SimpleNamespace(flush=lambda: None)),
    )

    captured: dict[str, Any] = {}

    def _capture_post_auth(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(dms, "_apply_post_auth_mikrotik_ops", _capture_post_auth)

    with app.app_context():
        ok, msg, resolved_ip = dms.apply_device_binding_for_login(
            cast(Any, user),
            "172.16.2.10",
            "pytest-agent",
            "AA:BB:CC:DD:EE:FF",
            bypass_explicit_auth=True,
        )

    assert ok is True
    assert msg == "Perangkat terotorisasi"
    assert resolved_ip == "172.16.2.10"
    # _apply_post_auth_mikrotik_ops wajib dipanggil meski ip_binding_enabled=False
    assert captured["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert captured["ip_address"] == "172.16.2.10"
    assert captured["server"] == "srv-user"
    assert captured["username"] == "08123456789"
    assert captured["binding_type"] == "bypassed"
    assert captured["binding_comment"] == ""


def test_apply_device_binding_for_login_calls_post_auth_ops_with_correct_binding(monkeypatch):
    """Ketika ip_binding_enabled=True, _apply_post_auth_mikrotik_ops dipanggil dengan
    binding_type dari resolve_allowed_binding_type_for_user dan comment yang memuat uid."""
    app = Flask(__name__)
    user = SimpleNamespace(
        id="u-3",
        phone_number="+628123456789",
        role=SimpleNamespace(value="USER"),
        mikrotik_server_name="srv-user",
    )
    device = SimpleNamespace(
        mac_address="AA:BB:CC:DD:EE:FF",
        ip_address="172.16.2.10",
        is_authorized=True,
        authorized_at=None,
    )

    monkeypatch.setattr(
        dms,
        "_get_settings",
        lambda: {
            "ip_binding_enabled": True,
            "ip_binding_type_allowed": "regular",
            "ip_binding_type_blocked": "blocked",
            "ip_binding_fail_open": False,
            "dhcp_static_lease_enabled": False,
            "dhcp_lease_server_name": "",
            "device_auto_replace_enabled": False,
            "max_devices": 3,
            "require_explicit": False,
            "device_stale_days": 30,
            "mikrotik_server_default": "all",
            "global_mac_claim_transfer_enabled": False,
        },
    )
    monkeypatch.setattr(dms, "_resolve_binding_ip", lambda *_a, **_k: ("172.16.2.10", "client_ip", "ok"))
    monkeypatch.setattr(dms, "register_or_update_device", lambda *_a, **_k: (True, "Device terdaftar", device))
    monkeypatch.setattr(
        dms,
        "db",
        SimpleNamespace(session=SimpleNamespace(flush=lambda: None)),
    )
    monkeypatch.setattr(dms, "resolve_allowed_binding_type_for_user", lambda _u: "bypassed")

    captured: dict[str, Any] = {}

    def _capture_post_auth(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(dms, "_apply_post_auth_mikrotik_ops", _capture_post_auth)

    with app.app_context():
        ok, msg, resolved_ip = dms.apply_device_binding_for_login(
            cast(Any, user),
            "172.16.2.10",
            "pytest-agent",
            "AA:BB:CC:DD:EE:FF",
            bypass_explicit_auth=True,
        )

    assert ok is True
    assert msg == "Perangkat terotorisasi"
    assert resolved_ip == "172.16.2.10"
    assert captured["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert captured["ip_address"] == "172.16.2.10"
    assert captured["server"] == "srv-user"
    assert captured["username"] == "08123456789"
    assert captured["binding_type"] == "bypassed"
    assert "uid=u-3" in captured["binding_comment"]
