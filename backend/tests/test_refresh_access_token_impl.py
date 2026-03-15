from __future__ import annotations

import uuid
from types import SimpleNamespace

from flask import Flask, current_app, request

from app.infrastructure.db.models import ApprovalStatus
from app.infrastructure.http.auth_contexts.admin_auth_handlers import refresh_access_token_impl


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def get(self, _model, _user_id):
        return self._user


def test_refresh_access_token_impl_keeps_existing_refresh_cookie_when_rotation_reuses_recent_token():
    app = Flask(__name__)
    app.config["REFRESH_COOKIE_NAME"] = "refresh_token"

    user = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        role=SimpleNamespace(value="USER"),
    )
    tracker: dict[str, str] = {}

    def _set_auth_cookie(_response, token: str):
        tracker["auth"] = token

    def _set_refresh_cookie(_response, token: str):
        tracker["refresh"] = token

    with app.app_context(), app.test_request_context(
        "/api/auth/refresh",
        method="POST",
        headers={"Cookie": "refresh_token=stale-refresh", "User-Agent": "UA/1.0"},
    ):
        response, status = refresh_access_token_impl(
            request=request,
            current_app=current_app,
            db=SimpleNamespace(session=_FakeSession(user)),
            User=object,
            ApprovalStatus=ApprovalStatus,
            AuthErrorResponseSchema=object,
            rotate_refresh_token=lambda *_a, **_k: SimpleNamespace(user_id=str(user.id), new_refresh_token=None),
            create_access_token=lambda *_a, **_k: "new-access",
            set_auth_cookie=_set_auth_cookie,
            set_refresh_cookie=_set_refresh_cookie,
            build_status_error=lambda *_a, **_k: None,
        )

    assert status == 200
    assert response.get_json() == {"access_token": "new-access", "token_type": "bearer"}
    assert tracker["auth"] == "new-access"
    assert "refresh" not in tracker