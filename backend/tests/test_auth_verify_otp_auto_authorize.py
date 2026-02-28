from types import SimpleNamespace
from typing import Any, cast
from contextlib import contextmanager

from flask import Flask

from app.infrastructure.http import auth_routes
from app.infrastructure.db.models import ApprovalStatus, UserRole


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeExecuteResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, user, *, scalar_value: Any = None):
        self._user = user
        self._scalar_value = scalar_value

    def execute(self, *_args, **_kwargs):
        return _FakeExecuteResult(self._user)

    def scalar(self, *_args, **_kwargs):
        return self._scalar_value

    def add(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class _FakeDb:
    def __init__(self, session):
        self.session = session


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test",
        OTP_VERIFY_MAX_ATTEMPTS=5,
        OTP_ALLOW_BYPASS=False,
        OTP_BYPASS_CODE="000000",
        OTP_AUTO_AUTHORIZE_DEVICE=True,
        SYNC_ADDRESS_LIST_ON_LOGIN=False,
    )
    return app


def test_verify_otp_auto_authorizes_device_even_if_user_already_has_authorized_device(monkeypatch):
    captured: dict[str, Any] = {"bypass": None}

    user = SimpleNamespace(
        id="user-1",
        phone_number="+628123456789",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        mikrotik_password="pw",
        last_login_at=None,
    )

    fake_session = _FakeSession(user, scalar_value="existing-device-id")
    monkeypatch.setattr(auth_routes, "db", _FakeDb(fake_session))

    monkeypatch.setattr(auth_routes, "verify_otp_from_redis", lambda *_a, **_k: True)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])

    monkeypatch.setattr(auth_routes.settings_service, "get_setting", lambda *_a, **_k: "True")
    monkeypatch.setattr(auth_routes, "resolve_client_mac", lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"))

    def _fake_apply_binding(*_args, **kwargs):
        captured["bypass"] = kwargs.get("bypass_explicit_auth")
        return True, "ok", "172.16.0.2"

    monkeypatch.setattr(auth_routes, "apply_device_binding_for_login", _fake_apply_binding)

    monkeypatch.setattr(auth_routes, "sync_address_list_for_single_user", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *_a, **_k: "access")
    monkeypatch.setattr(auth_routes, "issue_refresh_token_for_user", lambda *_a, **_k: "refresh")
    monkeypatch.setattr(auth_routes, "is_hotspot_login_required", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "_store_session_token", lambda *_a, **_k: None)

    # Avoid touching real SQLAlchemy model constructor
    monkeypatch.setattr(auth_routes, "UserLoginHistory", lambda **kw: SimpleNamespace(**kw))

    app = _make_app()
    verify_impl = _unwrap_decorators(auth_routes.verify_otp)

    with app.test_request_context(
        "/api/auth/verify-otp",
        method="POST",
        json={
            "phone_number": "+628123456789",
            "otp": "123456",
            "client_ip": "172.16.0.2",
            "client_mac": "AA:BB:CC:DD:EE:FF",
            "hotspot_login_context": True,
        },
        headers={"User-Agent": "pytest"},
    ):
        response, status = verify_impl()

    assert status == 200
    assert response.get_json()["access_token"] == "access"
    assert captured["bypass"] is True


def test_verify_otp_does_not_auto_authorize_when_using_bypass_code(monkeypatch):
    captured: dict[str, Any] = {"bypass": None}

    user = SimpleNamespace(
        id="user-1",
        phone_number="+628123456789",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        mikrotik_password="pw",
        last_login_at=None,
    )

    fake_session = _FakeSession(user, scalar_value="existing-device-id")
    monkeypatch.setattr(auth_routes, "db", _FakeDb(fake_session))

    # Force redis verify fail so bypass path is used
    monkeypatch.setattr(auth_routes, "verify_otp_from_redis", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])

    monkeypatch.setattr(auth_routes.settings_service, "get_setting", lambda *_a, **_k: "True")
    monkeypatch.setattr(auth_routes, "resolve_client_mac", lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"))

    def _fake_apply_binding(*_args, **kwargs):
        captured["bypass"] = kwargs.get("bypass_explicit_auth")
        return True, "ok", "172.16.0.2"

    monkeypatch.setattr(auth_routes, "apply_device_binding_for_login", _fake_apply_binding)

    monkeypatch.setattr(auth_routes, "sync_address_list_for_single_user", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *_a, **_k: "access")
    monkeypatch.setattr(auth_routes, "issue_refresh_token_for_user", lambda *_a, **_k: "refresh")
    monkeypatch.setattr(auth_routes, "is_hotspot_login_required", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "_store_session_token", lambda *_a, **_k: None)

    monkeypatch.setattr(auth_routes, "UserLoginHistory", lambda **kw: SimpleNamespace(**kw))

    app = _make_app()
    app.config.update(OTP_ALLOW_BYPASS=True, OTP_BYPASS_CODE="000000")

    verify_impl = _unwrap_decorators(auth_routes.verify_otp)

    with app.test_request_context(
        "/api/auth/verify-otp",
        method="POST",
        json={
            "phone_number": "+628123456789",
            "otp": "000000",
            "client_ip": "172.16.0.2",
            "client_mac": "AA:BB:CC:DD:EE:FF",
            "hotspot_login_context": True,
        },
        headers={"User-Agent": "pytest"},
    ):
        response, status = verify_impl()

    assert status == 200
    assert cast(dict, response.get_json())["access_token"] == "access"
    # Since user already has an authorized device, fallback legacy policy should NOT bypass explicit auth.
    assert captured["bypass"] is False


def test_verify_otp_still_self_authorizes_when_otp_auto_authorize_disabled(monkeypatch):
    captured: dict[str, Any] = {"bypass": None}

    user = SimpleNamespace(
        id="user-2",
        phone_number="+628123000111",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        mikrotik_password="pw",
        last_login_at=None,
    )

    # Simulasikan user yang sudah punya device authorized; tetap harus self-authorize saat OTP valid normal.
    fake_session = _FakeSession(user, scalar_value="existing-device-id")
    monkeypatch.setattr(auth_routes, "db", _FakeDb(fake_session))

    monkeypatch.setattr(auth_routes, "verify_otp_from_redis", lambda *_a, **_k: True)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])
    monkeypatch.setattr(auth_routes.settings_service, "get_setting", lambda *_a, **_k: "True")
    monkeypatch.setattr(auth_routes, "resolve_client_mac", lambda *_a, **_k: (True, "AA:BB:CC:00:11:22", "ok"))

    def _fake_apply_binding(*_args, **kwargs):
        captured["bypass"] = kwargs.get("bypass_explicit_auth")
        return True, "ok", "172.16.0.22"

    monkeypatch.setattr(auth_routes, "apply_device_binding_for_login", _fake_apply_binding)
    monkeypatch.setattr(auth_routes, "sync_address_list_for_single_user", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *_a, **_k: "access")
    monkeypatch.setattr(auth_routes, "issue_refresh_token_for_user", lambda *_a, **_k: "refresh")
    monkeypatch.setattr(auth_routes, "is_hotspot_login_required", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "_store_session_token", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "UserLoginHistory", lambda **kw: SimpleNamespace(**kw))

    app = _make_app()
    app.config.update(OTP_AUTO_AUTHORIZE_DEVICE=False)
    verify_impl = _unwrap_decorators(auth_routes.verify_otp)

    with app.test_request_context(
        "/api/auth/verify-otp",
        method="POST",
        json={
            "phone_number": "+628123000111",
            "otp": "123456",
            "client_ip": "172.16.0.22",
            "client_mac": "AA:BB:CC:00:11:22",
            "hotspot_login_context": True,
        },
        headers={"User-Agent": "pytest"},
    ):
        response, status = verify_impl()

    assert status == 200
    assert response.get_json()["access_token"] == "access"
    assert captured["bypass"] is True


def test_verify_otp_hotspot_binding_active_uses_precheck_not_post_binding(monkeypatch):
    user = SimpleNamespace(
        id="user-3",
        phone_number="+628123999000",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        mikrotik_password="pw",
        last_login_at=None,
    )

    fake_session = _FakeSession(user, scalar_value=None)
    monkeypatch.setattr(auth_routes, "db", _FakeDb(fake_session))

    monkeypatch.setattr(auth_routes, "verify_otp_from_redis", lambda *_a, **_k: True)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])

    monkeypatch.setattr(auth_routes.settings_service, "get_setting", lambda *_a, **_k: "True")
    monkeypatch.setattr(auth_routes, "resolve_client_mac", lambda *_a, **_k: (True, "AA:BB:CC:11:22:33", "ok"))

    monkeypatch.setattr(
        auth_routes,
        "apply_device_binding_for_login",
        lambda *_a, **_k: (True, "ok", "172.16.0.33"),
    )
    monkeypatch.setattr(auth_routes, "sync_address_list_for_single_user", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *_a, **_k: "access")
    monkeypatch.setattr(auth_routes, "issue_refresh_token_for_user", lambda *_a, **_k: "refresh")
    monkeypatch.setattr(auth_routes, "is_hotspot_login_required", lambda *_a, **_k: True)
    monkeypatch.setattr(auth_routes, "_store_session_token", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_routes, "UserLoginHistory", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(
        auth_routes,
        "has_hotspot_ip_binding_for_user",
        lambda *_a, **_k: (True, False, "not-found"),
    )

    @contextmanager
    def _fake_conn(*_args, **_kwargs):
        yield object()

    monkeypatch.setattr(auth_routes, "get_mikrotik_connection", _fake_conn)

    app = _make_app()
    verify_impl = _unwrap_decorators(auth_routes.verify_otp)

    with app.test_request_context(
        "/api/auth/verify-otp",
        method="POST",
        json={
            "phone_number": "+628123999000",
            "otp": "123456",
            "client_ip": "172.16.0.33",
            "client_mac": "AA:BB:CC:11:22:33",
        },
        headers={"User-Agent": "pytest"},
    ):
        response, status = verify_impl()

    assert status == 200
    payload = cast(dict, response.get_json())
    assert payload["hotspot_login_required"] is True
    assert payload["hotspot_binding_active"] is False


def test_verify_otp_rejects_hotspot_context_without_identity_in_production(monkeypatch):
    user = SimpleNamespace(
        id="user-4",
        phone_number="+628123111222",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_blocked=False,
        mikrotik_password="pw",
        last_login_at=None,
    )

    fake_session = _FakeSession(user, scalar_value=None)
    monkeypatch.setattr(auth_routes, "db", _FakeDb(fake_session))
    monkeypatch.setattr(auth_routes, "verify_otp_from_redis", lambda *_a, **_k: True)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])

    app = _make_app()
    app.config.update(
        FLASK_ENV="production",
        VERIFY_OTP_REQUIRE_TRUSTED_CAPTIVE_CONTEXT_PRODUCTION=True,
    )
    verify_impl = _unwrap_decorators(auth_routes.verify_otp)

    with app.test_request_context(
        "/api/auth/verify-otp",
        method="POST",
        json={
            "phone_number": "+628123111222",
            "otp": "123456",
            "hotspot_login_context": True,
        },
        headers={"User-Agent": "pytest"},
    ):
        response, status = verify_impl()

    assert status == 403
    assert "konteks hotspot" in cast(str, response.get_json().get("error", "")).lower()
