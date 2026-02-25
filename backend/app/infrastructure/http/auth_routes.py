# backend/app/infrastructure/http/auth_routes.py
import secrets
import hashlib
import itsdangerous
from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from http import HTTPStatus
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
import uuid
from werkzeug.security import check_password_hash, generate_password_hash
from typing import Any, Optional, cast

from .decorators import token_required, admin_required
from app.utils.request_utils import get_client_ip
from .schemas.auth_schemas import (
    RequestOtpRequestSchema,
    VerifyOtpRequestSchema,
    RequestOtpResponseSchema,
    VerifyOtpResponseSchema,
    AuthErrorResponseSchema,
    UserRegisterRequestSchema,
    UserRegisterResponseSchema,
    ChangePasswordRequestSchema,
    SessionTokenRequestSchema,
    StatusTokenVerifyRequestSchema,
)
from app.infrastructure.http.schemas.user_schemas import UserMeResponseSchema, UserProfileUpdateRequestSchema
from app.services.telegram_link_service import generate_user_link_token
from app.services import settings_service
from app.extensions import db, limiter
from app.infrastructure.db.models import (
    User,
    UserRole,
    ApprovalStatus,
    UserLoginHistory,
    UserDevice,
    NotificationRecipient,
    NotificationType,
)
from app.infrastructure.gateways.whatsapp_client import send_otp_whatsapp
from user_agents import parse as parse_user_agent
from app.services.notification_service import get_notification_message
from app.utils.formatters import (
    format_datetime_to_wita,
    format_to_local_phone,
    get_phone_number_variations,
    normalize_to_e164,
)

from app.services.jwt_token_service import create_access_token
from app.services.refresh_token_service import (
    issue_refresh_token_for_user,
    rotate_refresh_token,
    revoke_refresh_token,
)
from app.utils.auth_cookie_utils import (
    set_access_cookie,
    clear_access_cookie,
    set_refresh_cookie,
    clear_refresh_cookie,
)

from app.services.user_management.helpers import _generate_password, _handle_mikrotik_operation
from app.services.user_management.user_profile import _get_active_registration_bonus
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    get_mikrotik_connection,
    get_hotspot_active_session_by_ip,
)
from app.services.device_management_service import (
    apply_device_binding_for_login,
    resolve_binding_context,
    resolve_client_mac,
    normalize_mac,
)
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.services.access_policy_service import is_hotspot_login_required
from app.utils.metrics_utils import increment_metric

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message

    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False

    def send_whatsapp_message(recipient_number: str, message_body: str) -> bool:
        current_app.logger.warning("WhatsApp client not available. Dummy send_whatsapp_message called.")
        return False


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# --- Helper functions ---


def _set_auth_cookie(response, token: str) -> None:
    set_access_cookie(response, token)


def _clear_auth_cookie(response) -> None:
    clear_access_cookie(response)


def _set_refresh_cookie(response, token: str) -> None:
    set_refresh_cookie(response, token)


def _clear_refresh_cookie(response) -> None:
    clear_refresh_cookie(response)


def _extract_phone_from_request() -> Optional[str]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload.get("phone_number")
    if request.form:
        return request.form.get("phone_number")


def _is_demo_phone_allowed(phone_e164: str) -> bool:
    if not current_app.config.get("DEMO_MODE_ENABLED", False):
        return False

    if current_app.config.get("DEMO_ALLOW_ANY_PHONE", False):
        return True

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


def _safe_normalize_phone_for_key(phone_number: str) -> str:
    """Best-effort phone normalization for rate-limit keys.

    Must never raise (limiter key_func cannot error).
    """
    try:
        return normalize_to_e164(phone_number)
    except Exception:
        # fallback: digits-only if possible (avoid bypass via spaces/dashes)
        digits_only = "".join(ch for ch in str(phone_number) if ch.isdigit())
        if digits_only:
            return digits_only[:24]
        # keep key stable but short
        return "invalid-phone"


def _rate_limit_key_with_phone() -> str:
    client_ip = get_client_ip() or ""
    phone_number = _extract_phone_from_request()
    if phone_number:
        normalized = _safe_normalize_phone_for_key(str(phone_number))
        return f"{client_ip}:{normalized}"
    return client_ip


def _rate_limit_key_with_ip() -> str:
    client_ip = get_client_ip() or ""
    return client_ip


def _get_otp_fingerprint() -> str:
    if not current_app.config.get("OTP_FINGERPRINT_ENABLED", True):
        return ""
    client_ip = get_client_ip() or ""
    user_agent = request.headers.get("User-Agent") or ""
    raw = f"{client_ip}|{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_redis_client_otp() -> Any:
    return getattr(cast(Any, current_app), "redis_client_otp", None)


def _validation_error_details(error: ValidationError) -> list[dict[str, Any]]:
    return [dict(item) for item in error.errors()]


def _is_otp_cooldown_active(phone_number: str) -> bool:
    redis_client = _get_redis_client_otp()
    if redis_client is None:
        return False
    try:
        return redis_client.get(f"otp:cooldown:{phone_number}") is not None
    except Exception:
        return False


# --- Status page token helpers ---

_STATUS_TOKEN_ALLOWED = {"blocked", "inactive", "expired", "habis", "fup"}


def _get_status_token_serializer() -> itsdangerous.URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("SECRET_KEY tidak disetel untuk status token.")
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt="status-page-access")


def _generate_status_token(status: str) -> Optional[str]:
    if status not in _STATUS_TOKEN_ALLOWED:
        return None
    try:
        serializer = _get_status_token_serializer()
        payload = {
            "status": status,
            "nonce": secrets.token_urlsafe(8),
        }
        return serializer.dumps(payload)
    except Exception as e:
        current_app.logger.warning(f"Gagal membuat status token: {e}")
        return None


def _verify_status_token(token: str, expected_status: str) -> bool:
    if expected_status not in _STATUS_TOKEN_ALLOWED:
        return False
    try:
        serializer = _get_status_token_serializer()
        max_age = int(current_app.config.get("STATUS_PAGE_TOKEN_MAX_AGE_SECONDS", 300))
        payload = serializer.loads(token, max_age=max_age)
        return isinstance(payload, dict) and payload.get("status") == expected_status
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        return False
    except Exception as e:
        current_app.logger.warning(f"Gagal verifikasi status token: {e}")
        return False


def _build_status_error(status: str, message: str):
    token = _generate_status_token(status)
    return jsonify(AuthErrorResponseSchema(error=message, status=status, status_token=token).model_dump())


def _set_otp_cooldown(phone_number: str) -> None:
    redis_client = _get_redis_client_otp()
    if redis_client is None:
        return
    try:
        cooldown = int(current_app.config.get("OTP_REQUEST_COOLDOWN_SECONDS", 60))
        redis_client.setex(f"otp:cooldown:{phone_number}", cooldown, "1")
    except Exception:
        return


def _get_otp_fail_key(phone_number: str) -> str:
    fingerprint = _get_otp_fingerprint()
    if fingerprint:
        return f"otp:fail:{phone_number}:{fingerprint}"
    return f"otp:fail:{phone_number}"


def _get_otp_fail_count(phone_number: str) -> int:
    redis_client = _get_redis_client_otp()
    if redis_client is None:
        return 0
    try:
        raw = redis_client.get(_get_otp_fail_key(phone_number))
        return int(raw) if raw else 0
    except Exception:
        return 0


def _increment_otp_fail_count(phone_number: str) -> None:
    redis_client = _get_redis_client_otp()
    if redis_client is None:
        return
    try:
        key = _get_otp_fail_key(phone_number)
        window_seconds = int(current_app.config.get("OTP_VERIFY_WINDOW_SECONDS", 300))
        redis_client.incr(key)
        redis_client.expire(key, window_seconds)
    except Exception:
        return


def _clear_otp_fail_count(phone_number: str) -> None:
    redis_client = _get_redis_client_otp()
    if redis_client is None:
        return
    try:
        redis_client.delete(_get_otp_fail_key(phone_number))
    except Exception:
        return


def generate_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def store_otp_in_redis(phone_number: str, otp: str) -> bool:
    try:
        key = f"otp:{phone_number}"
        expire_seconds = current_app.config.get("OTP_EXPIRE_SECONDS", 300)
        redis_client = _get_redis_client_otp()
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
        redis_client = _get_redis_client_otp()
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


## create_access_token dipindahkan ke app.services.jwt_token_service


def _store_session_token(user_id: uuid.UUID) -> Optional[str]:
    redis_client = _get_redis_client_otp()
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


def _consume_session_token(token: str) -> Optional[uuid.UUID]:
    redis_client = _get_redis_client_otp()
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


# --- Routes ---


@auth_bp.route("/register", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("REGISTER_RATE_LIMIT", "5 per minute;20 per hour"), key_func=_rate_limit_key_with_ip
)
def register_user():
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        try:
            normalized_phone_number = normalize_to_e164(data_input.phone_number)
        except ValueError as e:
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        phone_variations = get_phone_number_variations(normalized_phone_number)
        if db.session.execute(select(User.id).where(User.phone_number.in_(phone_variations))).scalar_one_or_none():
            return jsonify(
                AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()
            ), HTTPStatus.CONFLICT

        ua_string = request.headers.get("User-Agent")
        device_brand, device_model, raw_ua = None, None, None
        if ua_string:
            raw_ua = ua_string[:1024]
            ua_info = parse_user_agent(ua_string)
            device_brand = getattr(ua_info.device, "brand", None)
            device_model = getattr(ua_info.device, "model", None)

        new_user_obj = cast(Any, User)(
            phone_number=normalized_phone_number,
            full_name=data_input.full_name,
            approval_status=ApprovalStatus.PENDING_APPROVAL,
            is_active=False,
            is_tamping=data_input.is_tamping,
            tamping_type=data_input.tamping_type,
            device_brand=device_brand,
            device_model=device_model,
            raw_user_agent=raw_ua,
            is_unlimited_user=False,
        )

        default_user_server = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_USER", "srv-user")
        default_komandan_server = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_KOMANDAN", "srv-komandan")

        if data_input.register_as_komandan:
            new_user_obj.role = UserRole.KOMANDAN
            new_user_obj.mikrotik_server_name = default_komandan_server
        else:
            new_user_obj.role = UserRole.USER
            new_user_obj.mikrotik_server_name = default_user_server
            if data_input.is_tamping:
                new_user_obj.blok = None
                new_user_obj.kamar = None
            else:
                new_user_obj.blok = data_input.blok
                new_user_obj.kamar = data_input.kamar

        inactive_profile = settings_service.get_setting(
            "MIKROTIK_INACTIVE_PROFILE", None
        ) or settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
        new_user_obj.mikrotik_profile_name = inactive_profile

        active_bonus = _get_active_registration_bonus()
        if active_bonus and active_bonus.bonus_value_mb and active_bonus.bonus_duration_days:
            current_app.logger.info(
                f"Menerapkan bonus registrasi '{active_bonus.name}' untuk pendaftar baru {new_user_obj.full_name}"
            )
            new_user_obj.total_quota_purchased_mb = active_bonus.bonus_value_mb
            new_user_obj.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(
                days=active_bonus.bonus_duration_days
            )
        else:
            new_user_obj.total_quota_purchased_mb = 0
            new_user_obj.quota_expiry_date = None

        db.session.add(new_user_obj)
        db.session.commit()
        db.session.refresh(new_user_obj)

        try:
            if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
                user_context = {"full_name": new_user_obj.full_name}
                user_message = get_notification_message("user_self_register_pending", user_context)
                send_whatsapp_message(new_user_obj.phone_number, user_message)

                recipients_query = (
                    select(User)
                    .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
                    .where(
                        NotificationRecipient.notification_type == NotificationType.NEW_USER_REGISTRATION,
                        User.is_active,
                    )
                )
                recipients = db.session.scalars(recipients_query).all()
                if recipients:
                    admin_context = {
                        "full_name": new_user_obj.full_name,
                        "phone_number": new_user_obj.phone_number,
                        "blok": new_user_obj.blok if new_user_obj.blok else "N/A",
                        "kamar": new_user_obj.kamar if new_user_obj.kamar else "N/A",
                        "role": new_user_obj.role.value,
                    }
                    admin_message = get_notification_message("new_user_registration_to_admin", admin_context)
                    for admin in recipients:
                        send_whatsapp_message(admin.phone_number, admin_message)
        except Exception as e_notify:
            current_app.logger.error(f"Failed to send new user registration notifications: {e_notify}", exc_info=True)

        return jsonify(
            UserRegisterResponseSchema(
                message="Registration successful. Your account is awaiting Admin approval.",
                user_id=new_user_obj.id,
                phone_number=new_user_obj.phone_number,
            ).model_dump()
        ), HTTPStatus.CREATED
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()
        ), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /register: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred during registration.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/request-otp", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("OTP_REQUEST_RATE_LIMIT", "5 per minute;20 per hour"),
    key_func=_rate_limit_key_with_phone,
)
def request_otp():
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict() if request.form else None
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST
        data = RequestOtpRequestSchema.model_validate(payload)

        try:
            phone_e164 = normalize_to_e164(data.phone_number)
        except ValueError as e:
            increment_metric("otp.request.failed")
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        if _is_otp_cooldown_active(phone_e164):
            return jsonify(
                AuthErrorResponseSchema(
                    error="Terlalu sering meminta OTP. Silakan coba beberapa saat lagi."
                ).model_dump()
            ), HTTPStatus.TOO_MANY_REQUESTS

        demo_phone_allowed = _is_demo_phone_allowed(phone_e164)
        phone_variations = get_phone_number_variations(phone_e164)
        user_for_otp = db.session.execute(
            select(User).where(User.phone_number.in_(phone_variations))
        ).scalar_one_or_none()
        if not user_for_otp:
            if demo_phone_allowed:
                _set_otp_cooldown(phone_e164)
                increment_metric("otp.request.success")
                current_app.logger.warning("OTP request demo accepted for non-registered phone: %s", phone_e164)
                return jsonify(
                    RequestOtpResponseSchema(message="Kode OTP berhasil diproses. Silakan lanjut verifikasi.").model_dump()
                ), HTTPStatus.OK

            increment_metric("otp.request.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Phone number is not registered.").model_dump()
            ), HTTPStatus.NOT_FOUND
        if not user_for_otp.is_active or user_for_otp.approval_status != ApprovalStatus.APPROVED:
            increment_metric("otp.request.failed")
            return _build_status_error(
                "inactive", "Login failed. Your account is not active or approved yet."
            ), HTTPStatus.FORBIDDEN

        otp_generated = generate_otp()
        if not store_otp_in_redis(phone_e164, otp_generated):
            if current_app.config.get("OTP_ALLOW_BYPASS", False):
                current_app.logger.warning("Redis OTP unavailable; bypass mode enabled.")
            else:
                increment_metric("otp.request.failed")
                return jsonify(
                    AuthErrorResponseSchema(error="Failed to process OTP request.").model_dump()
                ), HTTPStatus.INTERNAL_SERVER_ERROR

        send_otp_whatsapp(phone_e164, otp_generated)

        _set_otp_cooldown(phone_e164)
        increment_metric("otp.request.success")

        return jsonify(RequestOtpResponseSchema().model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /request-otp: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/verify-otp", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("OTP_VERIFY_RATE_LIMIT", "10 per minute;60 per hour"),
    key_func=_rate_limit_key_with_phone,
)
def verify_otp():
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict() if request.form else None
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        # Normalisasi key client identity (captive portal/MikroTik sering memakai variasi key).
        payload_dict: dict[str, Any] = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
        if payload_dict:
            if not payload_dict.get("client_ip"):
                candidate_ip = (
                    payload_dict.get("clientIp")
                    or payload_dict.get("ip")
                    or payload_dict.get("client-ip")
                    or request.args.get("client_ip")
                    or request.args.get("ip")
                    or request.args.get("client-ip")
                )
                if candidate_ip is not None:
                    payload_dict["client_ip"] = candidate_ip
            if not payload_dict.get("client_mac"):
                candidate_mac = (
                    payload_dict.get("clientMac")
                    or payload_dict.get("mac")
                    or payload_dict.get("mac-address")
                    or payload_dict.get("client-mac")
                    or request.args.get("client_mac")
                    or request.args.get("mac")
                    or request.args.get("mac-address")
                    or request.args.get("client-mac")
                )
                if candidate_mac is not None:
                    payload_dict["client_mac"] = candidate_mac
            if payload_dict.get("hotspot_login_context") is None:
                candidate_ctx = (
                    payload_dict.get("hotspotLoginContext")
                    or request.args.get("hotspot_login_context")
                    or request.args.get("hotspotLoginContext")
                )
                if candidate_ctx is not None:
                    payload_dict["hotspot_login_context"] = candidate_ctx

        data = VerifyOtpRequestSchema.model_validate(payload_dict)

        try:
            phone_e164 = normalize_to_e164(data.phone_number)
        except ValueError as e:
            increment_metric("otp.verify.failed")
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        fail_count = _get_otp_fail_count(phone_e164)
        max_attempts = int(current_app.config.get("OTP_VERIFY_MAX_ATTEMPTS", 5))
        if fail_count >= max_attempts:
            increment_metric("otp.verify.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Terlalu banyak percobaan OTP. Silakan coba lagi nanti.").model_dump()
            ), HTTPStatus.TOO_MANY_REQUESTS
        otp_bypass_code = str(current_app.config.get("OTP_BYPASS_CODE", "000000") or "000000")
        bypass_allowed = current_app.config.get("OTP_ALLOW_BYPASS", False)
        demo_bypass_code = str(current_app.config.get("DEMO_BYPASS_OTP_CODE", "000000") or "000000")
        demo_bypass_allowed = _is_demo_phone_allowed(phone_e164)
        used_bypass_code = False
        used_demo_bypass = False

        otp_ok = verify_otp_from_redis(phone_e164, data.otp)
        if not otp_ok:
            if bypass_allowed and data.otp == otp_bypass_code:
                current_app.logger.warning("OTP bypass global digunakan untuk login.")
                otp_ok = True
                used_bypass_code = True
            elif demo_bypass_allowed and data.otp == demo_bypass_code:
                current_app.logger.warning("OTP bypass demo digunakan untuk nomor whitelist demo.")
                otp_ok = True
                used_bypass_code = True
                used_demo_bypass = True

        if not otp_ok:
            _increment_otp_fail_count(phone_e164)
            increment_metric("otp.verify.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Invalid or expired OTP code.").model_dump()
            ), HTTPStatus.UNAUTHORIZED

        _clear_otp_fail_count(phone_e164)
        increment_metric("otp.verify.success")

        phone_variations = get_phone_number_variations(phone_e164)
        user_to_login = db.session.execute(
            select(User).where(User.phone_number.in_(phone_variations))
        ).scalar_one_or_none()

        if user_to_login is None and used_demo_bypass and current_app.config.get("DEMO_MODE_ENABLED", False):
            now_utc = datetime.now(dt_timezone.utc)
            local_phone = format_to_local_phone(phone_e164)
            fallback_name = f"Demo User {local_phone[-4:]}" if local_phone and len(local_phone) >= 4 else "Demo User"

            demo_user = User()
            demo_user.phone_number = phone_e164
            demo_user.full_name = fallback_name
            demo_user.password_hash = generate_password_hash(secrets.token_urlsafe(12))
            demo_user.role = UserRole.USER
            demo_user.approval_status = ApprovalStatus.APPROVED
            demo_user.is_active = True
            demo_user.approved_at = now_utc
            demo_user.approved_by_id = None
            demo_user.last_login_at = now_utc
            demo_user.mikrotik_user_exists = False

            db.session.add(demo_user)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                user_to_login = db.session.execute(
                    select(User).where(User.phone_number.in_(phone_variations))
                ).scalar_one_or_none()
            else:
                user_to_login = demo_user
                current_app.logger.warning(
                    "Demo user auto-provisioned via demo bypass: phone=%s user_id=%s",
                    phone_e164,
                    str(demo_user.id),
                )

        if not user_to_login:
            return jsonify(
                AuthErrorResponseSchema(error="User not found after OTP verification.").model_dump()
            ), HTTPStatus.INTERNAL_SERVER_ERROR
        if not user_to_login.is_active or user_to_login.approval_status != ApprovalStatus.APPROVED:
            return _build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
        if getattr(user_to_login, "is_blocked", False):
            return _build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        client_ip = data.client_ip or get_client_ip()
        client_mac = data.client_mac
        user_agent = request.headers.get("User-Agent")

        login_ip_for_history = client_ip

        binding_context = resolve_binding_context(user_to_login, client_ip, client_mac)
        if current_app.config.get("LOG_BINDING_DEBUG", False) or not client_ip:
            current_app.logger.info(
                "Verify-OTP binding context: "
                "input_ip=%s input_mac=%s resolved_ip=%s ip_source=%s ip_msg=%s "
                "resolved_mac=%s mac_source=%s mac_msg=%s",
                binding_context.get("input_ip"),
                binding_context.get("input_mac"),
                binding_context.get("resolved_ip"),
                binding_context.get("ip_source"),
                binding_context.get("ip_message"),
                binding_context.get("resolved_mac"),
                binding_context.get("mac_source"),
                binding_context.get("mac_message"),
            )

        if user_to_login.role in [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # Policy default: OTP sukses = user sudah memverifikasi dirinya sendiri.
            # Jadi device/MAC yang sedang dipakai boleh langsung di-authorize (tidak masuk pending-auth).
            #
            # Catatan keamanan:
            # - Jika OTP bypass code dipakai, kita JANGAN auto-authorize device.
            # - Bisa dimatikan lewat config OTP_AUTO_AUTHORIZE_DEVICE=False.
            otp_auto_authorize = current_app.config.get("OTP_AUTO_AUTHORIZE_DEVICE", True)

            bypass_explicit = bool(otp_auto_authorize) and (not used_bypass_code)

            # Fallback ke perilaku lama (opsional) jika auto-authorize dimatikan atau OTP bypass dipakai.
            if not bypass_explicit:
                # Jika explicit device auth diaktifkan, best-practice lama:
                # - device pertama user boleh auto-authorize setelah OTP berhasil
                # - device berikutnya wajib explicit authorization (tidak bypass)
                bypass_explicit = True
                try:
                    require_explicit = settings_service.get_setting("REQUIRE_EXPLICIT_DEVICE_AUTH", "False") == "True"
                    if require_explicit and user_to_login.role in [UserRole.USER, UserRole.KOMANDAN]:
                        has_any_authorized_device = (
                            db.session.scalar(
                                select(UserDevice.id)
                                .where(
                                    UserDevice.user_id == user_to_login.id,
                                    UserDevice.is_authorized.is_(True),
                                )
                                .limit(1)
                            )
                            is not None
                        )
                        bypass_explicit = not has_any_authorized_device
                except Exception:
                    # Fail-safe: tetap gunakan perilaku lama (bypass) jika ada error query
                    bypass_explicit = True

            ok_binding, msg_binding, resolved_ip = apply_device_binding_for_login(
                user_to_login,
                client_ip,
                user_agent,
                client_mac,
                bypass_explicit_auth=bypass_explicit,
            )
            if not ok_binding:
                if msg_binding in ["Limit perangkat tercapai", "Perangkat belum diotorisasi"]:
                    current_app.logger.warning(
                        "Verify-OTP denied by device binding policy: user_id=%s phone=%s ip=%s mac=%s msg=%s",
                        user_to_login.id,
                        user_to_login.phone_number,
                        client_ip,
                        client_mac,
                        msg_binding,
                    )
                    return jsonify(AuthErrorResponseSchema(error=msg_binding).model_dump()), HTTPStatus.FORBIDDEN
                current_app.logger.warning(f"IP binding di-skip untuk user {user_to_login.id}: {msg_binding}")

            if current_app.config.get("SYNC_ADDRESS_LIST_ON_LOGIN", True):
                try:
                    sync_address_list_for_single_user(user_to_login, client_ip=resolved_ip)
                except Exception as e_sync:
                    current_app.logger.warning(f"Gagal sync address-list saat login: {e_sync}")

            # Simpan IP yang sudah di-resolve (prioritas IP lokal hotspot) untuk riwayat login.
            if resolved_ip:
                login_ip_for_history = resolved_ip
            else:
                # Jika IP yang terlihat hanya IP publik/proxy, lebih baik simpan None daripada data menyesatkan.
                try:
                    from app.services.device_management_service import _is_client_ip_allowed  # type: ignore

                    if not _is_client_ip_allowed(client_ip):
                        login_ip_for_history = None
                except Exception:
                    pass

        user_to_login.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = cast(Any, UserLoginHistory)(
            user_id=user_to_login.id, ip_address=login_ip_for_history, user_agent_string=user_agent
        )
        db.session.add(new_login_entry)

        db.session.commit()

        jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
        access_token = create_access_token(data=jwt_payload)

        refresh_token = issue_refresh_token_for_user(user_to_login.id, user_agent=user_agent)

        session_token = _store_session_token(user_to_login.id)
        session_url = None
        if session_token:
            base_url = (
                current_app.config.get("APP_PUBLIC_BASE_URL")
                or current_app.config.get("FRONTEND_URL")
                or current_app.config.get("APP_LINK_USER")
            )
            if base_url:
                next_path = "/dashboard"
                if data.hotspot_login_context is True:
                    next_path = "/captive/terhubung"
                session_url = f"{base_url.rstrip('/')}/session/consume?token={session_token}&next={next_path}"

        hotspot_username: Optional[str] = None
        hotspot_password: Optional[str] = None
        hotspot_login_required = is_hotspot_login_required(user_to_login)
        allow_hotspot_credentials = bool(data.client_ip or data.client_mac)
        if not allow_hotspot_credentials and data.hotspot_login_context is True:
            allow_hotspot_credentials = True
            current_app.logger.info(
                "Hotspot credentials allowed via captive context without client_ip/client_mac for user=%s",
                user_to_login.id,
            )
        if hotspot_login_required and allow_hotspot_credentials:
            hotspot_username = format_to_local_phone(user_to_login.phone_number)
            hotspot_password = user_to_login.mikrotik_password

        response = jsonify(
            VerifyOtpResponseSchema(
                access_token=access_token,
                hotspot_username=hotspot_username,
                hotspot_password=hotspot_password,
                session_token=session_token,
                session_url=session_url,
                hotspot_login_required=hotspot_login_required,
            ).model_dump()
        )
        _set_auth_cookie(response, access_token)
        _set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /verify-otp: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/auto-login", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("AUTO_LOGIN_RATE_LIMIT", "60 per minute"), key_func=_rate_limit_key_with_ip
)
def auto_login():
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict() if request.form else {}

        # Normalisasi key client identity (menerima variasi key dari captive portal).
        payload_dict: dict[str, Any] = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
        if payload_dict:
            if not payload_dict.get("client_ip"):
                candidate_ip = (
                    payload_dict.get("clientIp")
                    or payload_dict.get("ip")
                    or payload_dict.get("client-ip")
                    or request.args.get("client_ip")
                    or request.args.get("ip")
                    or request.args.get("client-ip")
                )
                if candidate_ip is not None:
                    payload_dict["client_ip"] = candidate_ip
            if not payload_dict.get("client_mac"):
                candidate_mac = (
                    payload_dict.get("clientMac")
                    or payload_dict.get("mac")
                    or payload_dict.get("mac-address")
                    or payload_dict.get("client-mac")
                    or request.args.get("client_mac")
                    or request.args.get("mac")
                    or request.args.get("mac-address")
                    or request.args.get("client-mac")
                )
                if candidate_mac is not None:
                    payload_dict["client_mac"] = candidate_mac

        client_ip = payload_dict.get("client_ip")
        client_mac = payload_dict.get("client_mac")
        if not client_ip:
            client_ip = get_client_ip()
        if not client_ip:
            return jsonify(
                AuthErrorResponseSchema(error="IP klien tidak ditemukan.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        login_ip_for_history = client_ip

        user_agent = request.headers.get("User-Agent")

        resolved_mac = None
        if client_mac:
            resolved_mac = normalize_mac(client_mac)
        else:
            ok, mac, msg = resolve_client_mac(client_ip)
            if ok and mac:
                resolved_mac = mac
            elif not ok:
                current_app.logger.warning(f"Auto-login: gagal resolve MAC untuk IP {client_ip}: {msg}")

        device_query = (
            db.session.query(UserDevice)
            .join(User)
            .filter(
                UserDevice.is_authorized.is_(True),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        )

        device = None
        if resolved_mac:
            device = device_query.filter(UserDevice.mac_address == resolved_mac).first()
        if not device:
            device = (
                device_query.filter(UserDevice.ip_address == client_ip).order_by(UserDevice.last_seen_at.desc()).first()
            )

        user = device.user if (device and getattr(device, "user", None)) else None

        # Fallback: device belum pernah terdaftar, tapi hotspot MikroTik sudah punya sesi aktif untuk IP ini.
        # Ini membuat sistem lebih fleksibel untuk kasus pergantian MAC (privacy/random) atau login via portal MikroTik.
        if user is None:
            hotspot_username: Optional[str] = None
            hotspot_mac: Optional[str] = None
            try:
                with get_mikrotik_connection() as api:
                    if api:
                        ok_sess, sess, _msg = get_hotspot_active_session_by_ip(api, str(client_ip))
                        if ok_sess and sess:
                            hotspot_username = str(sess.get("user") or "").strip() or None
                            if sess.get("mac-address"):
                                hotspot_mac = normalize_mac(str(sess.get("mac-address") or ""))
            except Exception:
                hotspot_username = None
                hotspot_mac = None

            if hotspot_username:
                try:
                    variations = get_phone_number_variations(hotspot_username)
                except Exception:
                    variations = []
                if variations:
                    user = db.session.execute(
                        select(User).where(
                            User.phone_number.in_(variations),
                            User.is_active.is_(True),
                            User.approval_status == ApprovalStatus.APPROVED,
                        )
                    ).scalar_one_or_none()

                    if user and hotspot_mac:
                        resolved_mac = hotspot_mac

        if not user:
            return jsonify(
                AuthErrorResponseSchema(error="Perangkat belum terdaftar atau belum diotorisasi.").model_dump()
            ), HTTPStatus.UNAUTHORIZED
        if getattr(user, "is_blocked", False):
            return _build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        if user.role in [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            ok_binding, msg_binding, resolved_ip = apply_device_binding_for_login(
                user,
                client_ip,
                user_agent,
                resolved_mac,
            )
            if not ok_binding:
                if msg_binding in ["Limit perangkat tercapai", "Perangkat belum diotorisasi"]:
                    return jsonify(AuthErrorResponseSchema(error=msg_binding).model_dump()), HTTPStatus.FORBIDDEN
                current_app.logger.warning(f"Auto-login: IP binding di-skip untuk user {user.id}: {msg_binding}")

            if current_app.config.get("SYNC_ADDRESS_LIST_ON_LOGIN", True):
                try:
                    sync_address_list_for_single_user(user, client_ip=resolved_ip)
                except Exception as e_sync:
                    current_app.logger.warning(f"Auto-login: gagal sync address-list: {e_sync}")

            if resolved_ip:
                login_ip_for_history = resolved_ip
            else:
                try:
                    from app.services.device_management_service import _is_client_ip_allowed  # type: ignore

                    if not _is_client_ip_allowed(client_ip):
                        login_ip_for_history = None
                except Exception:
                    pass

        user.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = cast(Any, UserLoginHistory)(
            user_id=user.id, ip_address=login_ip_for_history, user_agent_string=user_agent
        )
        db.session.add(new_login_entry)
        db.session.commit()

        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        access_token = create_access_token(data=jwt_payload)

        refresh_token = issue_refresh_token_for_user(user.id, user_agent=user_agent)

        hotspot_username: Optional[str] = None
        hotspot_password: Optional[str] = None
        hotspot_login_required = is_hotspot_login_required(user)

        response = jsonify(
            VerifyOtpResponseSchema(
                access_token=access_token,
                hotspot_username=hotspot_username,
                hotspot_password=hotspot_password,
                hotspot_login_required=hotspot_login_required,
            ).model_dump()
        )
        _set_auth_cookie(response, access_token)
        _set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /auto-login: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/session/consume", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("SESSION_CONSUME_RATE_LIMIT", "30 per minute"), key_func=_rate_limit_key_with_ip
)
def consume_session_token():
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict() if request.form else None
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        data = SessionTokenRequestSchema.model_validate(payload)
        user_id = _consume_session_token(data.token)
        if not user_id:
            return jsonify(
                AuthErrorResponseSchema(error="Session token tidak valid atau kedaluwarsa.").model_dump()
            ), HTTPStatus.UNAUTHORIZED

        user = db.session.get(User, user_id)
        if not user:
            return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
        if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            return _build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
        if getattr(user, "is_blocked", False):
            return _build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        access_token = create_access_token(data=jwt_payload)

        refresh_token = issue_refresh_token_for_user(user.id, user_agent=request.headers.get("User-Agent"))
        response = jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump())
        _set_auth_cookie(response, access_token)
        _set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /session/consume: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/status-token/verify", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("SESSION_CONSUME_RATE_LIMIT", "30 per minute"), key_func=_rate_limit_key_with_ip
)
def verify_status_token():
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict() if request.form else None
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        data = StatusTokenVerifyRequestSchema.model_validate(payload)
        is_valid = _verify_status_token(data.token, data.status)
        return jsonify({"valid": is_valid}), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /status-token/verify: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/debug/binding", methods=["POST"])
@admin_required
def debug_binding(current_admin=None):
    if current_app.config.get("FLASK_ENV") == "production":
        return jsonify(AuthErrorResponseSchema(error="Endpoint tidak tersedia.").model_dump()), HTTPStatus.NOT_FOUND

    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    if not payload or not isinstance(payload, dict):
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    user_id_raw = payload.get("user_id")
    phone_number = payload.get("phone_number")
    client_ip = payload.get("client_ip")
    client_mac = payload.get("client_mac")

    user = None
    if user_id_raw:
        try:
            user = db.session.get(User, uuid.UUID(str(user_id_raw)))
        except (ValueError, TypeError):
            return jsonify(AuthErrorResponseSchema(error="user_id tidak valid.").model_dump()), HTTPStatus.BAD_REQUEST
    elif phone_number:
        variations = get_phone_number_variations(str(phone_number))
        user = db.session.execute(select(User).where(User.phone_number.in_(variations))).scalar_one_or_none()
    else:
        return jsonify(
            AuthErrorResponseSchema(error="user_id atau phone_number wajib diisi.").model_dump()
        ), HTTPStatus.BAD_REQUEST

    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND

    context = resolve_binding_context(user, client_ip, client_mac)
    mac_only = (
        (not context.get("input_ip")) and bool(context.get("input_mac")) and context.get("ip_source") == "device_mac"
    )
    return jsonify(
        {
            "user_id": str(user.id),
            "phone_number": user.phone_number,
            "binding": context,
            "mac_only": mac_only,
        }
    ), HTTPStatus.OK


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not user.is_active:
        return _build_status_error("inactive", "User account is not active."), HTTPStatus.FORBIDDEN
    if getattr(user, "is_blocked", False):
        return _build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN
    try:
        payload = UserMeResponseSchema.model_validate(user).model_dump(mode="json")
        payload["is_demo_user"] = _is_demo_phone_allowed(str(user.phone_number or ""))
        response = jsonify(payload)
        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        refreshed_access_token = create_access_token(data=jwt_payload)
        _set_auth_cookie(response, refreshed_access_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        current_app.logger.error(f"[/me] Pydantic validation FAILED for user {user.id}: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(
                error="User data on server is invalid.", details=_validation_error_details(e)
            ).model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/me/telegram/status", methods=["GET"])
@token_required
def get_my_telegram_status(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    chat_id = getattr(user, "telegram_chat_id", None)
    username = getattr(user, "telegram_username", None)
    linked_at = getattr(user, "telegram_linked_at", None)

    return jsonify(
        {
            "linked": bool(chat_id),
            "chat_id": chat_id,
            "username": username,
            "linked_at": linked_at.isoformat() if linked_at else None,
        }
    ), HTTPStatus.OK


@auth_bp.route("/me/telegram/unlink", methods=["POST"])
@token_required
def unlink_my_telegram(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    user.telegram_chat_id = None
    user.telegram_username = None
    user.telegram_linked_at = None
    db.session.commit()
    return jsonify({"message": "Telegram berhasil diputus."}), HTTPStatus.OK


@auth_bp.route("/me/telegram/link-token", methods=["POST"])
@token_required
def create_my_telegram_link_token(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    bot_username = str(settings_service.get_setting("TELEGRAM_BOT_USERNAME", "") or "").strip().lstrip("@")
    if not bot_username:
        return jsonify(
            {
                "message": "TELEGRAM_BOT_USERNAME belum disetel oleh admin.",
            }
        ), HTTPStatus.BAD_REQUEST

    token = generate_user_link_token(user_id=str(user.id))
    link_url = f"https://t.me/{bot_username}?start={token}"
    max_age = int(current_app.config.get("TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS", 600))

    return jsonify(
        {
            "token": token,
            "link_url": link_url,
            "expires_in_seconds": max_age,
            "bot_username": bot_username,
        }
    ), HTTPStatus.OK


@auth_bp.route("/me/profile", methods=["PUT"])
@token_required
def update_user_profile(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return jsonify(
            AuthErrorResponseSchema(error="Your account is not active or approved to update profile.").model_dump()
        ), HTTPStatus.FORBIDDEN

    try:
        update_data = UserProfileUpdateRequestSchema.model_validate(request.get_json())
        user.full_name = update_data.full_name
        if user.role == UserRole.USER:
            user.blok = update_data.blok
            user.kamar = update_data.kamar
        db.session.commit()
        payload = UserMeResponseSchema.model_validate(user).model_dump(mode="json")
        payload["is_demo_user"] = _is_demo_phone_allowed(str(user.phone_number or ""))
        return jsonify(payload), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=_validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update user profile {user.id}: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An internal error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/users/me/reset-hotspot-password", methods=["POST"])
@token_required
def reset_hotspot_password(current_user_id: uuid.UUID):
    current_user = db.session.get(User, current_user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if current_user.is_admin_role:
        return jsonify({"message": "Access denied. This feature is not for admin roles."}), HTTPStatus.FORBIDDEN
    if not current_user.is_active or current_user.approval_status != ApprovalStatus.APPROVED:
        return jsonify(
            {"message": "Your account is not active or approved. Cannot reset password."}
        ), HTTPStatus.FORBIDDEN

    try:
        new_mikrotik_password = _generate_password(length=6, numeric_only=True)
        mikrotik_username = format_to_local_phone(current_user.phone_number)

        # [PERBAIKAN] Menggunakan helper terpusat untuk konsistensi
        mikrotik_success, mikrotik_message = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=mikrotik_username,
            hotspot_password=new_mikrotik_password,
            mikrotik_profile_name=current_user.mikrotik_profile_name,
            server=current_user.mikrotik_server_name,
            comment="Password reset by user via Portal",
        )

        if not mikrotik_success:
            return jsonify(
                {"success": False, "message": f"Gagal mereset password di Mikrotik. Error: {mikrotik_message}"}
            ), HTTPStatus.INTERNAL_SERVER_ERROR

        current_user.mikrotik_password = new_mikrotik_password
        db.session.commit()

        if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            context = {
                "full_name": current_user.full_name,
                "hotspot_username": mikrotik_username,
                "hotspot_password": new_mikrotik_password,
            }
            message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
            send_whatsapp_message(current_user.phone_number, message_body)

        return jsonify(
            {"success": True, "message": "Password hotspot baru berhasil dibuat dan dikirim via WhatsApp."}
        ), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Internal error while resetting hotspot password for user {current_user.id}: {e}", exc_info=True
        )
        return jsonify({"success": False, "message": "An internal error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/admin/login", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("ADMIN_LOGIN_RATE_LIMIT", "10 per minute;60 per hour"),
    key_func=_rate_limit_key_with_ip,
)
def admin_login():
    if not request.is_json:
        return jsonify({"message": "Request body must be JSON."}), HTTPStatus.BAD_REQUEST
    data = request.get_json()
    username_input = data.get("username")
    password = data.get("password")
    if isinstance(username_input, str):
        username_input = username_input.strip()
    if not username_input or not password:
        return jsonify({"message": "Username and password are required."}), HTTPStatus.BAD_REQUEST

    try:
        from app.infrastructure.http.schemas.auth_schemas import validate_phone_number

        normalized_phone = validate_phone_number(username_input)
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST

    phone_variations = get_phone_number_variations(normalized_phone)
    user_to_login = db.session.execute(
        db.select(User).filter(User.phone_number.in_(phone_variations))
    ).scalar_one_or_none()

    if (
        not user_to_login
        or not user_to_login.is_admin_role
        or not user_to_login.is_active
        or user_to_login.approval_status != ApprovalStatus.APPROVED
        or not user_to_login.password_hash
        or not check_password_hash(user_to_login.password_hash, password)
    ):
        increment_metric("admin.login.failed")
        return jsonify({"message": "Invalid username or password."}), HTTPStatus.UNAUTHORIZED

    user_to_login.last_login_at = datetime.now(dt_timezone.utc)
    new_login_entry = cast(Any, UserLoginHistory)(
        user_id=user_to_login.id, ip_address=get_client_ip(), user_agent_string=request.headers.get("User-Agent")
    )
    db.session.add(new_login_entry)
    db.session.commit()

    try:
        if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            context = {
                "phone_number": format_to_local_phone(user_to_login.phone_number),
                "login_time": format_datetime_to_wita(user_to_login.last_login_at),
            }
            message_body = get_notification_message("admin_login_notification", context)
            send_whatsapp_message(user_to_login.phone_number, message_body)
    except Exception as e_notify:
        current_app.logger.error(f"Gagal mengirim notifikasi login admin: {e_notify}", exc_info=True)

    jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
    access_token = create_access_token(data=jwt_payload)
    refresh_token = issue_refresh_token_for_user(user_to_login.id, user_agent=request.headers.get("User-Agent"))
    increment_metric("admin.login.success")
    response = jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump())
    _set_auth_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)
    return response, HTTPStatus.OK


@auth_bp.route("/refresh", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("REFRESH_TOKEN_RATE_LIMIT", "60 per minute"), key_func=_rate_limit_key_with_ip
)
def refresh_access_token():
    refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
    raw_refresh = request.cookies.get(refresh_cookie_name)
    if not raw_refresh:
        return jsonify(AuthErrorResponseSchema(error="Refresh token missing.").model_dump()), HTTPStatus.UNAUTHORIZED

    user_agent = request.headers.get("User-Agent")
    rotated = rotate_refresh_token(raw_refresh, user_agent=user_agent)
    if not rotated:
        return jsonify(
            AuthErrorResponseSchema(error="Refresh token invalid or expired.").model_dump()
        ), HTTPStatus.UNAUTHORIZED

    try:
        user_id = uuid.UUID(rotated.user_id)
    except Exception:
        return jsonify(AuthErrorResponseSchema(error="Refresh token invalid.").model_dump()), HTTPStatus.UNAUTHORIZED

    user = db.session.get(User, user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.UNAUTHORIZED
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return _build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
    if getattr(user, "is_blocked", False):
        return _build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

    jwt_payload = {"sub": str(user.id), "rl": user.role.value}
    access_token = create_access_token(data=jwt_payload)
    response = jsonify({"access_token": access_token, "token_type": "bearer"})
    _set_auth_cookie(response, access_token)
    _set_refresh_cookie(response, rotated.new_refresh_token)
    return response, HTTPStatus.OK


@auth_bp.route("/me/change-password", methods=["POST"])
@token_required
def change_my_password(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    if not user.is_admin_role:
        return jsonify({"message": "This feature is for Admins only."}), HTTPStatus.FORBIDDEN

    data = request.get_json()
    try:
        validated_data = ChangePasswordRequestSchema.model_validate(data)
    except ValidationError as e:
        return jsonify({"message": "Invalid input.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    if not user.password_hash or not check_password_hash(user.password_hash, validated_data.current_password):
        return jsonify({"message": "Current password is incorrect."}), HTTPStatus.UNAUTHORIZED

    user.password_hash = generate_password_hash(validated_data.new_password)
    db.session.commit()

    try:
        if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            change_time_wita = format_datetime_to_wita(datetime.now(dt_timezone.utc))
            context = {"phone_number": user.phone_number, "change_time": change_time_wita}
            message_body = get_notification_message("password_change_notification", context)
            send_whatsapp_message(user.phone_number, message_body)
    except Exception as e_notif:
        current_app.logger.error(
            f"Failed to send password change notification for admin {user.id}: {e_notif}", exc_info=True
        )

    return jsonify({"message": "Password changed successfully."}), HTTPStatus.OK


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout_user(current_user_id: uuid.UUID):
    current_app.logger.info(f"User {current_user_id} initiated logout.")
    refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
    raw_refresh = request.cookies.get(refresh_cookie_name)
    if raw_refresh:
        try:
            revoke_refresh_token(raw_refresh)
        except Exception:
            pass

    response = jsonify({"message": "Logout successful"})
    _clear_auth_cookie(response)
    _clear_refresh_cookie(response)
    return response, HTTPStatus.OK
