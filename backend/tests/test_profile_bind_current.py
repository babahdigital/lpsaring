from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.db.models import ApprovalStatus, User
from app.infrastructure.http.user import profile_routes


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeSession:
    def __init__(self, *, user):
        self._user = user
        self.commit_calls = 0

    def get(self, model, user_id):
        if model is User and getattr(self._user, "id", None) == user_id:
            return self._user
        return None

    def commit(self):
        self.commit_calls += 1


def _make_app() -> Flask:
    return Flask(__name__)


def _make_user(user_id: uuid.UUID):
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
    )


def test_bind_current_best_effort_skips_single_user_sync(monkeypatch):
    user_id = uuid.uuid4()
    user = _make_user(user_id)
    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(profile_routes, "db", SimpleNamespace(session=fake_session))
    bind_calls = {"count": 0}

    def _fake_bind(*_args, **_kwargs):
        bind_calls["count"] += 1
        return True, "Perangkat terotorisasi", "172.16.3.10"

    monkeypatch.setattr(
        profile_routes,
        "apply_device_binding_for_login",
        _fake_bind,
    )
    monkeypatch.setattr(profile_routes.settings_service, "get_setting", lambda *_args, **_kwargs: "True")

    sync_called = {"count": 0}

    def _fake_sync(*_args, **_kwargs):
        sync_called["count"] += 1
        return True

    monkeypatch.setattr(profile_routes, "sync_address_list_for_single_user", _fake_sync)

    app = _make_app()
    impl = _unwrap_decorators(profile_routes.bind_current_device)

    with app.test_request_context(
        "/api/users/me/devices/bind-current?best_effort=1&client_ip=172.16.3.10&client_mac=AA:BB:CC:DD:EE:FF",
        method="POST",
    ):
        response, status = impl(current_user_id=cast(User, user_id))

    assert status == 200
    assert response.get_json()["bound"] is True
    assert bind_calls["count"] == 1
    assert sync_called["count"] == 0
    assert fake_session.commit_calls == 1


def test_bind_current_best_effort_without_identity_hint_noops(monkeypatch):
    user_id = uuid.uuid4()
    user = _make_user(user_id)
    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(profile_routes, "db", SimpleNamespace(session=fake_session))
    bind_calls = {"count": 0}

    def _fake_bind(*_args, **_kwargs):
        bind_calls["count"] += 1
        return True, "Perangkat terotorisasi", "172.16.3.10"

    monkeypatch.setattr(profile_routes, "apply_device_binding_for_login", _fake_bind)
    monkeypatch.setattr(profile_routes.settings_service, "get_setting", lambda *_args, **_kwargs: "True")

    sync_called = {"count": 0}

    def _fake_sync(*_args, **_kwargs):
        sync_called["count"] += 1
        return True

    monkeypatch.setattr(profile_routes, "sync_address_list_for_single_user", _fake_sync)

    app = _make_app()
    impl = _unwrap_decorators(profile_routes.bind_current_device)

    with app.test_request_context("/api/users/me/devices/bind-current?best_effort=1", method="POST"):
        response, status = impl(current_user_id=cast(User, user_id))

    assert status == 200
    assert response.get_json()["bound"] is False
    assert bind_calls["count"] == 0
    assert sync_called["count"] == 0
    assert fake_session.commit_calls == 0


def test_bind_current_without_identity_hint_rejected(monkeypatch):
    user_id = uuid.uuid4()
    user = _make_user(user_id)
    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(profile_routes, "db", SimpleNamespace(session=fake_session))
    bind_calls = {"count": 0}

    def _fake_bind(*_args, **_kwargs):
        bind_calls["count"] += 1
        return True, "Perangkat terotorisasi", "172.16.3.10"

    monkeypatch.setattr(profile_routes, "apply_device_binding_for_login", _fake_bind)
    monkeypatch.setattr(profile_routes.settings_service, "get_setting", lambda *_args, **_kwargs: "True")
    monkeypatch.setattr(profile_routes, "sync_address_list_for_single_user", lambda *_args, **_kwargs: True)

    app = _make_app()
    impl = _unwrap_decorators(profile_routes.bind_current_device)

    with app.test_request_context("/api/users/me/devices/bind-current", method="POST"):
        response, status = impl(current_user_id=cast(User, user_id))

    assert status == 400
    assert response.get_json()["bound"] is False
    assert bind_calls["count"] == 0
    assert fake_session.commit_calls == 0


def test_bind_current_without_best_effort_runs_single_user_sync(monkeypatch):
    user_id = uuid.uuid4()
    user = _make_user(user_id)
    fake_session = _FakeSession(user=user)
    monkeypatch.setattr(profile_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(
        profile_routes,
        "apply_device_binding_for_login",
        lambda *_args, **_kwargs: (True, "Perangkat terotorisasi", "172.16.3.10"),
    )
    monkeypatch.setattr(profile_routes.settings_service, "get_setting", lambda *_args, **_kwargs: "True")

    sync_called = {"count": 0}

    def _fake_sync(*_args, **_kwargs):
        sync_called["count"] += 1
        return True

    monkeypatch.setattr(profile_routes, "sync_address_list_for_single_user", _fake_sync)

    app = _make_app()
    impl = _unwrap_decorators(profile_routes.bind_current_device)

    with app.test_request_context(
        "/api/users/me/devices/bind-current?client_ip=172.16.3.10&client_mac=AA:BB:CC:DD:EE:FF",
        method="POST",
    ):
        response, status = impl(current_user_id=cast(User, user_id))

    assert status == 200
    assert response.get_json()["bound"] is True
    assert sync_called["count"] == 1
    assert fake_session.commit_calls == 1