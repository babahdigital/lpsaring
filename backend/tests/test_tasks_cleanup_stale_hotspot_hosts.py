from __future__ import annotations

from contextlib import contextmanager

from flask import Flask

import app.tasks as tasks


class _Resource:
    def __init__(self, rows):
        self.rows = list(rows)
        self.removed_ids: list[str] = []

    def get(self, **kwargs):
        if not kwargs:
            return list(self.rows)
        result = []
        for row in self.rows:
            ok = True
            for key, value in kwargs.items():
                if str(row.get(key)) != str(value):
                    ok = False
                    break
            if ok:
                result.append(row)
        return result

    def remove(self, **kwargs):
        row_id = kwargs.get("id")
        self.removed_ids.append(str(row_id))
        self.rows = [row for row in self.rows if str(row.get(".id") or row.get("id")) != str(row_id)]


class _Api:
    def __init__(self, resources):
        self.resources = resources

    def get_resource(self, path: str):
        return self.resources[path]


@contextmanager
def _api_context(api):
    yield api


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="unit-test-secret",
        ENABLE_MIKROTIK_OPERATIONS=True,
        HOTSPOT_CLIENT_IP_CIDRS=["172.16.2.0/23"],
        AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_ENABLED=True,
        AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_INTERVAL_SECONDS=1800,
        AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_MIN_IDLE_SECONDS=3600,
    )
    return app


def test_cleanup_stale_hotspot_hosts_task_removes_ghost_bypassed_host(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)

    hosts = _Resource(
        [
            {
                ".id": "h-ghost",
                "address": "154.30.75.26",
                "to-address": "154.30.75.26",
                "mac-address": "66:93:21:1F:07:B5",
                "server": "srv-user",
                "bypassed": "true",
                "idle-time": "3d8h53m40s",
                "comment": "authorized|user=082156121681|uid=u-1",
            },
            {
                ".id": "h-current",
                "address": "172.16.2.190",
                "to-address": "172.16.2.190",
                "mac-address": "66:93:21:1F:07:B5",
                "server": "srv-user",
                "bypassed": "true",
                "idle-time": "1s",
                "comment": "authorized|user=082156121681|uid=u-1",
            },
            {
                ".id": "h-translated",
                "address": "192.168.0.137",
                "to-address": "172.16.2.213",
                "mac-address": "F6:75:0C:85:0E:BD",
                "server": "srv-user",
                "bypassed": "false",
                "idle-time": "5d19h48m3s",
                "comment": None,
            },
        ]
    )
    arp = _Resource(
        [
            {
                ".id": "a-1",
                "address": "172.16.2.190",
                "mac-address": "66:93:21:1F:07:B5",
            }
        ]
    )
    leases = _Resource(
        [
            {
                ".id": "l-1",
                "address": "172.16.2.190",
                "mac-address": "66:93:21:1F:07:B5",
                "status": "bound",
            }
        ]
    )
    api = _Api(
        {
            "/ip/hotspot/host": hosts,
            "/ip/arp": arp,
            "/ip/dhcp-server/lease": leases,
        }
    )
    monkeypatch.setattr(tasks, "get_mikrotik_connection", lambda: _api_context(api))

    result = tasks.cleanup_stale_hotspot_hosts_task.run()

    assert result["removed"] == 1
    assert result["skipped_in_subnet"] == 1
    assert result["skipped_translated"] == 1
    assert hosts.removed_ids == ["h-ghost"]


def test_cleanup_stale_hotspot_hosts_task_skips_recent_or_unproven_rows(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)

    hosts = _Resource(
        [
            {
                ".id": "h-current",
                "address": "172.16.2.63",
                "to-address": "172.16.2.63",
                "mac-address": "2E:96:F8:D4:90:2E",
                "server": "srv-user",
                "bypassed": "true",
                "idle-time": "0s",
                "comment": "authorized|user=083869831957|uid=u-2",
            },
            {
                ".id": "h-recent",
                "address": "10.8.0.136",
                "to-address": "10.8.0.136",
                "mac-address": "2E:96:F8:D4:90:2E",
                "server": "srv-user",
                "bypassed": "true",
                "idle-time": "5m",
                "comment": "authorized|user=083869831957|uid=u-2",
            },
            {
                ".id": "h-no-local",
                "address": "10.8.0.141",
                "to-address": "10.8.0.141",
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "server": "srv-user",
                "bypassed": "true",
                "idle-time": "2d",
                "comment": "authorized|user=083869831957|uid=u-3",
            },
            {
                ".id": "h-not-bypassed",
                "address": "10.8.0.137",
                "to-address": "10.8.0.137",
                "mac-address": "2E:96:F8:D4:90:2E",
                "server": "srv-user",
                "bypassed": "false",
                "idle-time": "2d",
                "comment": None,
            },
        ]
    )
    arp = _Resource(
        [
            {
                ".id": "a-1",
                "address": "172.16.2.63",
                "mac-address": "2E:96:F8:D4:90:2E",
            }
        ]
    )
    leases = _Resource([])
    api = _Api(
        {
            "/ip/hotspot/host": hosts,
            "/ip/arp": arp,
            "/ip/dhcp-server/lease": leases,
        }
    )
    monkeypatch.setattr(tasks, "get_mikrotik_connection", lambda: _api_context(api))

    result = tasks.cleanup_stale_hotspot_hosts_task.run()

    assert result["removed"] == 0
    assert result["skipped_in_subnet"] == 1
    assert result["skipped_recent"] == 1
    assert result["skipped_no_current_host"] == 1
    assert result["skipped_not_bypassed"] == 1
    assert hosts.removed_ids == []