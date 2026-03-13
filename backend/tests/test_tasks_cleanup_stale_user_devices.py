from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from flask import Flask

import app.tasks as tasks


@contextmanager
def _api_context(api):
    yield api


class _FakeQuery:
    def options(self, *_args, **_kwargs):
        return self


class _FakeSession:
    def __init__(self, devices):
        self.devices = list(devices)
        self.deleted = []
        self.commit_calls = 0

    def scalars(self, _query):
        return SimpleNamespace(all=lambda: list(self.devices))

    def delete(self, device):
        self.deleted.append(device)
        self.devices.remove(device)

    def commit(self):
        self.commit_calls += 1


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="unit-test-secret",
        ENABLE_MIKROTIK_OPERATIONS=True,
        AUTO_CLEANUP_STALE_USER_DEVICES_ENABLED=True,
        AUTO_CLEANUP_STALE_USER_DEVICES_INTERVAL_SECONDS=3600,
        DEVICE_STALE_DAYS=30,
    )
    return app


def _patch_settings(monkeypatch):
    def _get_setting(key, default=None):
        values = {
            "MIKROTIK_DHCP_STATIC_LEASE_ENABLED": "True",
            "MIKROTIK_DHCP_LEASE_SERVER_NAME": "Klien",
            "MIKROTIK_DEFAULT_SERVER_USER": "all",
            "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
            "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
            "MIKROTIK_ADDRESS_LIST_FUP": "fup",
            "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
            "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
            "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
        }
        return values.get(key, default)

    monkeypatch.setattr(tasks.settings_service, "get_setting", _get_setting)


def test_cleanup_stale_user_devices_task_prunes_router_inactive_device(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)
    _patch_settings(monkeypatch)

    user = SimpleNamespace(
        id=uuid4(),
        phone_number="+628123456789",
        mikrotik_server_name="srv-user",
    )
    now = datetime.now(timezone.utc)
    device = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        user=user,
        mac_address="AA:BB:CC:DD:EE:01",
        ip_address="172.16.2.11",
        last_bytes_updated_at=now - timedelta(days=31),
        last_seen_at=now - timedelta(days=40),
        authorized_at=now - timedelta(days=45),
        first_seen_at=now - timedelta(days=60),
    )
    fake_session = _FakeSession([device])
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=fake_session, select=lambda *_args, **_kwargs: _FakeQuery()))
    api = object()
    monkeypatch.setattr(tasks, "get_mikrotik_connection", lambda: _api_context(api))
    monkeypatch.setattr(tasks, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))

    removed_bindings = []
    removed_address_lists = []
    removed_leases = []
    removed_hosts = []

    monkeypatch.setattr(
        tasks,
        "remove_ip_binding",
        lambda **kwargs: (removed_bindings.append(kwargs), (True, "ok"))[1],
    )
    monkeypatch.setattr(
        tasks,
        "remove_address_list_entry",
        lambda **kwargs: (removed_address_lists.append(kwargs), (True, "ok"))[1],
    )
    monkeypatch.setattr(
        tasks,
        "remove_dhcp_lease",
        lambda **kwargs: (removed_leases.append(kwargs), (True, "ok"))[1],
    )
    monkeypatch.setattr(
        tasks,
        "remove_hotspot_host_entries_best_effort",
        lambda **kwargs: (removed_hosts.append(kwargs), (True, "ok", 0))[1],
    )

    result = tasks.cleanup_stale_user_devices_task.run()

    assert result["deleted"] == 1
    assert result["deleted_from_last_bytes_updated_at"] == 1
    assert fake_session.deleted == [device]
    assert fake_session.commit_calls == 1
    assert removed_bindings == [
        {
            "api_connection": api,
            "mac_address": "AA:BB:CC:DD:EE:01",
            "server": "srv-user",
        }
    ]
    assert [entry["list_name"] for entry in removed_address_lists] == [
        "blocked",
        "active",
        "fup",
        "habis",
        "expired",
        "inactive",
    ]
    assert removed_leases == [
        {
            "api_connection": api,
            "mac_address": "AA:BB:CC:DD:EE:01",
            "server": "Klien",
        }
    ]
    assert removed_hosts == [
        {
            "api_connection": api,
            "mac_address": "AA:BB:CC:DD:EE:01",
            "address": "172.16.2.11",
            "username": "08123456789",
            "allow_username_only_fallback": False,
        }
    ]


def test_cleanup_stale_user_devices_task_skips_active_router_host(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)
    _patch_settings(monkeypatch)

    user = SimpleNamespace(
        id=uuid4(),
        phone_number="+628123456789",
        mikrotik_server_name="srv-user",
    )
    now = datetime.now(timezone.utc)
    device = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        user=user,
        mac_address="AA:BB:CC:DD:EE:02",
        ip_address="172.16.2.12",
        last_bytes_updated_at=now - timedelta(days=31),
        last_seen_at=now - timedelta(days=31),
        authorized_at=now - timedelta(days=31),
        first_seen_at=now - timedelta(days=60),
    )
    fake_session = _FakeSession([device])
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=fake_session, select=lambda *_args, **_kwargs: _FakeQuery()))
    api = object()
    monkeypatch.setattr(tasks, "get_mikrotik_connection", lambda: _api_context(api))
    monkeypatch.setattr(
        tasks,
        "get_hotspot_host_usage_map",
        lambda _api: (True, {"AA:BB:CC:DD:EE:02": {"address": "172.16.2.12"}}, "ok"),
    )

    cleanup_calls = {"count": 0}
    monkeypatch.setattr(tasks, "remove_ip_binding", lambda **_kwargs: (cleanup_calls.__setitem__("count", cleanup_calls["count"] + 1), (True, "ok"))[1])
    monkeypatch.setattr(tasks, "remove_address_list_entry", lambda **_kwargs: (cleanup_calls.__setitem__("count", cleanup_calls["count"] + 1), (True, "ok"))[1])
    monkeypatch.setattr(tasks, "remove_dhcp_lease", lambda **_kwargs: (cleanup_calls.__setitem__("count", cleanup_calls["count"] + 1), (True, "ok"))[1])
    monkeypatch.setattr(tasks, "remove_hotspot_host_entries_best_effort", lambda **_kwargs: (cleanup_calls.__setitem__("count", cleanup_calls["count"] + 1), (True, "ok", 0))[1])

    result = tasks.cleanup_stale_user_devices_task.run()

    assert result["stale_candidates"] == 1
    assert result["skipped_active_host"] == 1
    assert result["deleted"] == 0
    assert fake_session.deleted == []
    assert fake_session.commit_calls == 0
    assert cleanup_calls["count"] == 0