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


def test_reset_login_calls_network_reset_only_no_token_or_cookie_clear() -> None:
    """reset-login hanya bersihkan jaringan; token, UserDevice, dan cookie TIDAK dihapus."""
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    tracker = {
        "cleanup_called": False,
        "revoke_called": False,
        "clear_auth_called": False,
        "clear_refresh_called": False,
    }

    def _cleanup(_user):
        tracker["cleanup_called"] = True
        return {"ip_binding_removed": 2}

    def _revoke(_token: str):
        tracker["revoke_called"] = True

    def _clear_auth(_response):
        tracker["clear_auth_called"] = True

    def _clear_refresh(_response):
        tracker["clear_refresh_called"] = True

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.test_request_context("/api/auth/reset-login", method="POST", headers={"Cookie": "refresh_token=rt-reset-1"}):
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={"refresh_token": "rt-reset-1"}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=_revoke,
            clear_auth_cookie=_clear_auth,
            clear_refresh_cookie=_clear_refresh,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    payload = response.get_json()
    assert "Reset login berhasil" in payload["message"]
    assert payload["network_reset"]["ip_binding_removed"] == 2
    # Token, device, dan cookie TIDAK dihapus pada reset-login
    assert "summary" not in payload
    assert tracker["cleanup_called"] is True
    assert tracker["revoke_called"] is False
    assert tracker["clear_auth_called"] is False
    assert tracker["clear_refresh_called"] is False


def test_reset_login_returns_error_when_cleanup_raises() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    def _cleanup(_user):
        raise RuntimeError("cleanup failed")

    db = SimpleNamespace(session=SimpleNamespace(get=lambda _model, _id: user))

    with app.test_request_context("/api/auth/reset-login", method="POST"):
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=lambda _token: None,
            clear_auth_cookie=lambda _response: None,
            clear_refresh_cookie=lambda _response: None,
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

    with app.test_request_context("/api/auth/reset-login", method="POST"):
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=lambda _token: None,
            clear_auth_cookie=lambda _response: None,
            clear_refresh_cookie=lambda _response: None,
            cleanup_user_network_on_logout=_cleanup,
        )

    assert status == 200
    assert tracker["cleanup_called"] is True
    payload = response.get_json()
    assert "network_reset" in payload


def test_logout_deletes_all_tokens_and_devices_when_models_available() -> None:
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    class _RefreshTokenModel:
        user_id = "user_id"

    class _UserDeviceModel:
        user_id = "user_id"

    class _DeleteQuery:
        def __init__(self, deleted_count: int):
            self._deleted_count = deleted_count

        def filter(self, *_args, **_kwargs):
            return self

        def delete(self, synchronize_session: bool = False):
            return self._deleted_count

    class _DeleteSession:
        def __init__(self):
            self.committed = False

        def get(self, _model, _id):
            return user

        def query(self, model):
            if model is _RefreshTokenModel:
                return _DeleteQuery(4)
            if model is _UserDeviceModel:
                return _DeleteQuery(2)
            return _DeleteQuery(0)

        def commit(self):
            self.committed = True

    session = _DeleteSession()
    db = SimpleNamespace(session=session)

    tracker = {
        "revoke_called": False,
        "clear_auth_called": False,
        "clear_refresh_called": False,
    }

    def _cleanup(_user):
        return {"ip_binding_removed": 1}

    def _revoke(_token: str):
        tracker["revoke_called"] = True

    def _clear_auth(_response):
        tracker["clear_auth_called"] = True

    def _clear_refresh(_response):
        tracker["clear_refresh_called"] = True

    with app.test_request_context("/api/auth/logout", method="POST", headers={"Cookie": "refresh_token=rt-789"}):
        response, status = logout_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={"refresh_token": "rt-789"}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=_revoke,
            clear_auth_cookie=_clear_auth,
            clear_refresh_cookie=_clear_refresh,
            cleanup_user_network_on_logout=_cleanup,
            RefreshToken=_RefreshTokenModel,
            UserDevice=_UserDeviceModel,
        )

    assert status == 200
    payload = response.get_json()
    assert payload["summary"]["tokens_deleted"] == 4
    assert payload["summary"]["devices_deleted"] == 2
    assert session.committed is True
    assert tracker["revoke_called"] is False
    assert tracker["clear_auth_called"] is True
    assert tracker["clear_refresh_called"] is True


def test_reset_login_does_not_delete_tokens_or_clear_cookies_even_when_models_passed() -> None:
    """reset-login tidak menghapus token/device/cookie meskipun model diberikan."""
    app = _make_app()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    class _RefreshTokenModel:
        user_id = "user_id"

    class _UserDeviceModel:
        user_id = "user_id"

    class _DeleteQuery:
        def __init__(self, deleted_count: int):
            self._deleted_count = deleted_count
            self.delete_called = False

        def filter(self, *_args, **_kwargs):
            return self

        def delete(self, synchronize_session: bool = False):
            self.delete_called = True
            return self._deleted_count

    rt_query = _DeleteQuery(5)
    ud_query = _DeleteQuery(3)

    class _DeleteSession:
        def __init__(self):
            self.committed = False

        def get(self, _model, _id):
            return user

        def query(self, model):
            if model is _RefreshTokenModel:
                return rt_query
            if model is _UserDeviceModel:
                return ud_query
            return _DeleteQuery(0)

        def commit(self):
            self.committed = True

    session = _DeleteSession()
    db = SimpleNamespace(session=session)

    tracker = {
        "cleanup_called": False,
        "revoke_called": False,
        "clear_auth_called": False,
        "clear_refresh_called": False,
    }

    def _cleanup(_user):
        tracker["cleanup_called"] = True
        return {"ip_binding_removed": 2}

    def _revoke(_token: str):
        tracker["revoke_called"] = True

    def _clear_auth(_response):
        tracker["clear_auth_called"] = True

    def _clear_refresh(_response):
        tracker["clear_refresh_called"] = True

    with app.test_request_context("/api/auth/reset-login", method="POST", headers={"Cookie": "refresh_token=rt-rst-9"}):
        response, status = reset_login_user_impl(
            current_user_id=user_id,
            request=SimpleNamespace(cookies={"refresh_token": "rt-rst-9"}),
            current_app=app,
            db=db,
            User=object,
            revoke_refresh_token=_revoke,
            clear_auth_cookie=_clear_auth,
            clear_refresh_cookie=_clear_refresh,
            cleanup_user_network_on_logout=_cleanup,
            RefreshToken=_RefreshTokenModel,
            UserDevice=_UserDeviceModel,
        )

    assert status == 200
    payload = response.get_json()
    assert "Reset login berhasil" in payload["message"]
    assert payload["network_reset"]["ip_binding_removed"] == 2
    # Token/device TIDAK dihapus pada reset-login
    assert "summary" not in payload
    assert rt_query.delete_called is False
    assert ud_query.delete_called is False
    assert session.committed is False
    assert tracker["cleanup_called"] is True
    assert tracker["revoke_called"] is False
    assert tracker["clear_auth_called"] is False
    assert tracker["clear_refresh_called"] is False
