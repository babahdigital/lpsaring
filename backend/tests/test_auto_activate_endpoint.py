"""Tests for POST /api/auth/captive/auto-activate."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from flask import Flask

from app.infrastructure.http import auth_routes


def _unwrap(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def get(self, _model, _ident):
        return self._user

    def commit(self):
        return None

    def rollback(self):
        return None


class _FakeDb:
    def __init__(self, user):
        self.session = _FakeSession(user)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", ENABLE_OTP_AUTO_ACTIVATE=True, OTP_AUTO_ACTIVATE_TIMEOUT_S=5)
    return app


def _make_user(devices=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        phone_number="+628123456789",
        devices=devices or [],
    )


def _make_device(mac="AA:BB:CC:DD:EE:01", ip="172.16.0.10", last_seen_at=1000):
    return SimpleNamespace(
        mac_address=mac,
        ip_address=ip,
        last_seen_at=last_seen_at,
        first_seen_at=last_seen_at,
    )


def test_no_jwt_returns_401():
    app = _make_app()
    impl = auth_routes.captive_auto_activate  # decorated
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        result = impl()
    # token_required returns a Response with 401
    if isinstance(result, tuple):
        _resp, status = result
    else:
        _resp = result
        status = result.status_code
    assert status == 401


def test_no_devices_returns_no_known_device(monkeypatch):
    user = _make_user(devices=[])
    monkeypatch.setattr(auth_routes, "db", _FakeDb(user))

    app = _make_app()
    impl = _unwrap(auth_routes.captive_auto_activate)
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        body, status = impl(current_user_id=user.id)
    assert status == 200
    assert body == {"activated": False, "reason": "no_known_device"}


def test_feature_flag_disabled(monkeypatch):
    user = _make_user(devices=[_make_device()])
    monkeypatch.setattr(auth_routes, "db", _FakeDb(user))

    app = _make_app()
    app.config["ENABLE_OTP_AUTO_ACTIVATE"] = False
    impl = _unwrap(auth_routes.captive_auto_activate)
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        body, status = impl(current_user_id=user.id)
    assert status == 200
    assert body == {"activated": False, "reason": "disabled"}


def test_success(monkeypatch):
    dev_old = _make_device(mac="AA:BB:CC:DD:EE:01", last_seen_at=100)
    dev_new = _make_device(mac="AA:BB:CC:DD:EE:99", ip="172.16.0.20", last_seen_at=999)
    user = _make_user(devices=[dev_old, dev_new])
    monkeypatch.setattr(auth_routes, "db", _FakeDb(user))

    captured: dict[str, Any] = {}

    def _fake_apply(**kwargs):
        captured.update(kwargs)
        return True, "ok", kwargs.get("client_ip")

    monkeypatch.setattr(auth_routes, "apply_device_binding_for_login", _fake_apply)

    app = _make_app()
    impl = _unwrap(auth_routes.captive_auto_activate)
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        body, status = impl(current_user_id=user.id)
    assert status == 200
    assert body["activated"] is True
    assert body["mac_used"] == "AA:BB:CC:DD:EE:99"
    assert body["binding_active"] is True
    assert captured["bypass_explicit_auth"] is True
    assert captured["client_mac"] == "AA:BB:CC:DD:EE:99"
    assert captured["client_ip"] == "172.16.0.20"


def test_mikrotik_failure(monkeypatch):
    user = _make_user(devices=[_make_device()])
    monkeypatch.setattr(auth_routes, "db", _FakeDb(user))

    def _raises(**_kwargs):
        raise RuntimeError("mikrotik down")

    monkeypatch.setattr(auth_routes, "apply_device_binding_for_login", _raises)

    app = _make_app()
    impl = _unwrap(auth_routes.captive_auto_activate)
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        body, status = impl(current_user_id=user.id)
    assert status == 200
    assert body == {"activated": False, "reason": "mikrotik_unavailable"}


def test_binding_failed_returns_reason(monkeypatch):
    user = _make_user(devices=[_make_device()])
    monkeypatch.setattr(auth_routes, "db", _FakeDb(user))

    monkeypatch.setattr(
        auth_routes, "apply_device_binding_for_login",
        lambda **_kw: (False, "Limit perangkat tercapai", None),
    )

    app = _make_app()
    impl = _unwrap(auth_routes.captive_auto_activate)
    with app.test_request_context("/api/auth/captive/auto-activate", method="POST"):
        body, status = impl(current_user_id=user.id)
    assert status == 200
    assert body["activated"] is False
    assert body["reason"] == "binding_failed"
