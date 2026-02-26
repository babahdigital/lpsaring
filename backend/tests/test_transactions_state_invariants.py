from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.db.models import Transaction, TransactionStatus
from app.infrastructure.http.transactions import reconcile_service


class _FakeMidtransTransactions:
    def status(self, _order_id: str):
        return {
            "transaction_status": "settlement",
            "transaction_id": "trx-invariant-001",
            "payment_type": "qris",
            "settlement_time": datetime.now(dt_timezone.utc).isoformat(),
        }


class _FakeMidtransCoreApi:
    def __init__(self):
        self.transactions = _FakeMidtransTransactions()


class _FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _NeverUseMikrotikConnection:
    def __enter__(self):
        raise AssertionError("Mikrotik connection must not be used when order effect is already locked/done")

    def __exit__(self, exc_type, exc, tb):
        return False


def test_reconcile_skips_duplicate_hotspot_apply_effect(monkeypatch):
    monkeypatch.setattr(reconcile_service, "get_mikrotik_connection", lambda: _NeverUseMikrotikConnection())
    app = Flask(__name__)

    transaction = SimpleNamespace(
        status=TransactionStatus.PENDING,
        midtrans_transaction_id=None,
        payment_time=None,
        payment_code=None,
        biller_code=None,
        payment_method=None,
        expiry_time=None,
        va_number=None,
        qr_code_url=None,
        midtrans_notification_payload=None,
        user_id="user-1",
    )
    session = _FakeSession()

    events = []

    with app.app_context():
        reconcile_service.reconcile_pending_transaction(
            transaction=cast(Transaction, transaction),
            session=session,
            order_id="BD-LPSR-INVARIANT-001",
            route_label="test_reconcile",
            should_allow_call=lambda _name: True,
            get_midtrans_core_api_client=lambda: _FakeMidtransCoreApi(),
            record_success=lambda _name: None,
            record_failure=lambda _name: None,
            log_transaction_event=lambda **kwargs: events.append(kwargs.get("event_type")),
            safe_parse_midtrans_datetime=lambda _value: datetime.now(dt_timezone.utc),
            extract_va_number=lambda _payload: None,
            is_qr_payment_type=lambda _payment_type: True,
            extract_qr_code_url=lambda _payload: "https://example.test/qr",
            begin_order_effect=lambda **_kwargs: (False, None),
            finish_order_effect=lambda **_kwargs: None,
        )

    assert transaction.status == TransactionStatus.SUCCESS
    assert session.rollbacks == 0
    assert session.commits >= 2
    assert "STATUS_CHECK" in events
    assert "STATUS_CHANGED" in events
