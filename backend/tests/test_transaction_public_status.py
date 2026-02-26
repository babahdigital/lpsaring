from __future__ import annotations

import uuid
from types import SimpleNamespace

from flask import Flask

from app.infrastructure.http import transactions_routes
from app.infrastructure.db.models import TransactionStatus
from app.services.transaction_status_link_service import generate_transaction_status_token


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


class _FakeQuery:
    def __init__(self, result=None):
        self._result = result

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, transaction=None):
        self._transaction = transaction
        self.added = []

    def query(self, model):
        if model.__name__ == "Transaction":
            return _FakeQuery(self._transaction)
        return _FakeQuery(None)

    def get(self, _model, _pk):
        return None

    def refresh(self, _obj):
        return None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        return None

    def rollback(self):
        return None

    def remove(self):
        return None


class _FakeDB:
    def __init__(self, session: _FakeSession):
        self.session = session


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["APP_PUBLIC_BASE_URL"] = "https://lpsaring.example"
    return app


def test_public_status_endpoint_requires_valid_token(monkeypatch):
    order_id = "BD-LPSR-TESTORDER"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        midtrans_transaction_id=None,
        status=TransactionStatus.PENDING,
        amount=44000,
        payment_method="qris",
        snap_token=None,
        snap_redirect_url=None,
        payment_time=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url="https://qris.example/qr",
        hotspot_password=None,
        package=None,
        user=None,
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))
    # Avoid Midtrans reconciliation in this test.
    monkeypatch.setattr(transactions_routes, "should_allow_call", lambda _name: False)

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.get_transaction_by_order_id_public)

    with app.test_request_context(
        f"/api/transactions/public/by-order-id/{order_id}?t=BADTOKEN",
        method="GET",
    ):
        try:
            impl(order_id=order_id)
            assert False, "expected abort"
        except Exception as e:
            # Werkzeug HTTPException has code attribute.
            assert getattr(e, "code", None) in (401, 403)


def test_public_status_endpoint_rejects_missing_token(monkeypatch):
    order_id = "BD-LPSR-MISSING-TOKEN"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        midtrans_transaction_id=None,
        status=TransactionStatus.PENDING,
        amount=55000,
        payment_method="qris",
        snap_token=None,
        snap_redirect_url=None,
        payment_time=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url=None,
        hotspot_password=None,
        package=None,
        user=None,
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.get_transaction_by_order_id_public)

    with app.test_request_context(
        f"/api/transactions/public/by-order-id/{order_id}",
        method="GET",
    ):
        try:
            impl(order_id=order_id)
            assert False, "expected abort"
        except Exception as e:
            assert getattr(e, "code", None) in (401, 403)


def test_public_status_endpoint_returns_data_with_valid_token(monkeypatch):
    order_id = "BD-LPSR-TESTORDER"

    fake_pkg = SimpleNamespace(id=uuid.uuid4(), name="Paket", description=None, price=44000, data_quota_gb=1)
    fake_user = SimpleNamespace(id=uuid.uuid4(), phone_number="+628123", full_name="User", quota_expiry_date=None)
    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        midtrans_transaction_id=None,
        status=TransactionStatus.SUCCESS,
        amount=44000,
        payment_method="qris",
        snap_token=None,
        snap_redirect_url=None,
        payment_time=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url="https://qris.example/qr",
        hotspot_password="SHOULD_NOT_LEAK",
        package=fake_pkg,
        user=fake_user,
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.get_transaction_by_order_id_public)

    with app.app_context():
        token = generate_transaction_status_token(order_id)

    with app.test_request_context(
        f"/api/transactions/public/by-order-id/{order_id}?t={token}",
        method="GET",
    ):
        resp, status = impl(order_id=order_id)

    assert status == 200
    payload = resp.get_json()
    assert payload["midtrans_order_id"] == order_id
    assert payload["status"] == TransactionStatus.SUCCESS.value
    assert payload.get("hotspot_password") is None
    assert payload.get("user", {}).get("phone_number") == "-"
    assert payload.get("user", {}).get("id") == ""


def test_public_status_endpoint_rejects_malformed_token(monkeypatch):
    order_id = "BD-LPSR-MALFORMED-TOKEN"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        midtrans_transaction_id=None,
        status=TransactionStatus.PENDING,
        amount=44000,
        payment_method="qris",
        snap_token=None,
        snap_redirect_url=None,
        payment_time=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url=None,
        hotspot_password=None,
        package=None,
        user=None,
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.get_transaction_by_order_id_public)

    with app.test_request_context(
        f"/api/transactions/public/by-order-id/{order_id}?t=not-a-valid-status-token",
        method="GET",
    ):
        try:
            impl(order_id=order_id)
            assert False, "expected abort"
        except Exception as e:
            assert getattr(e, "code", None) in (401, 403)


def test_public_cancel_endpoint_sets_cancelled_for_unknown(monkeypatch):
    order_id = "BD-LPSR-TESTORDER"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        status=TransactionStatus.UNKNOWN,
    )

    fake_session = _FakeSession(transaction=fake_tx)
    monkeypatch.setattr(transactions_routes, "db", _FakeDB(fake_session))

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.cancel_transaction_public)

    with app.app_context():
        token = generate_transaction_status_token(order_id)

    with app.test_request_context(
        f"/api/transactions/public/{order_id}/cancel?t={token}",
        method="POST",
    ):
        resp, status = impl(order_id=order_id)

    assert status == 200
    payload = resp.get_json()
    assert payload.get("success") is True
    assert payload.get("status") == TransactionStatus.CANCELLED.value
    assert fake_tx.status == TransactionStatus.CANCELLED
    assert len(fake_session.added) >= 1


def test_public_cancel_endpoint_rejects_success_transaction(monkeypatch):
    order_id = "BD-LPSR-TESTORDER"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        status=TransactionStatus.SUCCESS,
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.cancel_transaction_public)

    with app.app_context():
        token = generate_transaction_status_token(order_id)

    with app.test_request_context(
        f"/api/transactions/public/{order_id}/cancel?t={token}",
        method="POST",
    ):
        resp, status = impl(order_id=order_id)

    assert status == 400
    payload = resp.get_json()
    assert payload.get("success") is False


def test_public_qr_endpoint_proxies_image(monkeypatch):
    order_id = "BD-LPSR-TESTORDER"

    fake_tx = SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        status=TransactionStatus.PENDING,
        qr_code_url="https://qris.example/qr",
    )

    monkeypatch.setattr(transactions_routes, "db", _FakeDB(_FakeSession(transaction=fake_tx)))

    class _Resp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = b"PNGDATA"

    monkeypatch.setattr(transactions_routes.requests, "get", lambda *_a, **_kw: _Resp())

    app = _make_app()
    impl = _unwrap_decorators(transactions_routes.get_transaction_qr_public)

    with app.app_context():
        token = generate_transaction_status_token(order_id)

    with app.test_request_context(
        f"/api/transactions/public/{order_id}/qr?t={token}",
        method="GET",
    ):
        resp = impl(midtrans_order_id=order_id)

    assert resp.status_code == 200
    assert resp.data == b"PNGDATA"
    assert "image/png" in (resp.headers.get("Content-Type") or "")
