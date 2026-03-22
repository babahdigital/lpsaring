"""Regression tests for Midtrans webhook signature hardening."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask

from app.infrastructure.http.transactions.webhook_routes import handle_notification_impl


class _FakeQuery:
    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return None


class _FakeSession:
    def query(self, *_args, **_kwargs):
        return _FakeQuery()


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        SECRET_KEY="test",
        MIDTRANS_SERVER_KEY="test-server-key",
        MIDTRANS_REQUIRE_SIGNATURE_VALIDATION=True,
        FLASK_ENV="production",
        MIDTRANS_IS_PRODUCTION=False,
    )
    return flask_app


@pytest.fixture
def signature_payload():
    order_id = "ORDER-123"
    status_code = "200"
    gross_amount = "100000.00"
    server_key = "test-server-key"

    string_to_hash = f"{order_id}{status_code}{gross_amount}{server_key}"
    signature_key = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()

    return {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross_amount,
        "signature_key": signature_key,
        "transaction_status": "capture",
        "fraud_status": "accept",
    }


def _call_handler(app, payload, *, is_duplicate=False):
    with app.test_request_context(
        "/api/transactions/webhook/midtrans/notification",
        method="POST",
        json=payload,
    ):
        return handle_notification_impl(
            db=SimpleNamespace(session=_FakeSession()),
            is_duplicate_webhook=lambda *_args, **_kwargs: is_duplicate,
            increment_metric=lambda *_args, **_kwargs: None,
            log_transaction_event=lambda *_args, **_kwargs: None,
            safe_parse_midtrans_datetime=lambda *_args, **_kwargs: None,
            extract_va_number=lambda *_args, **_kwargs: None,
            extract_qr_code_url=lambda *_args, **_kwargs: None,
            is_qr_payment_type=lambda *_args, **_kwargs: False,
            is_debt_settlement_order_id=lambda *_args, **_kwargs: False,
            apply_debt_settlement_on_success=lambda *_args, **_kwargs: None,
            send_whatsapp_invoice_task=None,
            format_currency_fn=lambda value: value,
            begin_order_effect=lambda *_args, **_kwargs: None,
            finish_order_effect=lambda *_args, **_kwargs: None,
        )


def test_uses_constant_time_comparison():
    sig_correct = "abcdef1234567890"
    sig_attack_1 = "abcdef0000000000"
    sig_attack_2 = "0bcdef1234567890"

    with patch("hmac.compare_digest") as mock_compare:
        mock_compare.return_value = False

        result1 = mock_compare(sig_correct, sig_attack_1)
        result2 = mock_compare(sig_correct, sig_attack_2)

    assert result1 is False
    assert result2 is False
    assert mock_compare.call_count == 2


def test_signature_validation_invalid_signature_returns_403(app, signature_payload):
    signature_payload["signature_key"] = "invalid_signature_key"

    response, status = _call_handler(app, signature_payload)

    assert status == 403
    assert "Signature tidak valid" in response.get_json()["message"]


def test_signature_validation_valid_signature_returns_ok(app, signature_payload):
    response, status = _call_handler(app, signature_payload, is_duplicate=True)

    assert status == 200
    assert response.get_json()["status"] == "ok"


def test_missing_signature_key_returns_403(app, signature_payload):
    del signature_payload["signature_key"]

    response, status = _call_handler(app, signature_payload)

    assert status == 403


def test_hmac_compare_digest_is_constant_time():
    sig1 = "a" * 128
    sig_early = "b" + sig1[1:]
    sig_late = sig1[:-1] + "b"

    assert hmac.compare_digest(sig1, sig_early) is False
    assert hmac.compare_digest(sig1, sig_late) is False
    assert hmac.compare_digest(sig1, sig1) is True
