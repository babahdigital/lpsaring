from __future__ import annotations

import uuid
from types import SimpleNamespace

from flask import Flask, jsonify, g
from jose import ExpiredSignatureError

from app.infrastructure.http import decorators


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def get(self, _model, _pk):
        return self._user


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["JWT_SECRET_KEY"] = "test-jwt-secret"
    app.config["JWT_ALGORITHM"] = "HS256"
    app.config["DEMO_MODE_ENABLED"] = True
    app.config["DEMO_ALLOWED_PHONES"] = ["081234567890"]
    app.config["AUTH_COOKIE_NAME"] = "auth_token"
    app.config["CSRF_PROTECT_ENABLED"] = True
    return app


def _make_user(phone: str, *, is_active: bool = True, is_approved: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        phone_number=phone,
        is_active=is_active,
        is_approved=is_approved,
        role=SimpleNamespace(value="USER"),
    )


def _protected_endpoint():
    @decorators.token_required
    def _handler(current_user_id=None):
        return jsonify({"ok": True, "current_user_id": str(current_user_id)}), 200

    return _handler


def test_token_required_blocks_demo_user_outside_payment_scope(monkeypatch):
    app = _make_app()
    demo_user = _make_user("+6281234567890")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(demo_user)))
    monkeypatch.setattr(decorators.jwt, "decode", lambda *_a, **_k: {"sub": str(demo_user.id)})

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/users/me/quota",
        method="GET",
        headers={"Authorization": "Bearer token-demo"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 403
    assert payload["code"] == "AUTH_DEMO_SCOPE_RESTRICTED"


def test_token_required_allows_demo_user_payment_scope(monkeypatch):
    app = _make_app()
    demo_user = _make_user("+6281234567890")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(demo_user)))
    monkeypatch.setattr(decorators.jwt, "decode", lambda *_a, **_k: {"sub": str(demo_user.id)})

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/transactions/initiate",
        method="POST",
        headers={"Authorization": "Bearer token-demo"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 200
    assert payload["ok"] is True
    assert payload["current_user_id"] == str(demo_user.id)


def test_token_required_allows_non_demo_user_any_scope(monkeypatch):
    app = _make_app()
    non_demo_user = _make_user("+628112223334")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(non_demo_user)))
    monkeypatch.setattr(decorators.jwt, "decode", lambda *_a, **_k: {"sub": str(non_demo_user.id)})

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/users/me/quota",
        method="GET",
        headers={"Authorization": "Bearer token-regular"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 200
    assert payload["ok"] is True
    assert payload["current_user_id"] == str(non_demo_user.id)


def test_token_required_refresh_fallback_blocks_demo_user_outside_payment_scope(monkeypatch):
    app = _make_app()
    demo_user = _make_user("+6281234567890")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(demo_user)))
    monkeypatch.setattr(
        decorators,
        "rotate_refresh_token",
        lambda *_a, **_k: SimpleNamespace(user_id=str(demo_user.id), new_refresh_token="new-refresh"),
    )
    monkeypatch.setattr(decorators, "create_access_token", lambda *_a, **_k: "new-access")

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/users/me/quota",
        method="GET",
        headers={"Cookie": "refresh_token=dummy-refresh-token"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 403
    assert payload["code"] == "AUTH_DEMO_SCOPE_RESTRICTED"


def test_token_required_refresh_fallback_allows_demo_user_payment_scope(monkeypatch):
    app = _make_app()
    demo_user = _make_user("+6281234567890")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(demo_user)))
    monkeypatch.setattr(
        decorators,
        "rotate_refresh_token",
        lambda *_a, **_k: SimpleNamespace(user_id=str(demo_user.id), new_refresh_token="new-refresh"),
    )
    monkeypatch.setattr(decorators, "create_access_token", lambda *_a, **_k: "new-access")

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/transactions/initiate",
        method="POST",
        headers={"Cookie": "refresh_token=dummy-refresh-token"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 200
    assert payload["ok"] is True
    assert payload["current_user_id"] == str(demo_user.id)


def test_token_required_logout_refresh_fallback_does_not_set_new_tokens(monkeypatch):
    app = _make_app()
    non_demo_user = _make_user("+628112223334")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(non_demo_user)))
    monkeypatch.setattr(
        decorators,
        "rotate_refresh_token",
        lambda *_a, **_k: SimpleNamespace(user_id=str(non_demo_user.id), new_refresh_token="new-refresh"),
    )
    monkeypatch.setattr(decorators, "create_access_token", lambda *_a, **_k: "new-access")

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/auth/logout",
        method="POST",
        headers={"Cookie": "refresh_token=dummy-refresh-token"},
    ):
        response, status = protected()
        payload = response.get_json()
        assert status == 200
        assert payload["ok"] is True
        assert payload["current_user_id"] == str(non_demo_user.id)
        assert not hasattr(g, "new_access_token")
        assert not hasattr(g, "new_refresh_token")


def test_token_required_logout_expired_cookie_does_not_set_new_tokens(monkeypatch):
    app = _make_app()
    non_demo_user = _make_user("+628112223334")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(non_demo_user)))
    monkeypatch.setattr(decorators.jwt, "decode", lambda *_a, **_k: (_ for _ in ()).throw(ExpiredSignatureError("expired")))
    monkeypatch.setattr(
        decorators,
        "rotate_refresh_token",
        lambda *_a, **_k: SimpleNamespace(user_id=str(non_demo_user.id), new_refresh_token="new-refresh"),
    )
    monkeypatch.setattr(decorators, "create_access_token", lambda *_a, **_k: "new-access")

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/auth/logout",
        method="POST",
        headers={"Cookie": "auth_token=expired-cookie-token; refresh_token=dummy-refresh-token"},
    ):
        response, status = protected()
        payload = response.get_json()
        assert status == 200
        assert payload["ok"] is True
        assert payload["current_user_id"] == str(non_demo_user.id)
        assert not hasattr(g, "new_access_token")
        assert not hasattr(g, "new_refresh_token")


def test_token_required_reset_login_refresh_fallback_does_not_set_new_tokens(monkeypatch):
    app = _make_app()
    non_demo_user = _make_user("+628112223334")

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(non_demo_user)))
    monkeypatch.setattr(
        decorators,
        "rotate_refresh_token",
        lambda *_a, **_k: SimpleNamespace(user_id=str(non_demo_user.id), new_refresh_token="new-refresh"),
    )
    monkeypatch.setattr(decorators, "create_access_token", lambda *_a, **_k: "new-access")

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/auth/reset-login",
        method="POST",
        headers={"Cookie": "refresh_token=dummy-refresh-token"},
    ):
        response, status = protected()
        payload = response.get_json()
        assert status == 200
        assert payload["ok"] is True
        assert payload["current_user_id"] == str(non_demo_user.id)
        assert not hasattr(g, "new_access_token")
        assert not hasattr(g, "new_refresh_token")


def test_token_required_allows_inactive_user_for_reset_login_path(monkeypatch):
    app = _make_app()
    inactive_user = _make_user("+628112223334", is_active=False, is_approved=False)

    monkeypatch.setattr(decorators, "db", SimpleNamespace(session=_FakeSession(inactive_user)))
    monkeypatch.setattr(decorators.jwt, "decode", lambda *_a, **_k: {"sub": str(inactive_user.id)})

    protected = _protected_endpoint()

    with app.test_request_context(
        "/api/auth/reset-login",
        method="POST",
        headers={"Authorization": "Bearer token-inactive"},
    ):
        response, status = protected()

    payload = response.get_json()
    assert status == 200
    assert payload["ok"] is True
    assert payload["current_user_id"] == str(inactive_user.id)
