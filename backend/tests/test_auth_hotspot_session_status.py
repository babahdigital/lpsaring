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
            query_args={},
            format_to_local_phone=lambda *_a, **_k: "08123456789",
            normalize_mac=lambda value: str(value or "").strip().upper() or None,
            resolve_client_mac=lambda *_a, **_k: (True, None, "no-ip"),
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=lambda *_a, **_k: (True, True, "ok"),
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_binding_active"] is True
    assert payload["hotspot_session_active"] is True
    assert payload["hotspot_hint_applied"] is False


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
            query_args={},
            format_to_local_phone=lambda *_a, **_k: "08122000111",
            normalize_mac=lambda value: str(value or "").strip().upper() or None,
            resolve_client_mac=lambda *_a, **_k: (True, None, "no-ip"),
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=lambda *_a, **_k: (True, False, "not-found"),
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_binding_active"] is False
    assert payload["hotspot_session_active"] is False


def test_hotspot_session_status_checks_mac_hint_first_then_fallback():
    app = _make_app()
    app.config.update(HOTSPOT_SESSION_STATUS_ALLOW_USER_LEVEL_FALLBACK=True)
    user = SimpleNamespace(id="u-3", phone_number="+628122333444")

    @contextmanager
    def _conn(*_args, **_kwargs):
        yield object()

    def _has_binding(_api, *, username, user_id, mac_address):
        if mac_address == "AA:BB:CC:DD:EE:FF":
            return True, False, "mac-not-found"
        if mac_address is None:
            return True, True, "user-level-found"
        return True, False, "not-found"

    with app.app_context():
        response, status = get_hotspot_session_status_impl(
            current_user_id="u-3",
            db=_FakeDb(user),
            User=SimpleNamespace,
            AuthErrorResponseSchema=_SchemaStub,
            query_args={"client_ip": "172.16.2.10", "client_mac": "aa:bb:cc:dd:ee:ff"},
            format_to_local_phone=lambda *_a, **_k: "08122333444",
            normalize_mac=lambda value: str(value or "").strip().upper() or None,
            resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=_has_binding,
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_binding_active"] is True
    assert payload["hotspot_session_active"] is True
    assert payload["hotspot_hint_applied"] is True


def test_hotspot_session_status_rejects_mismatched_mac_hint():
    app = _make_app()
    user = SimpleNamespace(id="u-4", phone_number="+628122333555")

    @contextmanager
    def _conn(*_args, **_kwargs):
        yield object()

    with app.app_context():
        response, status = get_hotspot_session_status_impl(
            current_user_id="u-4",
            db=_FakeDb(user),
            User=SimpleNamespace,
            AuthErrorResponseSchema=_SchemaStub,
            query_args={"client_ip": "172.16.2.11", "client_mac": "00:11:22:33:44:55"},
            format_to_local_phone=lambda *_a, **_k: "08122333555",
            normalize_mac=lambda value: str(value or "").strip().upper() or None,
            resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
            is_hotspot_login_required=lambda *_a, **_k: True,
            get_mikrotik_connection=_conn,
            has_hotspot_ip_binding_for_user=lambda *_a, **_k: (True, True, "ok"),
        )

    assert status == 200
    payload = response.get_json()
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_binding_active"] is False
    assert payload["hotspot_session_active"] is False
    assert payload["hotspot_hint_applied"] is True
