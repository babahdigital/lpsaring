from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

from flask import Flask

from app.infrastructure.http import transactions_routes
from app.infrastructure.db.models import ApprovalStatus, TransactionStatus


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeQuery:
    def __init__(self, result=None):
        self._result = result

    def get(self, _pk):
        return self._result

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, user=None, package=None, transaction=None):
        self._user = user
        self._package = package
        self._transaction = transaction
        self.added = []
        self.commits = 0

    def get(self, model, _pk):
        if model.__name__ == "User":
            return self._user
        return None

    def query(self, model):
        if model.__name__ == "Package":
            return _FakeQuery(self._package)
        if model.__name__ == "Transaction":
            return _FakeQuery(self._transaction)
        return _FakeQuery(None)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def remove(self):
        return None


class _FakeDB:
    def __init__(self, session: _FakeSession):
        self.session = session


class _FakeSnap:
    def __init__(self, capture):
        self._capture = capture

    def create_transaction(self, snap_params):
        self._capture["snap_params"] = snap_params
        return {"token": "dummy-token", "redirect_url": "https://example.test"}


class _FakeCoreApi:
    def __init__(self, capture, response):
        self._capture = capture
        self._response = response

    def charge(self, payload):
        self._capture["charge_payload"] = payload
        return self._response


class _FakeColumn:
    def __eq__(self, _other):
        return self

    def __gt__(self, _other):
        return self

    def in_(self, _values):
        return self

    def is_(self, _value):
        return self

    def desc(self):
        return self


class _FakeTransaction:
    # Provide class-level attributes to mimic SQLAlchemy columns.
    # The production code references Transaction.user_id/package_id/etc at class level
    # when building query filters.
    user_id = _FakeColumn()
    package_id = _FakeColumn()
    status = _FakeColumn()
    expiry_time = _FakeColumn()
    created_at = _FakeColumn()

    def __init__(
        self,
        id=None,
        user_id=None,
        package_id=None,
        midtrans_order_id=None,
        amount=None,
        status=None,
        expiry_time=None,
    ):
        self.id = id
        self.user_id = user_id
        self.package_id = package_id
        self.midtrans_order_id = midtrans_order_id
        self.amount = amount
        self.status = status
        self.expiry_time = expiry_time
        self.snap_token = None
        self.snap_redirect_url = None
        self.midtrans_transaction_id = None
        self.payment_method = None
        self.payment_time = None
        self.va_number = None
        self.payment_code = None
        self.biller_code = None
        self.qr_code_url = None
        self.hotspot_password = None
        self.package = None
        self.user = None


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["APP_PUBLIC_BASE_URL"] = "https://lpsaring.example"
    app.config["MIDTRANS_IS_PRODUCTION"] = False
    app.config["MIDTRANS_DEFAULT_EXPIRY_MINUTES"] = 15
    return app


def test_initiate_transaction_sets_unknown_and_expiry_and_finish_url(monkeypatch):
    user_id = uuid.uuid4()
    pkg_id = uuid.uuid4()

    fake_user = SimpleNamespace(
        id=user_id,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        full_name="User",
        phone_number="+6281234567890",
    )
    fake_package = SimpleNamespace(id=pkg_id, is_active=True, price=200000, name="Paket")

    fake_session = _FakeSession(user=fake_user, package=fake_package)
    monkeypatch.setattr(transactions_routes, "db", _FakeDB(fake_session))

    capture = {}
    monkeypatch.setattr(transactions_routes, "get_midtrans_snap_client", lambda: _FakeSnap(capture))
    monkeypatch.setattr(transactions_routes, "should_allow_call", lambda _name: True)

    app = _make_app()
    initiate_impl = _unwrap_decorators(transactions_routes.initiate_transaction)

    with app.test_request_context(
        "/api/transactions/initiate",
        method="POST",
        json={"package_id": str(pkg_id)},
    ):
        resp, status = initiate_impl(current_user_id=user_id)

    assert status == 200
    payload = resp.get_json()
    assert payload["snap_token"] == "dummy-token"
    assert payload["order_id"].startswith("BD-LPSR-")

    created_tx = next(
        obj for obj in fake_session.added if hasattr(obj, "midtrans_order_id") and hasattr(obj, "expiry_time")
    )
    assert created_tx.status == TransactionStatus.UNKNOWN
    assert isinstance(created_tx.expiry_time, datetime)
    assert created_tx.expiry_time.tzinfo is not None

    finish_url = capture["snap_params"]["callbacks"]["finish"]
    assert "status=pending" not in finish_url


def test_initiate_transaction_core_api_sets_pending_and_qr_fields(monkeypatch):
    user_id = uuid.uuid4()
    pkg_id = uuid.uuid4()

    fake_user = SimpleNamespace(
        id=user_id,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        full_name="User",
        phone_number="+6281234567890",
    )
    fake_package = SimpleNamespace(id=pkg_id, is_active=True, price=200000, name="Paket")

    fake_session = _FakeSession(user=fake_user, package=fake_package)
    monkeypatch.setattr(transactions_routes, "db", _FakeDB(fake_session))
    monkeypatch.setattr(transactions_routes, "should_allow_call", lambda _name: True)

    # Force provider mode to core_api.
    def _fake_get_setting(key, default=None):
        if key == "PAYMENT_PROVIDER_MODE":
            return "core_api"
        return default

    monkeypatch.setattr(transactions_routes.settings_service, "get_setting", _fake_get_setting)

    capture = {}
    fake_charge_resp = {
        "payment_type": "qris",
        "transaction_id": "trx-123",
        "actions": [
            {"name": "generate-qr-code", "url": "https://qris.example/qr"},
        ],
    }
    monkeypatch.setattr(
        transactions_routes, "get_midtrans_core_api_client", lambda: _FakeCoreApi(capture, fake_charge_resp)
    )

    app = _make_app()
    initiate_impl = _unwrap_decorators(transactions_routes.initiate_transaction)

    with app.test_request_context(
        "/api/transactions/initiate",
        method="POST",
        json={"package_id": str(pkg_id), "payment_method": "qris"},
    ):
        resp, status = initiate_impl(current_user_id=user_id)

    assert status == 200
    payload = resp.get_json()
    assert payload["provider_mode"] == "core_api"
    assert payload["order_id"].startswith("BD-LPSR-")
    assert "snap_token" not in payload

    created_tx = next(
        obj for obj in fake_session.added if hasattr(obj, "midtrans_order_id") and hasattr(obj, "expiry_time")
    )
    assert created_tx.status == TransactionStatus.PENDING
    assert created_tx.qr_code_url == "https://qris.example/qr"
    assert created_tx.midtrans_transaction_id == "trx-123"

    charge_payload = capture.get("charge_payload")
    assert isinstance(charge_payload, dict)
    assert charge_payload.get("payment_type") == "qris"


def test_initiate_transaction_core_api_gopay_stores_deeplink_redirect(monkeypatch):
    user_id = uuid.uuid4()
    pkg_id = uuid.uuid4()

    fake_user = SimpleNamespace(
        id=user_id,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        full_name="User",
        phone_number="+6281234567890",
    )
    fake_package = SimpleNamespace(id=pkg_id, is_active=True, price=44000, name="Paket")

    fake_session = _FakeSession(user=fake_user, package=fake_package)
    monkeypatch.setattr(transactions_routes, "db", _FakeDB(fake_session))
    monkeypatch.setattr(transactions_routes, "should_allow_call", lambda _name: True)

    def _fake_get_setting(key, default=None):
        if key == "PAYMENT_PROVIDER_MODE":
            return "core_api"
        return default

    monkeypatch.setattr(transactions_routes.settings_service, "get_setting", _fake_get_setting)

    capture = {}
    fake_charge_resp = {
        "payment_type": "gopay",
        "transaction_id": "trx-999",
        "actions": [
            {"name": "generate-qr-code", "url": "https://gopay.example/qr"},
            {"name": "deeplink-redirect", "url": "gopay://pay?ref=abc"},
        ],
    }
    monkeypatch.setattr(
        transactions_routes, "get_midtrans_core_api_client", lambda: _FakeCoreApi(capture, fake_charge_resp)
    )

    app = _make_app()
    initiate_impl = _unwrap_decorators(transactions_routes.initiate_transaction)

    with app.test_request_context(
        "/api/transactions/initiate",
        method="POST",
        json={"package_id": str(pkg_id), "payment_method": "gopay"},
    ):
        resp, status = initiate_impl(current_user_id=user_id)

    assert status == 200
    payload = resp.get_json()
    assert payload["provider_mode"] == "core_api"
    assert payload["redirect_url"] == "gopay://pay?ref=abc"

    created_tx = next(obj for obj in fake_session.added if hasattr(obj, "midtrans_order_id"))
    assert created_tx.status == TransactionStatus.PENDING
    assert created_tx.qr_code_url == "https://gopay.example/qr"
    assert created_tx.snap_redirect_url == "gopay://pay?ref=abc"


def test_cancel_transaction_sets_cancelled(monkeypatch):
    user_id = uuid.uuid4()
    order_id = "BD-LPSR-TESTORDER"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        user_id=user_id,
        status=TransactionStatus.UNKNOWN,
    )
    fake_request_user = SimpleNamespace(id=user_id, is_admin_role=False)

    fake_session = _FakeSession(user=fake_request_user, transaction=fake_tx)
    monkeypatch.setattr(transactions_routes, "db", _FakeDB(fake_session))

    app = _make_app()
    cancel_impl = _unwrap_decorators(transactions_routes.cancel_transaction)

    with app.test_request_context(
        f"/api/transactions/{order_id}/cancel",
        method="POST",
    ):
        resp, status = cancel_impl(current_user_id=user_id, order_id=order_id)

    assert status == 200
    assert resp.get_json()["status"] == TransactionStatus.CANCELLED.value
