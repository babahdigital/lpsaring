from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from flask import current_app

from app.utils.circuit_breaker import get_circuit_status
from app.utils.formatters import format_app_datetime_display


DEFAULT_PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE = (
    "Pembelian sementara ditutup. Layanan pembayaran sedang mengalami gangguan."
)


def get_payment_gateway_unavailable_message() -> str:
    raw_message = current_app.config.get(
        "PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE",
        DEFAULT_PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE,
    )
    message = str(raw_message or "").strip()
    if message:
        return message
    return DEFAULT_PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE


def get_payment_gateway_public_status() -> dict[str, object]:
    checked_at = datetime.now(dt_timezone.utc)
    circuit_status = get_circuit_status("midtrans")

    open_until_timestamp = int(circuit_status.get("open_until_timestamp", 0) or 0)
    open_until = None
    if open_until_timestamp > 0:
        open_until = datetime.fromtimestamp(open_until_timestamp, tz=dt_timezone.utc)

    available = not bool(circuit_status.get("is_open"))
    retry_after_seconds = int(circuit_status.get("retry_after_seconds", 0) or 0)

    payload: dict[str, object] = {
        "available": available,
        "message": None if available else get_payment_gateway_unavailable_message(),
        "reason": None if available else "payment_gateway_unavailable",
        "circuit_name": "midtrans",
        "circuit_state": str(circuit_status.get("state") or "closed"),
        "retry_after_seconds": retry_after_seconds if not available else 0,
        "checked_at": checked_at.isoformat(),
        "checked_at_display": format_app_datetime_display(checked_at, fallback="-"),
        "open_until": open_until.isoformat() if open_until is not None else None,
        "open_until_display": (
            format_app_datetime_display(open_until, fallback="-") if open_until is not None else None
        ),
    }
    return payload