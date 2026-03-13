from __future__ import annotations

import app.commands.sync_unauthorized_hosts_command as cmd


def test_load_unauthorized_sync_db_state_releases_session(monkeypatch):
    settings = {
        "MIKROTIK_ADDRESS_LIST_UNAUTHORIZED": "unauthorized",
        "MIKROTIK_ADDRESS_LIST_UNAUTHORIZED_TIMEOUT": "30m",
        "MIKROTIK_ADDRESS_LIST_ACTIVE": "aktif",
        "MIKROTIK_ADDRESS_LIST_FUP": "fup",
        "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
        "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
        "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
        "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
    }

    monkeypatch.setattr(cmd.settings_service, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(
        cmd.settings_service,
        "get_setting_as_int",
        lambda key, default=0: 12 if key == "MIKROTIK_UNAUTHORIZED_MIN_UPTIME_MINUTES" else default,
    )

    class _ScalarResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return list(self._values)

    scalar_values = iter(
        [
            ["172.16.2.10", "172.16.2.11"],
            ["aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:00"],
        ]
    )
    monkeypatch.setattr(cmd.db.session, "scalars", lambda _statement: _ScalarResult(next(scalar_values)))

    removed = []
    monkeypatch.setattr(cmd.db.session, "remove", lambda: removed.append(True))

    state = cmd._load_unauthorized_sync_db_state(list_name=None, timeout=None, min_uptime_minutes=None)

    assert state.resolved_list == "unauthorized"
    assert state.resolved_timeout == "30m"
    assert state.resolved_min_uptime == 12
    assert state.status_list_names == {"aktif", "fup", "inactive", "expired", "habis", "blocked"}
    assert state.authorized_device_ips == {"172.16.2.10", "172.16.2.11"}
    assert state.authorized_device_macs == {"AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:00"}
    assert removed == [True]


def test_plan_critical_status_overlap_removals_enforces_priority():
    ip_to_lists = {
        "172.16.2.10": {"active", "fup"},
        "172.16.2.11": {"active", "blocked"},
        "172.16.2.12": {"active", "fup", "blocked"},
        "172.16.2.13": {"fup"},
    }

    plans = cmd._plan_critical_status_overlap_removals(
        ip_to_lists=ip_to_lists,
        list_active="active",
        list_fup="fup",
        list_blocked="blocked",
    )

    assert len(plans) == 4
    assert ("172.16.2.10", "active", "fup") in plans
    assert ("172.16.2.11", "active", "blocked") in plans
    assert ("172.16.2.12", "active", "blocked") in plans
    assert ("172.16.2.12", "fup", "blocked") in plans


def test_plan_critical_status_overlap_removals_ignores_single_or_unknown_lists():
    ip_to_lists = {
        "172.16.2.20": {"active"},
        "172.16.2.21": {"fup"},
        "172.16.2.22": {"blocked"},
        "172.16.2.23": {"unknown-a", "unknown-b"},
    }

    plans = cmd._plan_critical_status_overlap_removals(
        ip_to_lists=ip_to_lists,
        list_active="active",
        list_fup="fup",
        list_blocked="blocked",
    )

    assert plans == []
