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


class _FakeDb:
    def __init__(self, device):
        self.session = _FakeSession(device)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="unit-test")
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
        get_hotspot_active_session_by_ip=lambda *_a, **_k: (True, None, "unused"),
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
