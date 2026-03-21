from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
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


def test_update_user_by_admin_validates_and_normalizes_debt_date(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="USER"), is_admin_role=False)
    fake_session = _FakeSession(users_by_id={user_id: fake_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    captured_payload = {}

    def _fake_update_user(_user, _current_admin, payload):
        captured_payload.update(payload)
        return True, "ok", SimpleNamespace(id=user_id)

    monkeypatch.setattr(
        user_management_routes.user_profile_service,
        "update_user_by_admin_comprehensive",
        _fake_update_user,
    )

    class _FakeUserResponseSchema:
        @staticmethod
        def from_orm(user):
            return SimpleNamespace(model_dump=lambda: {"id": str(user.id)})

    monkeypatch.setattr(user_management_routes, "UserResponseSchema", _FakeUserResponseSchema)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024, "debt_date": "2026-03-21"},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        _response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    assert captured_payload["debt_add_mb"] == 1024
    assert captured_payload["debt_date"] == date(2026, 3, 21)
    assert "debt_due_date" not in captured_payload


def test_update_user_by_admin_rejects_invalid_debt_date(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="USER"), is_admin_role=False)
    fake_session = _FakeSession(users_by_id={user_id: fake_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024, "debt_date": "21/03/2026"},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 400
    body = response.get_json()
    assert body["message"] == "Data tidak valid."
    assert fake_session.rollback_calls == 1


def test_serialize_public_update_submission_adds_display_dates():
    created_at = datetime(2026, 3, 21, 1, 2, 3, tzinfo=timezone.utc)
    processed_at = datetime(2026, 3, 21, 4, 5, 6, tzinfo=timezone.utc)
    item = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Naru",
        role="USER",
        blok="A",
        kamar="1",
        tamping_type=None,
        phone_number="081234567890",
        source_ip="10.0.0.1",
        approval_status="PENDING",
        processed_by_user_id=None,
        processed_at=processed_at,
        rejection_reason=None,
        created_at=created_at,
    )

    payload = user_management_routes._serialize_public_update_submission(item)

    assert payload["processed_at"] == processed_at.isoformat()
    assert payload["created_at"] == created_at.isoformat()
    assert payload["processed_at_display"] == "21-03-2026 12:05:06"
    assert payload["created_at_display"] == "21-03-2026 09:02:03"
