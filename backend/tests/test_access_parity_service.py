from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.services import access_parity_service


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResource:
    def __init__(self, rows):
        self._rows = rows

    def get(self, **_kwargs):
        return list(self._rows)


class _FakeApi:
    def __init__(self, dhcp_rows=None):
        self._dhcp_rows = dhcp_rows or []

    def get_resource(self, path):
        if path == "/ip/dhcp-server/lease":
            return _FakeResource(self._dhcp_rows)
        raise AssertionError(f"Unexpected API resource path: {path}")


def _setup_common_mocks(monkeypatch, users, *, host_map=None, binding_map=None, dhcp_rows=None):
    fake_db = SimpleNamespace(session=SimpleNamespace(scalars=lambda *_args, **_kwargs: _ScalarResult(users)))
    monkeypatch.setattr(access_parity_service, "db", fake_db)

    monkeypatch.setattr(access_parity_service.settings_service, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "active")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "regular")

    monkeypatch.setattr(
        access_parity_service,
        "get_hotspot_host_usage_map",
        lambda _api: (True, host_map or {}, "ok"),
    )
    monkeypatch.setattr(
        access_parity_service,
        "get_hotspot_ip_binding_user_map",
        lambda _api: (True, binding_map or {}, "ok"),
    )
    monkeypatch.setattr(
        access_parity_service,
        "get_firewall_address_list_entries",
        lambda _api, _list_name: (True, [], "ok"),
    )

    fake_api = _FakeApi(dhcp_rows=dhcp_rows)

    @contextmanager
    def _fake_conn():
        yield fake_api

    monkeypatch.setattr(access_parity_service, "get_mikrotik_connection", _fake_conn)


def test_collect_access_parity_report_flags_user_without_authorized_device(monkeypatch):
    user = SimpleNamespace(id="user-1", phone_number="+628111111111", devices=[])
    _setup_common_mocks(monkeypatch, [user])

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert report["summary"]["mismatch_types"]["no_authorized_device"] == 1
    assert len(report["items"]) == 1

    item = report["items"][0]
    assert item["mismatches"] == ["no_authorized_device"]
    assert item["auto_fixable"] is False


def test_collect_access_parity_report_flags_no_ip_binding_and_dhcp_gap(monkeypatch):
    device = SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address=None, is_authorized=True)
    user = SimpleNamespace(id="user-2", phone_number="+628122222222", devices=[device])
    _setup_common_mocks(monkeypatch, [user], host_map={}, binding_map={}, dhcp_rows=[])

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert len(report["items"]) == 1

    item = report["items"][0]
    assert set(item["mismatches"]) == {"dhcp_lease_missing", "missing_ip_binding", "no_resolvable_ip"}
    assert item["auto_fixable"] is False
    assert any(action["action"] == "resolve_ip_from_host_or_binding" for action in item["action_plan"])

    mismatch_types = report["summary"]["mismatch_types"]
    assert mismatch_types["missing_ip_binding"] == 1
    assert mismatch_types["no_resolvable_ip"] == 1
    assert mismatch_types["dhcp_lease_missing"] == 1
