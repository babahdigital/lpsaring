from __future__ import annotations

import uuid

from flask import Flask

from app.infrastructure.http.decorators import (
    _audit_key_is_sensitive,
    _audit_sanitize,
    _extract_target_user_id,
)


def test_audit_key_sensitive_exact_match() -> None:
    assert _audit_key_is_sensitive("password") is True
    assert _audit_key_is_sensitive("OTP") is True
    assert _audit_key_is_sensitive("signature_key") is True


def test_audit_key_sensitive_substring_settings_keys() -> None:
    # M7: settings keys yang sebelumnya tidak ter-redact harus tertangkap.
    assert _audit_key_is_sensitive("WHATSAPP_API_KEY") is True
    assert _audit_key_is_sensitive("TELEGRAM_BOT_TOKEN") is True
    assert _audit_key_is_sensitive("MIDTRANS_SERVER_KEY") is True
    assert _audit_key_is_sensitive("MIKROTIK_PASSWORD") is True
    assert _audit_key_is_sensitive("TELEGRAM_WEBHOOK_SECRET") is True
    assert _audit_key_is_sensitive("MIDTRANS_CLIENT_KEY") is True
    assert _audit_key_is_sensitive("ENCRYPTION_KEY") is True


def test_audit_key_not_sensitive_safe_keys() -> None:
    assert _audit_key_is_sensitive("phone_number") is False
    assert _audit_key_is_sensitive("user_id") is False
    assert _audit_key_is_sensitive("FRONTEND_URL") is False
    assert _audit_key_is_sensitive("") is False


def test_audit_sanitize_redacts_sensitive_in_nested_dict() -> None:
    payload = {
        "settings": {
            "WHATSAPP_API_KEY": "abc123secret",
            "FRONTEND_URL": "https://app.example.com",
            "TELEGRAM_BOT_TOKEN": "999:xyz",
        }
    }
    result = _audit_sanitize(payload)
    assert isinstance(result, dict)
    inner = result["settings"]
    assert inner["WHATSAPP_API_KEY"] == "(redacted)"
    assert inner["TELEGRAM_BOT_TOKEN"] == "(redacted)"
    assert inner["FRONTEND_URL"] == "https://app.example.com"


def test_audit_sanitize_truncates_long_strings() -> None:
    long_value = "x" * 800
    result = _audit_sanitize({"note": long_value})
    assert isinstance(result, dict)
    assert isinstance(result["note"], str)
    assert len(result["note"]) <= 501  # 500 + "…"
    assert result["note"].endswith("…")


def test_extract_target_user_id_from_view_args() -> None:
    app = Flask(__name__)
    valid = str(uuid.uuid4())
    with app.test_request_context("/api/admin/users/x"):
        from flask import request

        request.view_args = {"user_id": valid}
        assert _extract_target_user_id() == valid


def test_extract_target_user_id_invalid_uuid_returns_none() -> None:
    app = Flask(__name__)
    with app.test_request_context("/api/admin/users/notauuid"):
        from flask import request

        request.view_args = {"user_id": "notauuid"}
        assert _extract_target_user_id() is None


def test_extract_target_user_id_from_query_string() -> None:
    app = Flask(__name__)
    valid = str(uuid.uuid4())
    with app.test_request_context(f"/api/admin/x?target_user_id={valid}"):
        assert _extract_target_user_id() == valid


def test_extract_target_user_id_from_json_payload_fallback() -> None:
    app = Flask(__name__)
    valid = str(uuid.uuid4())
    with app.test_request_context("/api/admin/x", method="POST"):
        # Tidak ada di view_args atau query — pakai payload.
        payload = {"user_id": valid}
        assert _extract_target_user_id(payload) == valid


def test_extract_target_user_id_priority_view_args_over_payload() -> None:
    app = Flask(__name__)
    view_uuid = str(uuid.uuid4())
    payload_uuid = str(uuid.uuid4())
    assert view_uuid != payload_uuid
    with app.test_request_context("/api/admin/users/x"):
        from flask import request

        request.view_args = {"user_id": view_uuid}
        # Payload UUID berbeda — view_args harus menang.
        assert _extract_target_user_id({"user_id": payload_uuid}) == view_uuid
