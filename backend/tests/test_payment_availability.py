from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from flask import Flask

from app.infrastructure.http import public_routes
from app.infrastructure.http.transactions import initiation_routes
from app.utils import payment_availability


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE"] = (
        "Pembelian sementara ditutup. Layanan pembayaran sedang mengalami gangguan."
    )
    return app


def test_payment_gateway_public_status_reports_open_circuit(monkeypatch):
    app = _make_app()
    open_until = datetime.now(dt_timezone.utc) + timedelta(seconds=45)

    monkeypatch.setattr(
        payment_availability,
        "get_circuit_status",
        lambda _name: {
            "state": "open",
            "is_open": True,
            "open_until_timestamp": int(open_until.timestamp()),
            "retry_after_seconds": 45,
        },
    )

    with app.app_context():
        payload = payment_availability.get_payment_gateway_public_status()

    assert payload["available"] is False
    assert payload["message"] == app.config["PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE"]
    assert payload["reason"] == "payment_gateway_unavailable"
    assert payload["circuit_state"] == "open"
    assert payload["retry_after_seconds"] == 45
    assert payload["open_until"] == open_until.replace(microsecond=0).isoformat()


def test_public_payment_availability_route_is_no_store(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(
        public_routes,
        "get_payment_gateway_public_status",
        lambda: {
            "available": False,
            "message": app.config["PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE"],
            "reason": "payment_gateway_unavailable",
            "circuit_name": "midtrans",
            "circuit_state": "open",
            "retry_after_seconds": 30,
            "checked_at": "2026-03-21T00:00:00+00:00",
            "checked_at_display": "21-03-2026 08:00:00",
            "open_until": "2026-03-21T00:00:30+00:00",
            "open_until_display": "21-03-2026 08:00:30",
        },
    )

    with app.app_context(), app.test_request_context("/api/settings/payment-availability", method="GET"):
        response, status = public_routes.get_public_payment_availability()

    assert status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["available"] is False


def test_midtrans_user_message_uses_payment_availability_message_for_5xx():
    app = _make_app()

    with app.app_context():
        message = initiation_routes._build_midtrans_user_message(
            'API response: `{"status_code":"500","status_message":"Internal Server Error"}`'
        )

    assert message == app.config["PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE"]