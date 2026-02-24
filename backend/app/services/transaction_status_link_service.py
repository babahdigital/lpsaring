from __future__ import annotations

import itsdangerous
from flask import current_app


def _get_serializer() -> itsdangerous.URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("SECRET_KEY tidak diatur di konfigurasi aplikasi.")
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt="transaction-status-access")


def get_transaction_status_token_max_age_seconds() -> int:
    try:
        value = int(current_app.config.get("TRANSACTION_STATUS_TOKEN_MAX_AGE_SECONDS", 7 * 24 * 3600))
    except Exception:
        value = 7 * 24 * 3600
    # Clamp (min 5 minutes, max 30 days)
    return max(300, min(value, 30 * 24 * 3600))


def generate_transaction_status_token(order_id: str) -> str:
    order_id_clean = str(order_id or "").strip()
    if not order_id_clean:
        raise ValueError("order_id kosong")
    s = _get_serializer()
    payload = {"v": 1, "order_id": order_id_clean}
    return str(s.dumps(payload))


def verify_transaction_status_token(token: str, *, expected_order_id: str) -> bool:
    raw_token = str(token or "").strip()
    if not raw_token:
        return False

    expected = str(expected_order_id or "").strip()
    if not expected:
        return False

    s = _get_serializer()
    try:
        max_age = get_transaction_status_token_max_age_seconds()
        payload = s.loads(raw_token, max_age=max_age)
        if not isinstance(payload, dict):
            return False
        if str(payload.get("order_id") or "").strip() != expected:
            return False
        return True
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        return False
