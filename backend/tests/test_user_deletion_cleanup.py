from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from flask import Flask

from app.infrastructure.db.models import UserRole
from app.services.user_management import user_deletion


class _ScalarResult:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


class _Query:
    def __init__(self, deleted_count: int):
        self._deleted_count = deleted_count
        self.deleted_called = 0

    def filter(self, *args, **kwargs):
        return self

    def delete(self, synchronize_session: bool = False):
        self.deleted_called += 1
        return self._deleted_count


class _FakeSession:
    def __init__(self, *, devices: list[Any], tokens_deleted: int, devices_deleted: int):
        self._devices = devices
        self._query_map = {
            "RefreshToken": _Query(tokens_deleted),
            "UserDevice": _Query(devices_deleted),
        }
        self.deleted_objects: list[Any] = []

    def scalars(self, *args, **kwargs):
        return _ScalarResult(self._devices)

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        return self._query_map[name]

    def delete(self, obj):
        self.deleted_objects.append(obj)


class _Resource:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)
        self.removed_ids: list[str] = []

    def get(self, **query):
        if not query:
            return list(self._rows)

        result: list[dict[str, Any]] = []
        for row in self._rows:
            ok = True
            for key, value in query.items():
                if str(row.get(key, "")) != str(value):
                    ok = False
                    break
            if ok:
                result.append(row)
        return result

    def remove(self, **kwargs):
        rid = kwargs.get("id") or kwargs.get(".id")
        if rid is None:
            return
        rid = str(rid)
        self.removed_ids.append(rid)
        self._rows = [row for row in self._rows if str(row.get("id") or row.get(".id")) != rid]


class _Api:
    def __init__(self, resources: dict[str, _Resource]):
        self._resources = resources

    def get_resource(self, path: str):
        return self._resources[path]


def _make_app() -> Flask:
    return Flask(__name__)


def test_process_user_removal_soft_delete_cleans_tokens_and_sessions(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        full_name="Regular User",
        phone_number="+628123456789",
        role=UserRole.USER,
        is_admin_role=False,
        is_active=True,
        mikrotik_user_exists=True,
        mikrotik_server_name="all",
    )
    admin_actor = SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=False, is_admin_role=True)

    devices = [SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address="172.16.0.10")]
    fake_session = _FakeSession(devices=devices, tokens_deleted=2, devices_deleted=1)

    monkeypatch.setattr(user_deletion, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_deletion.settings_service, "get_setting_as_bool", lambda *args, **kwargs: False)
    monkeypatch.setattr(user_deletion, "format_to_local_phone", lambda _phone: "08123456789")
    monkeypatch.setattr(user_deletion, "_handle_mikrotik_operation", lambda *args, **kwargs: (True, "Sukses"))
    monkeypatch.setattr(user_deletion, "_log_admin_action", lambda *args, **kwargs: None)

    @contextmanager
    def _no_mikrotik(**kwargs):
        yield None

    monkeypatch.setattr(user_deletion, "get_mikrotik_connection", _no_mikrotik)

    app = _make_app()
    with app.app_context():
        success, message = user_deletion.process_user_removal(user, admin_actor)

    assert success is True
    assert "DINONAKTIFKAN" in message
    assert "Token dibersihkan: 2" in message
    assert "Session device dibersihkan: 1" in message
    assert "MikroTik tidak terhubung" in message
    assert user.is_active is False
    assert user.mikrotik_user_exists is False
    assert fake_session._query_map["RefreshToken"].deleted_called == 1
    assert fake_session._query_map["UserDevice"].deleted_called == 1


def test_process_user_removal_hard_delete_cleans_router_artifacts(monkeypatch):
    user_id = uuid.uuid4()
    uid_marker = f"uid={user_id}"
    user08 = "08123456789"

    user = SimpleNamespace(
        id=user_id,
        full_name="Target User",
        phone_number="+628123456789",
        role=UserRole.USER,
        is_admin_role=False,
        is_active=True,
        mikrotik_user_exists=True,
        mikrotik_server_name="all",
    )
    admin_actor = SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=True, is_admin_role=True)

    devices = [SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address="172.16.0.10")]
    fake_session = _FakeSession(devices=devices, tokens_deleted=1, devices_deleted=1)
    monkeypatch.setattr(user_deletion, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_deletion.settings_service, "get_setting_as_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(user_deletion.settings_service, "get_setting", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(user_deletion, "format_to_local_phone", lambda _phone: user08)

    call_tracker = {"hotspot_delete_called": 0, "log_details": None}

    def _mikrotik_success(operation_func, **kwargs):
        call_tracker["hotspot_delete_called"] += 1
        assert "username" in kwargs
        return True, "Sukses"

    def _capture_log(_admin, _target, _action, details):
        call_tracker["log_details"] = details

    monkeypatch.setattr(user_deletion, "_handle_mikrotik_operation", _mikrotik_success)
    monkeypatch.setattr(user_deletion, "_log_admin_action", _capture_log)

    resources = {
        "/ip/hotspot/active": _Resource(
            [
                {"id": "ha1", "mac-address": "AA:BB:CC:DD:EE:FF"},
                {"id": "ha2", "comment": f"lpsaring|{uid_marker}|user={user08}"},
            ]
        ),
        "/ip/hotspot/host": _Resource(
            [
                {"id": "hh1", "mac-address": "AA:BB:CC:DD:EE:FF", "address": "172.16.0.10"},
                {"id": "hh2", "comment": f"legacy|{uid_marker}"},
            ]
        ),
        "/ip/hotspot/ip-binding": _Resource(
            [
                {"id": "b1", "mac-address": "AA:BB:CC:DD:EE:FF"},
                {"id": "b2", "comment": f"lpsaring|user={user08}"},
            ]
        ),
        "/ip/dhcp-server/lease": _Resource(
            [
                {"id": "l1", "mac-address": "AA:BB:CC:DD:EE:FF"},
                {"id": "l2", "comment": f"legacy|{uid_marker}"},
            ]
        ),
        "/ip/arp": _Resource(
            [
                {"id": "a1", "address": "172.16.0.10", "mac-address": "AA:BB:CC:DD:EE:FF"},
                {"id": "a2", "comment": f"lpsaring|user={user08}"},
            ]
        ),
        "/ip/firewall/address-list": _Resource(
            [
                {"id": "f1", "list": "blocked", "address": "172.16.0.10"},
                {"id": "f2", "list": "active", "comment": f"lpsaring|{uid_marker}"},
                {"id": "f3", "list": "manual", "comment": f"lpsaring|{uid_marker}"},
            ]
        ),
    }
    api = _Api(resources)

    @contextmanager
    def _mikrotik_ok(**kwargs):
        yield api

    monkeypatch.setattr(user_deletion, "get_mikrotik_connection", _mikrotik_ok)

    app = _make_app()
    with app.app_context():
        success, message = user_deletion.process_user_removal(user, admin_actor)

    assert success is True
    assert "DIHAPUS secara permanen" in message
    assert "Token dibersihkan: 1" in message
    assert call_tracker["hotspot_delete_called"] == 1
    assert user in fake_session.deleted_objects

    assert "ha1" in resources["/ip/hotspot/active"].removed_ids
    assert "hh1" in resources["/ip/hotspot/host"].removed_ids
    assert "b1" in resources["/ip/hotspot/ip-binding"].removed_ids
    assert "l1" in resources["/ip/dhcp-server/lease"].removed_ids
    assert "a1" in resources["/ip/arp"].removed_ids
    assert "f1" in resources["/ip/firewall/address-list"].removed_ids

    log_details = call_tracker["log_details"]
    assert isinstance(log_details, dict)
    assert log_details["tokens_deleted"] == 1
    assert log_details["devices_deleted"] == 1
    assert log_details["router_cleanup"]["mikrotik_connected"] is True
    assert log_details["router_cleanup"]["comment_tagged_entries_removed"] >= 1
