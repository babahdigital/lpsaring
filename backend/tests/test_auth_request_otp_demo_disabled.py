from types import SimpleNamespace

from flask import Flask

from app.infrastructure.db.models import ApprovalStatus
from app.infrastructure.http import auth_routes


class _FakeExecuteResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def execute(self, *_args, **_kwargs):
        return _FakeExecuteResult(self._user)


class _FakeDb:
    def __init__(self, session):
        self.session = session


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test",
        DEMO_ALLOWED_PHONES=["+6281234567890"],
        DEMO_MODE_ENABLED=False,
        OTP_ALLOW_BYPASS=False,
    )
    return app


def _make_approved_user(phone: str):
    return SimpleNamespace(
        id="user-1",
        phone_number=phone,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
    )


def test_request_otp_blocks_demo_phone_when_demo_mode_disabled(monkeypatch):
    user = _make_approved_user("+6281234567890")
    monkeypatch.setattr(auth_routes, "db", _FakeDb(_FakeSession(user)))
    monkeypatch.setattr(auth_routes.settings_service, "get_setting_as_bool", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])
    monkeypatch.setattr(auth_routes, "generate_otp", lambda: "123456")
    monkeypatch.setattr(auth_routes, "store_otp_in_redis", lambda *_a, **_k: True)

    sent = {"called": False}
    monkeypatch.setattr(
        auth_routes,
        "send_otp_whatsapp",
        lambda *_a, **_k: sent.__setitem__("called", True),
    )

    request_impl = _unwrap_decorators(auth_routes.request_otp)
    app = _make_app()

    with app.test_request_context(
        "/api/auth/request-otp",
        method="POST",
        json={"phone_number": "+6281234567890"},
    ):
        response, status = request_impl()

    assert status == 403
    assert response.get_json()["error"] == "Mode demo sedang nonaktif."
    assert sent["called"] is False


def test_request_otp_allows_non_demo_phone_when_demo_mode_disabled(monkeypatch):
    user = _make_approved_user("+628111223344")
    monkeypatch.setattr(auth_routes, "db", _FakeDb(_FakeSession(user)))
    monkeypatch.setattr(auth_routes.settings_service, "get_setting_as_bool", lambda *_a, **_k: False)
    monkeypatch.setattr(auth_routes, "normalize_to_e164", lambda p: p)
    monkeypatch.setattr(auth_routes, "get_phone_number_variations", lambda p: [p])
    monkeypatch.setattr(auth_routes, "generate_otp", lambda: "123456")
    monkeypatch.setattr(auth_routes, "store_otp_in_redis", lambda *_a, **_k: True)

    sent = {"called": False}
    monkeypatch.setattr(
        auth_routes,
        "send_otp_whatsapp",
        lambda *_a, **_k: sent.__setitem__("called", True),
    )

    request_impl = _unwrap_decorators(auth_routes.request_otp)
    app = _make_app()

    with app.test_request_context(
        "/api/auth/request-otp",
        method="POST",
        json={"phone_number": "+628111223344"},
    ):
        response, status = request_impl()

    assert status == 200
    assert response.get_json()["message"] == "Kode OTP telah dikirim ke nomor WhatsApp Anda."
    assert sent["called"] is True
