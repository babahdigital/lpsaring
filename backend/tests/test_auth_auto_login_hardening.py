from __future__ import annotations

from typing import Any
from types import SimpleNamespace
from http import HTTPStatus

from flask import Flask

from app.infrastructure.http.auth_contexts.login_handlers import auto_login_impl


class _SchemaStub:
    def __init__(self, **kwargs):
        self._data = kwargs

    def model_dump(self):
        return dict(self._data)


class _Col:
    def __eq__(self, _other):
        return self

    def is_(self, _other):
        return self

    def desc(self):
        return self


class _UserModel:
    id = _Col()
    approval_status = _Col()
    is_active = _Col()


class _UserDeviceModel:
    id = _Col()
    user_id = _Col()
    is_authorized = _Col()
    device_mac = _Col()
    mac_address = _Col()
    last_seen = _Col()


class _FakeQuery:
    def __init__(self, device):
        self._device = device

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._device

    def all(self):
        if self._device is None:
            return []
        if isinstance(self._device, list):
            return self._device
        return [self._device]


class _FakeSession:
    def __init__(self, device):
        self._device = device

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._device)

    def add(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class _SequencedQuery:
    def __init__(self, devices):
        self._devices = devices

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        value = self._devices.pop(0) if self._devices else None
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def all(self):
        if not self._devices:
            return []
        value = self._devices.pop(0)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


class _SequencedSession:
    def __init__(self, devices):
        self._devices = list(devices)

    def query(self, *_args, **_kwargs):
        return _SequencedQuery(self._devices)

    def add(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class _SequencedDb:
    def __init__(self, devices):
        self.session = _SequencedSession(devices)


class _FakeDb:
    def __init__(self, device):
        self.session = _FakeSession(device)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="unit-test", JWT_SECRET_KEY="unit-jwt", JWT_ALGORITHM="HS256")
    return app


def _deps(db_obj):
    deps: dict[str, Any] = dict(
        db=db_obj,
        User=_UserModel,
        UserDevice=_UserDeviceModel,
        ApprovalStatus=SimpleNamespace(APPROVED="APPROVED"),
        UserRole=SimpleNamespace(USER="USER", KOMANDAN="KOMANDAN", ADMIN="ADMIN", SUPER_ADMIN="SUPER_ADMIN"),
        UserLoginHistory=lambda **kw: SimpleNamespace(**kw),
        AuthErrorResponseSchema=_SchemaStub,
        VerifyOtpResponseSchema=_SchemaStub,
        get_client_ip=lambda: None,
        normalize_mac=lambda v: str(v or "").strip().upper() if v else None,
        get_phone_number_variations=lambda v: [v],
        get_mikrotik_connection=lambda: None,
        sync_address_list_for_single_user=lambda *_a, **_k: True,
        create_access_token=lambda **_k: "access-token",
        issue_refresh_token_for_user=lambda *_a, **_k: "refresh-token",
        set_auth_cookie=lambda *_a, **_k: None,
        set_refresh_cookie=lambda *_a, **_k: None,
        build_status_error=lambda status, message: ({"status": status, "message": message}, HTTPStatus.FORBIDDEN),
        request=SimpleNamespace(args={}, headers={"User-Agent": "pytest"}),
    )
    return deps


def test_auto_login_rejects_ip_outside_hotspot_cidr(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: False)

    deps = _deps(_FakeDb(device=None))
    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
        apply_device_binding_for_login=lambda *_a, **_k: (True, "ok", "172.16.2.10"),
    )

    with app.test_request_context("/api/auth/auto-login", method="POST", json={"client_ip": "8.8.8.8"}):
        response, status = auto_login_impl(payload={"client_ip": "8.8.8.8"}, **deps)

    assert status == HTTPStatus.FORBIDDEN
    assert "jaringan hotspot" in str(response.get_json().get("error", "")).lower()


def test_auto_login_rejects_request_mac_mismatch(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    deps = _deps(_FakeDb(device=None))
    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
        apply_device_binding_for_login=lambda *_a, **_k: (True, "ok", "172.16.2.10"),
    )

    payload = {"client_ip": "172.16.2.10", "client_mac": "00:11:22:33:44:55"}
    with app.test_request_context("/api/auth/auto-login", method="POST", json=payload):
        response, status = auto_login_impl(payload=payload, **deps)

    assert status == HTTPStatus.FORBIDDEN
    assert "identitas perangkat" in str(response.get_json().get("error", "")).lower()


def test_auto_login_uses_router_verified_mac_as_authority(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    user = SimpleNamespace(
        id="user-1",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        last_login_at=None,
    )
    device = SimpleNamespace(user=user)

    deps = _deps(_FakeDb(device=device))
    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
        apply_device_binding_for_login=lambda *_a, **_k: (True, "ok", "172.16.2.10"),
    )

    payload = {"client_ip": "172.16.2.10", "client_mac": "AA:BB:CC:DD:EE:FF"}
    with app.test_request_context("/api/auth/auto-login", method="POST", json=payload):
        response, status = auto_login_impl(payload=payload, **deps)

    assert status == HTTPStatus.OK
    assert response.get_json().get("access_token") == "access-token"


def test_auto_login_extracts_identity_hint_from_referer(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    user = SimpleNamespace(
        id="user-ref",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        last_login_at=None,
    )
    device = SimpleNamespace(user=user)

    deps = _deps(_FakeDb(device=device))
    deps["request"] = SimpleNamespace(
        args={},
        headers={
            "User-Agent": "pytest",
            "Referer": (
                "https://lpsaring.babahdigital.net/captive?link_login_only=http://login.home.arpa/login"
                "&client_mac=AA%253ABB%253ACC%253ADD%253AEE%253AFF&client_ip=172.16.2.55"
            ),
        },
    )
    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:FF", "ok"),
        apply_device_binding_for_login=lambda *_a, **kwargs: (
            True,
            "ok",
            kwargs.get("client_ip") or "172.16.2.55",
        ),
    )

    with app.test_request_context("/api/auth/auto-login", method="POST", json={}):
        response, status = auto_login_impl(payload={}, **deps)

    assert status == HTTPStatus.OK
    assert response.get_json().get("access_token") == "access-token"


def test_auto_login_self_heals_known_device_when_authorized_flag_missing(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    captured: dict[str, Any] = {"bypass": None}

    user = SimpleNamespace(
        id="user-self-heal",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        is_active=True,
        approval_status="APPROVED",
        last_login_at=None,
    )
    known_device = SimpleNamespace(user=user)

    deps = _deps(_SequencedDb(devices=[None, [known_device]]))

    def _apply_binding(*_args, **kwargs):
        captured["bypass"] = kwargs.get("bypass_explicit_auth")
        return True, "Perangkat terotorisasi", "172.16.2.88"

    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:DD:EE:99", "ok"),
        apply_device_binding_for_login=_apply_binding,
    )

    payload = {"client_ip": "172.16.2.88", "client_mac": "AA:BB:CC:DD:EE:99"}
    with app.test_request_context("/api/auth/auto-login", method="POST", json=payload):
        response, status = auto_login_impl(payload=payload, **deps)

    assert status == HTTPStatus.OK
    assert response.get_json().get("access_token") == "access-token"
    assert captured["bypass"] is True


def test_auto_login_resumes_with_valid_jwt_session_when_device_not_authorized(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms
    from app.infrastructure.http.auth_contexts import login_handlers as lh

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    captured: dict[str, Any] = {"bypass": None}
    trusted_user = SimpleNamespace(
        id="user-jwt",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        is_active=True,
        approval_status="APPROVED",
        last_login_at=None,
    )

    deps = _deps(_SequencedDb(devices=[None, []]))
    deps["request"] = SimpleNamespace(
        args={},
        cookies={"auth_token": "valid-token"},
        headers={"User-Agent": "pytest"},
    )

    monkeypatch.setattr(lh.jwt, "decode", lambda *_a, **_k: {"sub": "user-jwt"})

    original_get = deps["db"].session.__class__.__dict__.get("get")
    deps["db"].session.get = lambda _model, user_id: trusted_user if str(user_id) == "user-jwt" else None

    def _apply_binding(*_args, **kwargs):
        captured["bypass"] = kwargs.get("bypass_explicit_auth")
        return True, "Perangkat terotorisasi", "172.16.2.120"

    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:00:00:01", "ok"),
        apply_device_binding_for_login=_apply_binding,
    )

    payload = {"client_ip": "172.16.2.120", "client_mac": "AA:BB:CC:00:00:01"}
    with app.test_request_context("/api/auth/auto-login", method="POST", json=payload):
        response, status = auto_login_impl(payload=payload, **deps)

    if original_get is None:
        delattr(deps["db"].session, "get")
    else:
        deps["db"].session.get = original_get

    assert status == HTTPStatus.OK
    assert response.get_json().get("access_token") == "access-token"
    assert captured["bypass"] is True


def test_auto_login_jwt_resume_blocked_when_mac_owned_by_other_user(monkeypatch):
    app = _make_app()

    from app.services import device_management_service as dms
    from app.infrastructure.http.auth_contexts import login_handlers as lh

    monkeypatch.setattr(dms, "_is_client_ip_allowed", lambda *_a, **_k: True)

    trusted_user = SimpleNamespace(
        id="user-jwt-a",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        is_active=True,
        approval_status="APPROVED",
        last_login_at=None,
    )
    other_user = SimpleNamespace(
        id="user-jwt-b",
        role=SimpleNamespace(value="USER"),
        is_blocked=False,
        is_active=True,
        approval_status="APPROVED",
        last_login_at=None,
    )
    owner_device = SimpleNamespace(user=other_user)

    deps = _deps(_SequencedDb(devices=[None, [owner_device], [owner_device]]))
    deps["request"] = SimpleNamespace(
        args={},
        cookies={"auth_token": "valid-token"},
        headers={"User-Agent": "pytest"},
    )

    monkeypatch.setattr(lh.jwt, "decode", lambda *_a, **_k: {"sub": "user-jwt-a"})
    deps["db"].session.get = lambda _model, user_id: trusted_user if str(user_id) == "user-jwt-a" else None

    deps.update(
        resolve_client_mac=lambda *_a, **_k: (True, "AA:BB:CC:00:00:02", "ok"),
        apply_device_binding_for_login=lambda *_a, **_k: (True, "ok", "172.16.2.121"),
    )

    payload = {"client_ip": "172.16.2.121", "client_mac": "AA:BB:CC:00:00:02"}
    with app.test_request_context("/api/auth/auto-login", method="POST", json=payload):
        response, status = auto_login_impl(payload=payload, **deps)

    assert status == HTTPStatus.UNAUTHORIZED
    assert "tidak cocok" in str(response.get_json().get("error", "")).lower()
