from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.http.admin import user_management_routes
from app.infrastructure.db.models import User


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeSession:
    def __init__(self, *, user):
        self._user = user
        self._commit_called = 0
        self._rollback_called = 0

    def get(self, model, user_id):
        if model is User and getattr(self._user, "id", None) == user_id:
            return self._user
        return None

    def commit(self):
        self._commit_called += 1

    def rollback(self):
        self._rollback_called += 1


def _make_app() -> Flask:
    return Flask(__name__)


def test_reset_login_deletes_tokens_and_devices_even_when_mikrotik_unavailable(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, phone_number="+628123456789", role=SimpleNamespace(value="USER"))

    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))

    monkeypatch.setattr(
        user_management_routes.user_deletion,
        "run_user_auth_cleanup",
        lambda _user: {
            "tokens_deleted": 3,
            "devices_deleted": 2,
            "device_count_before": 2,
            "macs": ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"],
            "ips": ["172.16.0.10", "172.16.0.11"],
            "mac_count": 2,
            "ip_count": 2,
            "username_08": "08123456789",
            "router": {
                "mikrotik_connected": False,
                "ip_bindings_removed": 0,
                "dhcp_leases_removed": 0,
                "arp_entries_removed": 0,
                "address_list_entries_removed": 0,
                "comment_tagged_entries_removed": 0,
                "errors": [],
            },
        },
    )
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
    assert "MikroTik tidak terhubung" in payload["message"]
    assert fake_session._commit_called == 1


def test_reset_login_removes_comment_tagged_router_entries(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, phone_number="+628123456789", role=SimpleNamespace(value="USER"))
    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))

    cleanup_summary = {
        "tokens_deleted": 1,
        "devices_deleted": 1,
        "device_count_before": 1,
        "macs": ["AA:BB:CC:DD:EE:FF"],
        "ips": ["172.16.0.10"],
        "mac_count": 1,
        "ip_count": 1,
        "username_08": "08123456789",
        "router": {
            "mikrotik_connected": True,
            "ip_bindings_removed": 1,
            "dhcp_leases_removed": 2,
            "arp_entries_removed": 2,
            "address_list_entries_removed": 2,
            "comment_tagged_entries_removed": 3,
            "errors": [],
        },
    }
    monkeypatch.setattr(user_management_routes.user_deletion, "run_user_auth_cleanup", lambda _user: cleanup_summary)
    monkeypatch.setattr(user_management_routes, "_log_admin_action", lambda **kwargs: None)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.admin_reset_user_login)

    with app.test_request_context(f"/api/admin/users/{user_id}/reset-login", method="POST"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    payload = response.get_json()["summary"]
    assert payload["router"]["mikrotik_connected"] is True

    assert payload["router"]["comment_tagged_entries_removed"] >= 1
    assert payload["mac_count"] == 1
    assert payload["ip_count"] == 1


def test_reset_login_denies_non_super_admin_for_demo_user(monkeypatch):
    user_id = uuid.uuid4()
    demo_phone = "081234567890"
    user = SimpleNamespace(
        id=user_id,
        phone_number=demo_phone,
        full_name="Regular Name",
        role=SimpleNamespace(value="USER"),
    )

    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))

    called = {"cleanup": False}

    def _should_not_run(_user):
        called["cleanup"] = True
        return {}

    monkeypatch.setattr(user_management_routes.user_deletion, "run_user_auth_cleanup", _should_not_run)

    app = _make_app()
    app.config["DEMO_ALLOWED_PHONES"] = [demo_phone]
    impl = _unwrap_decorators(user_management_routes.admin_reset_user_login)

    with app.test_request_context(f"/api/admin/users/{user_id}/reset-login", method="POST"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=False))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 403
    assert response.get_json()["message"] == "Akses ditolak."
    assert called["cleanup"] is False
