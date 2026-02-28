from contextlib import contextmanager
from types import SimpleNamespace

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
        yield object()

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

    summary = reset_user_network_on_logout(user)

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

    summary = reset_user_network_on_logout(user)

    assert summary["mikrotik_ops_enabled"] is False
    assert summary["devices_seen"] == 0
