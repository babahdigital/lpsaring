from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

from flask import Flask

from app.infrastructure.http.admin import user_management_routes
from app.infrastructure.db.models import User


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Query:
    def __init__(self, deleted_count: int):
        self._deleted_count = deleted_count

    def filter(self, *args, **kwargs):
        return self

    def delete(self, synchronize_session: bool = False):
        return self._deleted_count


class _FakeSession:
    def __init__(self, *, user: Any, devices: list[Any], tokens_deleted: int, devices_deleted: int):
        self._user = user
        self._devices = devices
        self._tokens_deleted = tokens_deleted
        self._devices_deleted = devices_deleted
        self._commit_called = 0
        self._rollback_called = 0

    def get(self, model, user_id):
        if model is User and getattr(self._user, "id", None) == user_id:
            return self._user
        return None

    def scalars(self, *args, **kwargs):
        return _ScalarResult(self._devices)

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "RefreshToken":
            return _Query(self._tokens_deleted)
        if name == "UserDevice":
            return _Query(self._devices_deleted)
        return _Query(0)

    def commit(self):
        self._commit_called += 1

    def rollback(self):
        self._rollback_called += 1


class _Resource:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)
        self.removed_ids: list[str] = []

    def get(self, **query):
        if not query:
            return list(self._rows)
        result = []
        for row in self._rows:
            ok = True
            for key, value in query.items():
                if str(row.get(key, "")) != str(value):
                    ok = False
                    break
            if ok:
                result.append(row)
        return result

    def remove(self, id: str):
        self.removed_ids.append(str(id))
        self._rows = [r for r in self._rows if str(r.get("id") or r.get(".id")) != str(id)]


class _Api:
    def __init__(self, resources: dict[str, _Resource]):
        self._resources = resources

    def get_resource(self, path: str):
        return self._resources[path]


def _make_app() -> Flask:
    return Flask(__name__)


def test_reset_login_deletes_tokens_and_devices_even_when_mikrotik_unavailable(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, phone_number="+628123456789", role=SimpleNamespace(value="USER"))

    fake_session = _FakeSession(user=user, devices=[], tokens_deleted=3, devices_deleted=2)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))

    @contextmanager
    def _no_mikrotik(**kwargs):
        yield None

    monkeypatch.setattr(user_management_routes, "get_mikrotik_connection", _no_mikrotik)
    monkeypatch.setattr(user_management_routes, "_log_admin_action", lambda **kwargs: None)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.admin_reset_user_login)

    with app.test_request_context(f"/api/admin/users/{user_id}/reset-login", method="POST"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    payload = response.get_json()
    assert payload["summary"]["tokens_deleted"] == 3
    assert payload["summary"]["devices_deleted"] == 2
    assert payload["summary"]["router"]["mikrotik_connected"] is False


def test_reset_login_removes_comment_tagged_router_entries(monkeypatch):
    user_id = uuid.uuid4()
    uid_marker = f"uid={user_id}"
    user08 = "08123456789"

    user = SimpleNamespace(id=user_id, phone_number="+628123456789", role=SimpleNamespace(value="USER"))
    devices = [SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address="172.16.0.10")]

    fake_session = _FakeSession(user=user, devices=devices, tokens_deleted=1, devices_deleted=1)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_log_admin_action", lambda **kwargs: None)
    monkeypatch.setattr(user_management_routes, "format_to_local_phone", lambda _: user08)
    monkeypatch.setattr(user_management_routes.settings_service, "get_setting", lambda *args, **kwargs: args[1])

    resources = {
        "/ip/hotspot/ip-binding": _Resource(
            [
                {"id": "b1", "mac-address": "AA:BB:CC:DD:EE:FF", "comment": f"lpsaring | {uid_marker} | user={user08}"},
                {"id": "b2", "mac-address": "11:22:33:44:55:66", "comment": "manual"},
            ]
        ),
        "/ip/dhcp-server/lease": _Resource(
            [
                {"id": "l1", "mac-address": "AA:BB:CC:DD:EE:FF"},
                {"id": "l2", "mac-address": "11:22:33:44:55:66"},
                {"id": "l3", "mac-address": "66:55:44:33:22:11", "comment": f"legacy|{uid_marker}"},
            ]
        ),
        "/ip/arp": _Resource(
            [
                {"id": "p1", "mac-address": "AA:BB:CC:DD:EE:FF", "address": "172.16.0.10"},
                {"id": "p2", "mac-address": "11:22:33:44:55:66", "address": "172.16.0.20"},
                {"id": "p3", "address": "172.16.0.77", "comment": f"lpsaring|user={user08}"},
            ]
        ),
        "/ip/firewall/address-list": _Resource(
            [
                {
                    "id": "f1",
                    "list": "blocked",
                    "address": "172.16.0.10",
                    "comment": f"lpsaring|{uid_marker}|user={user08}",
                },
                {"id": "f2", "list": "active", "address": "172.16.0.99", "comment": f"lpsaring|{uid_marker}"},
                {"id": "f3", "list": "blocked", "address": "172.16.0.20", "comment": "other"},
            ]
        ),
    }

    api = _Api(resources)

    @contextmanager
    def _mikrotik_ok(**kwargs):
        yield api

    monkeypatch.setattr(user_management_routes, "get_mikrotik_connection", _mikrotik_ok)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.admin_reset_user_login)

    with app.test_request_context(f"/api/admin/users/{user_id}/reset-login", method="POST"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    payload = response.get_json()["summary"]
    assert payload["router"]["mikrotik_connected"] is True

    # Comment-tagged removals are tracked
    assert payload["router"]["comment_tagged_entries_removed"] >= 1

    # Ensure at least the matching items are removed in resources
    assert "b1" in resources["/ip/hotspot/ip-binding"].removed_ids
    assert "l1" in resources["/ip/dhcp-server/lease"].removed_ids
    assert "l3" in resources["/ip/dhcp-server/lease"].removed_ids
    assert "p1" in resources["/ip/arp"].removed_ids
    assert "p3" in resources["/ip/arp"].removed_ids
    assert "f1" in resources["/ip/firewall/address-list"].removed_ids
    assert "f2" in resources["/ip/firewall/address-list"].removed_ids


def test_reset_login_denies_non_super_admin_for_demo_user(monkeypatch):
    user_id = uuid.uuid4()
    demo_phone = "081234567890"
    user = SimpleNamespace(
        id=user_id,
        phone_number=demo_phone,
        full_name="Regular Name",
        role=SimpleNamespace(value="USER"),
    )

    fake_session = _FakeSession(user=user, devices=[], tokens_deleted=0, devices_deleted=0)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))

    app = _make_app()
    app.config["DEMO_ALLOWED_PHONES"] = [demo_phone]
    impl = _unwrap_decorators(user_management_routes.admin_reset_user_login)

    with app.test_request_context(f"/api/admin/users/{user_id}/reset-login", method="POST"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=False))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 403
    assert response.get_json()["message"] == "Akses ditolak."
