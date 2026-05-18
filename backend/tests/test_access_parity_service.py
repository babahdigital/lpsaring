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


def _setup_common_mocks(
    monkeypatch,
    users,
    *,
    host_map=None,
    binding_map=None,
    dhcp_rows=None,
    firewall_entries_by_list=None,
):
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
        lambda _api, _list_name: (True, (firewall_entries_by_list or {}).get(_list_name, []), "ok"),
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
    assert report["summary"]["mismatches"] == 0
    assert report["summary"]["mismatches_total"] == 1
    assert report["summary"]["non_parity_mismatches"] == 1
    assert report["summary"]["no_authorized_device_count"] == 1
    assert len(report["items"]) == 1

    item = report["items"][0]
    assert item["mismatches"] == ["no_authorized_device"]
    assert item["parity_relevant"] is False
    assert item["auto_fixable"] is False


def test_collect_access_parity_report_flags_no_ip_binding_and_dhcp_gap(monkeypatch):
    device = SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address=None, is_authorized=True)
    user = SimpleNamespace(id="user-2", phone_number="+628122222222", devices=[device])
    _setup_common_mocks(monkeypatch, [user], host_map={}, binding_map={}, dhcp_rows=[])

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert len(report["items"]) == 1
    assert report["summary"]["mismatches"] == 1
    assert report["summary"]["mismatches_total"] == 1
    assert report["summary"]["non_parity_mismatches"] == 0
    assert report["summary"]["no_authorized_device_count"] == 0

    item = report["items"][0]
    # dhcp_lease_missing is NOT expected: device is offline (not in host table),
    # so DHCP check is intentionally skipped to avoid permanent false positives.
    assert set(item["mismatches"]) == {"missing_ip_binding", "no_resolvable_ip"}
    assert item["parity_relevant"] is True
    assert item["auto_fixable"] is False
    assert any(action["action"] == "resolve_ip_from_host_or_binding" for action in item["action_plan"])

    mismatch_types = report["summary"]["mismatch_types"]
    assert mismatch_types["missing_ip_binding"] == 1
    assert mismatch_types["no_resolvable_ip"] == 1
    assert mismatch_types.get("dhcp_lease_missing", 0) == 0


def test_collect_access_parity_report_ignores_missing_dhcp_for_blocked_hard_block(monkeypatch):
    mac = "3E:8E:E6:63:D1:8C"
    ip = "172.16.2.206"
    device = SimpleNamespace(mac_address=mac, ip_address=ip, is_authorized=True)
    user = SimpleNamespace(id="blocked-user", phone_number="+6283854110679", devices=[device])

    _setup_common_mocks(
        monkeypatch,
        [user],
        host_map={mac: {"address": ip}},
        binding_map={mac: {"type": "blocked", "address": ip}},
        dhcp_rows=[],
        firewall_entries_by_list={"blocked": [{"address": ip}]},
    )
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "blocked")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "blocked")

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert report["items"] == []
    assert report["summary"]["mismatches"] == 0
    assert report["summary"]["mismatches_total"] == 0
    assert report["summary"]["mismatch_types"]["dhcp_lease_missing"] == 0


def test_collect_access_parity_report_skips_dhcp_missing_when_live_host_signal_exists(monkeypatch):
    mac = "74:D5:58:53:90:3F"
    ip = "172.16.3.79"
    device = SimpleNamespace(mac_address=mac, ip_address=ip, is_authorized=True)
    user = SimpleNamespace(id="live-host-user", phone_number="+6282159997961", devices=[device])

    _setup_common_mocks(
        monkeypatch,
        [user],
        host_map={mac: {"address": ip}},
        binding_map={mac: {"type": "bypassed", "address": ip}},
        dhcp_rows=[],
        firewall_entries_by_list={"active": [{"address": ip}]},
    )
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "active")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "bypassed")

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert report["items"] == []
    assert report["summary"]["mismatches"] == 0
    assert report["summary"]["mismatch_types"]["dhcp_lease_missing"] == 0


def test_collect_access_parity_report_treats_dhcp_only_mismatch_as_non_parity(monkeypatch):
    """dhcp_lease_missing is non-parity when it is the sole mismatch.

    Scenario: device is currently online (present in hotspot host table) but with a
    different IP than the one stored in the DB (e.g. after a DHCP reassignment). The
    ip-binding is correct, but no static DHCP lease exists for the DB address. The
    mismatch is purely administrative and does not affect current connectivity, so
    parity_relevant must be False.

    Note: dhcp_lease_missing is intentionally NOT flagged for offline devices (host_ip
    is None) to avoid permanent false positives for bypassed users who are not
    currently connected.
    """
    mac = "84:14:4D:8F:19:CA"
    ip = "172.16.3.138"
    ip_live = "172.16.3.100"  # device is online but with a different IP than DB record
    device = SimpleNamespace(mac_address=mac, ip_address=ip, is_authorized=True)
    user = SimpleNamespace(id="dhcp-only-user", phone_number="+6282113301370", devices=[device])

    _setup_common_mocks(
        monkeypatch,
        [user],
        host_map={mac: {"address": ip_live}},  # online with different IP → triggers DHCP check
        binding_map={mac: {"type": "bypassed", "address": ip}},
        dhcp_rows=[],
        firewall_entries_by_list={"active": [{"address": ip}]},
    )
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "active")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "bypassed")

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    assert len(report["items"]) == 1
    item = report["items"][0]
    assert item["mismatches"] == ["dhcp_lease_missing"]
    assert item["parity_relevant"] is False

    assert report["summary"]["mismatches"] == 0
    assert report["summary"]["mismatches_total"] == 1
    assert report["summary"]["non_parity_mismatches"] == 1
    assert report["summary"]["mismatch_types"]["dhcp_lease_missing"] == 1


def test_collect_access_parity_report_no_dhcp_mismatch_for_waiting_static_lease(monkeypatch):
    """Regression: "waiting" DHCP static lease must count as present — not as missing.

    Scenario: parity-guard previously wrote a static DHCP lease for the device's
    live IP. RouterOS reports this lease as status="waiting" because the client
    hasn't yet renewed its DHCP lease from the hotspot server (it's using a DHCP
    IP from before the static lease was written). The old code skipped "waiting"
    leases unconditionally, so the very lease we wrote was invisible → parity-guard
    flagged dhcp_lease_missing again → wrote the same lease → infinite loop.

    After the fix: "waiting" leases are counted as present; only "offered" (ephemeral
    in-flight) and "expired" (lapsed dynamic) leases are skipped.
    """
    mac = "F6:75:0C:85:0E:BE"
    ip_db = "172.16.3.174"  # stale IP stored in DB
    ip_live = "172.16.3.184"  # current live IP from host table (device has new DHCP IP)
    device = SimpleNamespace(mac_address=mac, ip_address=ip_db, is_authorized=True)
    user = SimpleNamespace(id="waiting-lease-user", phone_number="+6283852923433", devices=[device])

    # The parity-guard previously wrote a static lease for ip_live with status=waiting.
    dhcp_rows = [
        {"mac-address": mac, "address": ip_live, "status": "waiting", "dynamic": "false"},
    ]
    _setup_common_mocks(
        monkeypatch,
        [user],
        host_map={mac: {"address": ip_live}},  # device is online with ip_live
        binding_map={mac: {"type": "bypassed", "address": None}},
        dhcp_rows=dhcp_rows,
        firewall_entries_by_list={"active": [{"address": ip_db}]},
    )
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "active")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "bypassed")

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    # Static DHCP lease in "waiting" state IS a configured lease → no dhcp_lease_missing
    assert report["summary"]["mismatch_types"].get("dhcp_lease_missing", 0) == 0
    # No parity mismatches (ip-binding is correct, firewall list is correct)
    assert report["summary"]["mismatches"] == 0


def test_collect_access_parity_report_no_dhcp_mismatch_for_offline_bypassed_user(monkeypatch):
    """Regression test: offline bypassed users must NOT produce dhcp_lease_missing.

    This was a performance bug: 31 offline bypassed users were flagged every 10 min
    because host_ip=None caused _has_live_host_ip_signal to return False regardless
    of the DHCP state. The fix adds `if host_ip and` to skip the DHCP check entirely
    when the device is not present in the hotspot host table.
    """
    mac = "AA:11:BB:22:CC:33"
    ip = "172.16.3.50"
    device = SimpleNamespace(mac_address=mac, ip_address=ip, is_authorized=True)
    user = SimpleNamespace(id="offline-bypass", phone_number="+6281200001234", devices=[device])

    _setup_common_mocks(
        monkeypatch,
        [user],
        host_map={},  # device NOT in host table → offline
        binding_map={mac: {"type": "bypassed", "address": ip}},
        dhcp_rows=[],  # no static DHCP lease
        firewall_entries_by_list={"active": [{"address": ip}]},
    )
    monkeypatch.setattr(access_parity_service, "get_user_access_status", lambda _user: "active")
    monkeypatch.setattr(access_parity_service, "resolve_allowed_binding_type_for_user", lambda _user: "bypassed")

    report = access_parity_service.collect_access_parity_report()

    assert report["ok"] is True
    # Offline device with correct ip-binding → no mismatches at all
    assert report["items"] == []
    assert report["summary"]["mismatches"] == 0
    assert report["summary"]["mismatches_total"] == 0
    assert report["summary"]["mismatch_types"].get("dhcp_lease_missing", 0) == 0
