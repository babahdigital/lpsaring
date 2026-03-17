from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.db.models import User
from app.infrastructure.http.admin import user_management_routes


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeSession:
    def __init__(self, *, users_by_id):
        self._users_by_id = users_by_id
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def get(self, model, user_id):
        if model is User:
            return self._users_by_id.get(user_id)
        return None

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, _obj):
        self.refresh_calls += 1
        raise AssertionError("update_user_by_admin should reload the user instead of refreshing the returned instance")


def _make_app() -> Flask:
    return Flask(__name__)


def test_update_user_by_admin_serializes_reloaded_user_after_commit(monkeypatch):
    user_id = uuid.uuid4()
    stale_user = SimpleNamespace(
        id=user_id,
        phone_number="081234567890",
        full_name="Sebelum Update",
        role=SimpleNamespace(value="USER"),
    )
    reloaded_user = SimpleNamespace(
        id=user_id,
        phone_number="081234567890",
        full_name="Sesudah Update",
        role=SimpleNamespace(value="USER"),
    )
    fake_session = _FakeSession(users_by_id={user_id: stale_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    def _fake_update_user(_user, _current_admin, _payload):
        fake_session._users_by_id[user_id] = reloaded_user
        return True, "ok", SimpleNamespace(id=user_id)

    monkeypatch.setattr(
        user_management_routes.user_profile_service,
        "update_user_by_admin_comprehensive",
        _fake_update_user,
    )

    class _FakeUserResponseSchema:
        @staticmethod
        def from_orm(user):
            return SimpleNamespace(
                model_dump=lambda: {
                    "id": str(user.id),
                    "phone_number": user.phone_number,
                    "full_name": user.full_name,
                }
            )

    monkeypatch.setattr(user_management_routes, "UserResponseSchema", _FakeUserResponseSchema)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    assert response.get_json() == {
        "id": str(user_id),
        "phone_number": "081234567890",
        "full_name": "Sesudah Update",
    }
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0
    assert fake_session.refresh_calls == 0
