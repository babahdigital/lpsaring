from __future__ import annotations

import uuid
from types import SimpleNamespace

from flask import Flask

from app.infrastructure.http.auth_contexts.admin_auth_handlers import logout_user_impl, reset_login_user_impl


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["REFRESH_COOKIE_NAME"] = "refresh_token"
    return app


def test_logout_calls_network_reset_and_revokes_refresh_token() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    tracker = {
        "cleanup_called": False,
        "revoke_token": None,
        "clear_auth_called": False,
        "clear_refresh_called": False,
    }

    def _cleanup(_user):
        tracker["cleanup_called"] = True
        return {"ok": True}

    def _revoke(token: str):
        tracker["revoke_token"] = token

    def _clear_auth(_response):
        tracker["clear_auth_called"] = True

    def _clear_refresh(_response):
        tracker["clear_refresh_called"] = True

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.test_request_context("/api/auth/logout", method="POST", headers={"Cookie": "refresh_token=rt-123"}):
        response, status = logout_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={"refresh_token": "rt-123"}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=_revoke,
            clear_auth_cookie=_clear_auth,
            clear_refresh_cookie=_clear_refresh,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    assert response.get_json()["message"] == "Logout successful"
    assert tracker["cleanup_called"] is True
    assert tracker["revoke_token"] == "rt-123"
    assert tracker["clear_auth_called"] is True
    assert tracker["clear_refresh_called"] is True


def test_logout_stays_success_when_network_reset_fails() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    tracker = {
        "revoke_called": False,
        "clear_auth_called": False,
        "clear_refresh_called": False,
    }

    def _cleanup(_user):
        raise RuntimeError("cleanup failed")

    def _revoke(_token: str):
        tracker["revoke_called"] = True

    def _clear_auth(_response):
        tracker["clear_auth_called"] = True

    def _clear_refresh(_response):
        tracker["clear_refresh_called"] = True

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.test_request_context("/api/auth/logout", method="POST", headers={"Cookie": "refresh_token=rt-456"}):
        response, status = logout_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={"refresh_token": "rt-456"}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=_revoke,
            clear_auth_cookie=_clear_auth,
            clear_refresh_cookie=_clear_refresh,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    assert response.get_json()["message"] == "Logout successful"
    assert tracker["revoke_called"] is True
    assert tracker["clear_auth_called"] is True
    assert tracker["clear_refresh_called"] is True


def test_reset_login_calls_network_reset_without_revoking_tokens() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    tracker = {
        "cleanup_called": False,
    }

    def _cleanup(_user):
        tracker["cleanup_called"] = True
        return {"ip_binding_removed": 2}

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.app_context():
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            current_app=app,
            db=db,
            User=object,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    payload = response.get_json()
    assert "Reset login berhasil" in payload["message"]
    assert payload["network_reset"]["ip_binding_removed"] == 2
    assert tracker["cleanup_called"] is True


def test_reset_login_returns_error_when_cleanup_raises() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    def _cleanup(_user):
        raise RuntimeError("cleanup failed")

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.app_context():
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            current_app=app,
            db=db,
            User=object,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 500
    assert "gagal" in response.get_json()["message"].lower()


def test_reset_login_admin_user_still_executes_cleanup() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    admin_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="ADMIN"))
    tracker = {"cleanup_called": False}

    def _cleanup(_user):
        tracker["cleanup_called"] = True
        return {"ip_binding_removed": 0, "dhcp_removed": 0, "arp_removed": 0, "host_removed": 0}

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: admin_user))

    with app.app_context():
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            current_app=app,
            db=db,
            User=object,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    assert tracker["cleanup_called"] is True
    payload = response.get_json()
    assert "network_reset" in payload
