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
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


def test_cleanup_waiting_dhcp_arp_task_removes_waiting_and_linked_arp(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)

    def _get_setting(key, default=None):
        values = {
            "ENABLE_MIKROTIK_OPERATIONS": "True",
            "AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED": "True",
            "AUTO_CLEANUP_WAITING_DHCP_ARP_COMMENT_KEYWORD": "lpsaring|static-dhcp",
        }
        return values.get(key, default)

    monkeypatch.setattr(tasks.settings_service, "get_setting", _get_setting)
    monkeypatch.setattr(tasks.settings_service, "get_setting_as_int", lambda key, default=0: 0)

    leases = _Resource(
        [
            {
                ".id": "l-1",
                "status": "waiting",
                "comment": "lpsaring|static-dhcp|uid=u1",
                "address": "172.16.2.10",
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "last-seen": "1d2h",
            },
            {
                ".id": "l-2",
                "status": "bound",
                "comment": "lpsaring|static-dhcp|uid=u1",
                "address": "172.16.2.11",
                "mac-address": "11:22:33:44:55:66",
                "last-seen": "10m",
            },
        ]
    )
    arp = _Resource(
        [
            {
                ".id": "a-1",
                "address": "172.16.2.10",
                "mac-address": "AA:BB:CC:DD:EE:FF",
            },
            {
                ".id": "a-2",
                "address": "172.16.2.22",
                "mac-address": "22:33:44:55:66:77",
            },
        ]
    )
    api = _Api(
        {
            "/ip/dhcp-server/lease": leases,
            "/ip/arp": arp,
        }
    )
    monkeypatch.setattr(tasks, "get_mikrotik_connection", lambda: _api_context(api))

    tasks.cleanup_waiting_dhcp_arp_task.run()

    assert leases.removed_ids == ["l-1"]
    assert arp.removed_ids == ["a-1"]


def test_cleanup_waiting_dhcp_arp_task_skips_when_feature_disabled(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)

    def _get_setting(key, default=None):
        values = {
            "ENABLE_MIKROTIK_OPERATIONS": "True",
            "AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED": "False",
        }
        return values.get(key, default)

    monkeypatch.setattr(tasks.settings_service, "get_setting", _get_setting)

    called = {"value": False}

    @contextmanager
    def _unexpected_api_context():
        called["value"] = True
        yield object()

    monkeypatch.setattr(tasks, "get_mikrotik_connection", _unexpected_api_context)

    tasks.cleanup_waiting_dhcp_arp_task.run()

    assert called["value"] is False
