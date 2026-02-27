from __future__ import annotations

import hashlib
import secrets
import uuid
from http import HTTPStatus
from typing import Any, Optional, cast

import itsdangerous
from flask import current_app, jsonify, request
from pydantic import ValidationError

from app.services import settings_service
from app.utils.access_status import STATUS_PAGE_ALLOWED
from app.utils.auth_cookie_utils import (
    clear_access_cookie,
    clear_refresh_cookie,
    set_access_cookie,
    set_refresh_cookie,
)
from app.utils.formatters import get_phone_number_variations, normalize_to_e164
from app.utils.request_utils import get_client_ip


def set_auth_cookie_helper(response, token: str) -> None:
    set_access_cookie(response, token)


def clear_auth_cookie_helper(response) -> None:
    clear_access_cookie(response)


def set_refresh_cookie_helper(response, token: str) -> None:
    set_refresh_cookie(response, token)


def clear_refresh_cookie_helper(response) -> None:
    clear_refresh_cookie(response)


def extract_phone_from_request() -> Optional[str]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload.get("phone_number")
    if request.form:
        return request.form.get("phone_number")
    return None


def is_demo_mode_enabled() -> bool:
    return settings_service.get_setting_as_bool(
        "DEMO_MODE_ENABLED",
        bool(current_app.config.get("DEMO_MODE_ENABLED", False)),
    )


def is_demo_phone_whitelisted(phone_e164: str) -> bool:
    allowed_raw = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(allowed_raw, list) or len(allowed_raw) == 0:
        return False

    target_variants = set(get_phone_number_variations(phone_e164))

    for candidate in allowed_raw:
        if candidate is None:
            continue

        raw_phone = str(candidate).strip()
        if raw_phone == "":
            continue

        try:
            normalized_candidate = normalize_to_e164(raw_phone)
        except ValueError:
            continue

        candidate_variants = set(get_phone_number_variations(normalized_candidate))
        if target_variants.intersection(candidate_variants):
            return True

    return False


def is_demo_phone_allowed(phone_e164: str) -> bool:
    if not is_demo_mode_enabled():
        return False
    return is_demo_phone_whitelisted(phone_e164)


def safe_normalize_phone_for_key(phone_number: str) -> str:
    try:
        return normalize_to_e164(phone_number)
    except Exception:
        digits_only = "".join(ch for ch in str(phone_number) if ch.isdigit())
        if digits_only:
            return digits_only[:24]
        return "invalid-phone"


def rate_limit_key_with_phone() -> str:
    client_ip = get_client_ip() or ""
    phone_number = extract_phone_from_request()
    if phone_number:
        normalized = safe_normalize_phone_for_key(str(phone_number))
        return f"{client_ip}:{normalized}"
    return client_ip


def rate_limit_key_with_ip() -> str:
    client_ip = get_client_ip() or ""
    return client_ip


def get_otp_fingerprint() -> str:
    if not current_app.config.get("OTP_FINGERPRINT_ENABLED", True):
        return ""
    client_ip = get_client_ip() or ""
    user_agent = request.headers.get("User-Agent") or ""
    raw = f"{client_ip}|{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_redis_client_otp() -> Any:
    return getattr(cast(Any, current_app), "redis_client_otp", None)


def validation_error_details(error: ValidationError) -> list[dict[str, Any]]:
    return [dict(item) for item in error.errors()]


def is_otp_cooldown_active(phone_number: str) -> bool:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return False
    try:
        return redis_client.get(f"otp:cooldown:{phone_number}") is not None
    except Exception:
        return False


def get_status_token_serializer() -> itsdangerous.URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("SECRET_KEY tidak disetel untuk status token.")
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt="status-page-access")


def generate_status_token(status: str) -> Optional[str]:
    if status not in STATUS_PAGE_ALLOWED:
        return None
    try:
        serializer = get_status_token_serializer()
        payload = {
            "status": status,
            "nonce": secrets.token_urlsafe(8),
        }
        return serializer.dumps(payload)
    except Exception as e:
        current_app.logger.warning(f"Gagal membuat status token: {e}")
        return None


def verify_status_token_value(token: str, expected_status: str) -> bool:
    if expected_status not in STATUS_PAGE_ALLOWED:
        return False
    try:
        serializer = get_status_token_serializer()
        max_age = int(current_app.config.get("STATUS_PAGE_TOKEN_MAX_AGE_SECONDS", 300))
        payload = serializer.loads(token, max_age=max_age)
        return isinstance(payload, dict) and payload.get("status") == expected_status
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        return False
    except Exception as e:
        current_app.logger.warning(f"Gagal verifikasi status token: {e}")
        return False


def build_status_error_payload(status: str, message: str, build_error_payload):
    token = generate_status_token(status)
    payload = build_error_payload(
        message,
        status_code=HTTPStatus.FORBIDDEN,
        code="STATUS_TOKEN_INVALID",
        extra={"status": status, "status_token": token},
    )
    return jsonify(payload)


def set_otp_cooldown(phone_number: str) -> None:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return
    try:
        cooldown = int(current_app.config.get("OTP_REQUEST_COOLDOWN_SECONDS", 60))
        redis_client.setex(f"otp:cooldown:{phone_number}", cooldown, "1")
    except Exception:
        return


def get_otp_fail_key(phone_number: str) -> str:
    fingerprint = get_otp_fingerprint()
    if fingerprint:
        return f"otp:fail:{phone_number}:{fingerprint}"
    return f"otp:fail:{phone_number}"


def get_otp_fail_count(phone_number: str) -> int:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return 0
    try:
        raw = redis_client.get(get_otp_fail_key(phone_number))
        return int(raw) if raw else 0
    except Exception:
        return 0


def increment_otp_fail_count(phone_number: str) -> None:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return
    try:
        key = get_otp_fail_key(phone_number)
        window_seconds = int(current_app.config.get("OTP_VERIFY_WINDOW_SECONDS", 300))
        redis_client.incr(key)
        redis_client.expire(key, window_seconds)
    except Exception:
        return


def clear_otp_fail_count(phone_number: str) -> None:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return
    try:
        redis_client.delete(get_otp_fail_key(phone_number))
    except Exception:
        return


def generate_otp_code(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def store_otp_in_redis(phone_number: str, otp: str) -> bool:
    try:
        key = f"otp:{phone_number}"
        expire_seconds = current_app.config.get("OTP_EXPIRE_SECONDS", 300)
        redis_client = get_redis_client_otp()
        if redis_client is None:
            current_app.logger.error("Redis client for OTP is not initialized.")
            return False
        redis_client.setex(key, expire_seconds, otp)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to store OTP in Redis for {phone_number}: {e}", exc_info=True)
        return False


def verify_otp_from_redis(phone_number: str, otp_code: str) -> bool:
    try:
        key = f"otp:{phone_number}"
        redis_client = get_redis_client_otp()
        if redis_client is None:
            current_app.logger.error("Redis client for OTP is not initialized.")
            return False
        stored_otp = redis_client.get(key)

        if stored_otp is not None and stored_otp == otp_code:
            redis_client.delete(key)
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve OTP from Redis for {phone_number}: {e}", exc_info=True)
        return False


def store_session_token(user_id: uuid.UUID) -> Optional[str]:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        current_app.logger.warning("Redis tidak tersedia untuk session token.")
        return None
    token = secrets.token_urlsafe(32)
    key = f"session:{token}"
    expire_seconds = current_app.config.get("SESSION_TOKEN_EXPIRE_SECONDS", 120)
    try:
        redis_client.setex(key, expire_seconds, str(user_id))
        return token
    except Exception as e:
        current_app.logger.error(f"Gagal menyimpan session token: {e}", exc_info=True)
        return None


def consume_session_token_value(token: str) -> Optional[uuid.UUID]:
    redis_client = get_redis_client_otp()
    if redis_client is None:
        return None
    key = f"session:{token}"
    try:
        user_id_str = redis_client.get(key)
        if not user_id_str:
            return None
        redis_client.delete(key)
        return uuid.UUID(user_id_str)
    except Exception as e:
        current_app.logger.error(f"Gagal mengkonsumsi session token: {e}", exc_info=True)
        return None
