from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from flask import Flask

from app.infrastructure.http.auth_contexts.hotspot_status_handlers import get_hotspot_session_status_impl


class _SchemaStub:
    def __init__(self, **kwargs):
        self._data = kwargs

    def model_dump(self):
        return dict(self._data)


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def get(self, *_args, **_kwargs):
        return self._user


class _FakeDb:
    def __init__(self, user):
        self.session = _FakeSession(user)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="unit-test")
    return app


def test_hotspot_session_status_reports_active_binding():
    app = _make_app()
    user = SimpleNamespace(id="u-1", phone_number="+628123456789")

    @contextmanager
    def _conn(*_args, **_kwargs):
        yield object()

    with app.app_context():
        response, status = get_hotspot_session_status_impl(
            current_user_id="u-1",
            db=_FakeDb(user),
            User=SimpleNamespace,
            AuthErrorResponseSchema=_SchemaStub,
            format_to_local_phone=lambda *_a, **_k: "08123456789",
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=lambda *_a, **_k: (True, True, "ok"),
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_session_active"] is True


def test_hotspot_session_status_reports_inactive_when_binding_missing():
    app = _make_app()
    user = SimpleNamespace(id="u-2", phone_number="+628122000111")

    @contextmanager
    def _conn(*_args, **_kwargs):
        yield object()

    with app.app_context():
        response, status = get_hotspot_session_status_impl(
            current_user_id="u-2",
            db=_FakeDb(user),
            User=SimpleNamespace,
            AuthErrorResponseSchema=_SchemaStub,
            format_to_local_phone=lambda *_a, **_k: "08122000111",
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=lambda *_a, **_k: (True, False, "not-found"),
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_session_active"] is False
