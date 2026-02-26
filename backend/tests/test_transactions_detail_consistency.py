from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

from flask import Flask
import midtransclient

from app.infrastructure.db.models import Transaction, TransactionStatus
from app.infrastructure.http.transactions import authenticated_routes, public_routes
from app.infrastructure.http.transactions.reconcile_service import reconcile_pending_transaction


class _FakeLoad:
    def selectinload(self, *_args, **_kwargs):
        return self


def _fake_selectinload(*_args, **_kwargs):
    return _FakeLoad()


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
    def __init__(self, transaction=None, requester=None, debt=None):
        self._transaction = transaction
        self._requester = requester
        self._debt = debt
        self.is_active = True

    def query(self, model):
        if model.__name__ == "Transaction":
            return _FakeQuery(self._transaction)
        return _FakeQuery(None)

    def get(self, model, _pk):
        if model.__name__ == "User":
            return self._requester
        if model.__name__ == "UserQuotaDebt":
            return self._debt
        return None

    def refresh(self, _obj):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def remove(self):
        return None


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


def _build_transaction_and_user(order_id: str):
    user_id = uuid.uuid4()
    package = SimpleNamespace(
        id=uuid.uuid4(),
        name="Paket 10GB",
        description="Paket bulanan",
        price=55000,
        data_quota_gb=10,
        profile=None,
    )
    user = SimpleNamespace(
        id=user_id,
        phone_number="+628123456789",
        full_name="User Test",
        quota_expiry_date=None,
        is_unlimited_user=False,
        quota_debt_auto_mb=0,
    )
    transaction = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        midtrans_order_id=order_id,
        midtrans_transaction_id="trx-123",
        status=TransactionStatus.PENDING,
        amount=55000,
        payment_method="qris",
        snap_token=None,
        snap_redirect_url="https://pay.example/redirect",
        payment_time=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url="https://qris.example/qr",
        hotspot_password="HOTSPOT-SECRET",
        package=package,
        user=user,
    )
    requester = SimpleNamespace(id=user_id, is_admin_role=False)
    return transaction, requester


def test_transaction_detail_auth_and_public_consistent_shared_fields(monkeypatch):
    order_id = "BD-LPSR-CONSIST-001"
    tx_auth, requester_auth = _build_transaction_and_user(order_id)
    tx_public, _requester_public = _build_transaction_and_user(order_id)

    reconcile_calls: list[tuple[str, str]] = []

    def _fake_reconcile(**kwargs):
        route_label = str(kwargs.get("route_label", ""))
        reconcile_calls.append((route_label, kwargs["order_id"]))

    monkeypatch.setattr(authenticated_routes, "reconcile_pending_transaction", _fake_reconcile)
    monkeypatch.setattr(public_routes, "reconcile_pending_transaction", _fake_reconcile)
    monkeypatch.setattr(public_routes, "verify_transaction_status_token", lambda *_a, **_kw: True)

    app = _make_app()

    with app.app_context():
        auth_response, auth_status = authenticated_routes.get_transaction_by_order_id_impl(
            current_user_id=requester_auth.id,
            order_id=order_id,
            db=SimpleNamespace(),
            session=_FakeSession(transaction=tx_auth, requester=requester_auth),
            selectinload=_fake_selectinload,
            Package=SimpleNamespace(profile=None),
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: None,
            record_success=lambda _name: None,
            record_failure=lambda _name: None,
            log_transaction_event=lambda **_kwargs: None,
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda _pm: False,
            extract_qr_code_url=lambda _payload: None,
            is_debt_settlement_order_id=lambda _oid: False,
            extract_manual_debt_id_from_order_id=lambda _oid: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

        public_response, public_status = public_routes.get_transaction_by_order_id_public_impl(
            order_id=order_id,
            db=SimpleNamespace(session=_FakeSession(transaction=tx_public, requester=None)),
            request=SimpleNamespace(args={"t": "VALIDTOKEN"}),
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: None,
            record_success=lambda _name: None,
            record_failure=lambda _name: None,
            log_transaction_event=lambda **_kwargs: None,
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            extract_qr_code_url=lambda _payload: None,
            is_qr_payment_type=lambda _pm: False,
            is_debt_settlement_order_id=lambda _oid: False,
            extract_manual_debt_id_from_order_id=lambda _oid: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert auth_status == 200
    assert public_status == 200

    auth_payload = auth_response.get_json()
    public_payload = public_response.get_json()

    shared_fields = [
        "midtrans_order_id",
        "midtrans_transaction_id",
        "status",
        "amount",
        "payment_method",
        "snap_token",
        "snap_redirect_url",
        "deeplink_redirect_url",
        "va_number",
        "payment_code",
        "biller_code",
        "qr_code_url",
        "purpose",
    ]
    for field in shared_fields:
        assert auth_payload.get(field) == public_payload.get(field), f"field mismatch: {field}"

    assert len(reconcile_calls) == 2
    assert ("auth_get_transaction_by_order_id", order_id) in reconcile_calls
    assert ("public_get_transaction_by_order_id", order_id) in reconcile_calls


def test_transaction_detail_public_masks_sensitive_user_and_password(monkeypatch):
    order_id = "BD-LPSR-CONSIST-002"
    tx_public, _requester_public = _build_transaction_and_user(order_id)

    monkeypatch.setattr(public_routes, "reconcile_pending_transaction", lambda **_kwargs: None)
    monkeypatch.setattr(public_routes, "verify_transaction_status_token", lambda *_a, **_kw: True)

    app = _make_app()

    with app.app_context():
        response, status = public_routes.get_transaction_by_order_id_public_impl(
            order_id=order_id,
            db=SimpleNamespace(session=_FakeSession(transaction=tx_public, requester=None)),
            request=SimpleNamespace(args={"t": "VALIDTOKEN"}),
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: None,
            record_success=lambda _name: None,
            record_failure=lambda _name: None,
            log_transaction_event=lambda **_kwargs: None,
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            extract_qr_code_url=lambda _payload: None,
            is_qr_payment_type=lambda _pm: False,
            is_debt_settlement_order_id=lambda _oid: False,
            extract_manual_debt_id_from_order_id=lambda _oid: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert status == 200
    payload = response.get_json()
    assert payload.get("hotspot_password") is None
    assert payload.get("user", {}).get("phone_number") == "-"
    assert payload.get("user", {}).get("id") == ""


class _FakeTxStatusApi:
    def __init__(self, payload):
        self._payload = payload

    def status(self, _order_id):
        return self._payload


class _FakeCoreApi:
    def __init__(self, payload):
        self.transactions = _FakeTxStatusApi(payload)


class _ReconcileSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def query(self, _model):
        return _FakeQuery(None)


def _build_reconcile_tx(order_id: str, status: TransactionStatus = TransactionStatus.PENDING):
    return SimpleNamespace(
        id=uuid.uuid4(),
        midtrans_order_id=order_id,
        midtrans_transaction_id=None,
        status=status,
        amount=25000,
        payment_method=None,
        expiry_time=None,
        va_number=None,
        payment_code=None,
        biller_code=None,
        qr_code_url=None,
        payment_time=None,
        midtrans_notification_payload=None,
    )


def test_reconcile_pending_transaction_sets_success_and_logs_status_changed(monkeypatch):
    order_id = "BD-LPSR-RECON-001"
    tx = cast(Transaction, _build_reconcile_tx(order_id, TransactionStatus.PENDING))
    session = _ReconcileSession()
    events: list[str] = []
    metrics: list[str] = []

    monkeypatch.setattr(
        "app.infrastructure.http.transactions.reconcile_service.get_mikrotik_connection",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.infrastructure.http.transactions.reconcile_service.apply_package_and_sync_to_mikrotik",
        lambda *_args, **_kwargs: (True, "ok"),
    )

    app = _make_app()
    with app.app_context():
        reconcile_pending_transaction(
            transaction=tx,
            session=session,
            order_id=order_id,
            route_label="test_reconcile",
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: _FakeCoreApi(
                {
                    "transaction_status": "settlement",
                    "transaction_id": "trx-settle-1",
                    "payment_type": "qris",
                    "settlement_time": "2026-02-26T10:10:00+07:00",
                }
            ),
            record_success=lambda name: metrics.append(f"success:{name}"),
            record_failure=lambda name: metrics.append(f"failure:{name}"),
            log_transaction_event=lambda **kwargs: events.append(str(kwargs.get("event_type"))),
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda payment_type: str(payment_type).lower() == "qris",
            extract_qr_code_url=lambda _payload: "https://qris.example/qr",
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert tx.status == TransactionStatus.SUCCESS
    assert tx.midtrans_transaction_id == "trx-settle-1"
    assert "STATUS_CHECK" in events
    assert "STATUS_CHANGED" in events
    assert "success:midtrans" in metrics
    assert session.commits >= 2


def test_reconcile_pending_transaction_sets_expired_and_logs_status_changed():
    order_id = "BD-LPSR-RECON-002"
    tx = cast(Transaction, _build_reconcile_tx(order_id, TransactionStatus.PENDING))
    session = _ReconcileSession()
    events: list[str] = []
    metrics: list[str] = []

    app = _make_app()
    with app.app_context():
        reconcile_pending_transaction(
            transaction=tx,
            session=session,
            order_id=order_id,
            route_label="test_reconcile",
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: _FakeCoreApi(
                {
                    "transaction_status": "expire",
                    "transaction_id": "trx-exp-1",
                    "payment_type": "bank_transfer",
                }
            ),
            record_success=lambda name: metrics.append(f"success:{name}"),
            record_failure=lambda name: metrics.append(f"failure:{name}"),
            log_transaction_event=lambda **kwargs: events.append(str(kwargs.get("event_type"))),
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda _payment_type: False,
            extract_qr_code_url=lambda _payload: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert tx.status == TransactionStatus.EXPIRED
    assert "STATUS_CHECK" in events
    assert "STATUS_CHANGED" in events
    assert "success:midtrans" in metrics
    assert session.commits >= 2


def test_reconcile_pending_transaction_records_failure_when_midtrans_call_blocked():
    order_id = "BD-LPSR-RECON-003"
    tx = cast(Transaction, _build_reconcile_tx(order_id, TransactionStatus.PENDING))
    session = _ReconcileSession()
    events: list[str] = []
    metrics: list[str] = []

    app = _make_app()
    with app.app_context():
        reconcile_pending_transaction(
            transaction=tx,
            session=session,
            order_id=order_id,
            route_label="test_reconcile",
            should_allow_call=lambda _name: False,
            get_midtrans_core_api_client=lambda: _FakeCoreApi({"transaction_status": "settlement"}),
            record_success=lambda name: metrics.append(f"success:{name}"),
            record_failure=lambda name: metrics.append(f"failure:{name}"),
            log_transaction_event=lambda **kwargs: events.append(str(kwargs.get("event_type"))),
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda _payment_type: False,
            extract_qr_code_url=lambda _payload: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert tx.status == TransactionStatus.PENDING
    assert "STATUS_CHECK" not in events
    assert "STATUS_CHANGED" not in events
    assert "failure:midtrans" in metrics
    assert "success:midtrans" not in metrics


def test_reconcile_pending_transaction_records_failure_when_midtrans_api_error():
    order_id = "BD-LPSR-RECON-004"
    tx = cast(Transaction, _build_reconcile_tx(order_id, TransactionStatus.PENDING))
    session = _ReconcileSession()
    events: list[str] = []
    metrics: list[str] = []

    class _CoreApiError:
        class transactions:
            @staticmethod
            def status(_order_id):
                raise midtransclient.error_midtrans.MidtransAPIError("forced midtrans error")

    app = _make_app()
    with app.app_context():
        reconcile_pending_transaction(
            transaction=tx,
            session=session,
            order_id=order_id,
            route_label="test_reconcile",
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: _CoreApiError(),
            record_success=lambda name: metrics.append(f"success:{name}"),
            record_failure=lambda name: metrics.append(f"failure:{name}"),
            log_transaction_event=lambda **kwargs: events.append(str(kwargs.get("event_type"))),
            safe_parse_midtrans_datetime=lambda _v: None,
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda _payment_type: False,
            extract_qr_code_url=lambda _payload: None,
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert tx.status == TransactionStatus.PENDING
    assert "STATUS_CHECK" not in events
    assert "STATUS_CHANGED" not in events
    assert "failure:midtrans" in metrics
    assert "success:midtrans" not in metrics
