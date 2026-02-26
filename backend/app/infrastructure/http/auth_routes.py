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
from app.infrastructure.http.error_envelope import build_error_payload, error_response
from app.infrastructure.http.auth_contexts.otp_handlers import request_otp_impl
from app.infrastructure.http.auth_contexts.session_handlers import consume_session_token_impl
from app.infrastructure.http.auth_contexts.profile_handlers import get_current_user_impl, update_user_profile_impl
from app.infrastructure.http.auth_contexts.admin_auth_handlers import (
    admin_login_impl,
    refresh_access_token_impl,
    logout_user_impl,
)
from app.infrastructure.http.auth_contexts.login_handlers import auto_login_impl
from app.infrastructure.http.auth_contexts.status_handlers import verify_status_token_impl, debug_binding_impl
from app.infrastructure.http.auth_contexts.verify_otp_handlers import verify_otp_impl

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
    payload = build_error_payload(
        message,
        status_code=HTTPStatus.FORBIDDEN,
        code="STATUS_TOKEN_INVALID",
        extra={"status": status, "status_token": token},
    )
    return jsonify(payload)


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
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    return request_otp_impl(
        payload=payload,
        db=db,
        RequestOtpRequestSchema=RequestOtpRequestSchema,
        RequestOtpResponseSchema=RequestOtpResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        normalize_to_e164=normalize_to_e164,
        increment_metric=increment_metric,
        is_otp_cooldown_active=_is_otp_cooldown_active,
        is_demo_phone_allowed=_is_demo_phone_allowed,
        get_phone_number_variations=get_phone_number_variations,
        set_otp_cooldown=_set_otp_cooldown,
        build_status_error=_build_status_error,
        generate_otp=generate_otp,
        store_otp_in_redis=store_otp_in_redis,
        send_otp_whatsapp=send_otp_whatsapp,
        validation_error_details=_validation_error_details,
    )


@auth_bp.route("/verify-otp", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("OTP_VERIFY_RATE_LIMIT", "10 per minute;60 per hour"),
    key_func=_rate_limit_key_with_phone,
)
def verify_otp():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    return verify_otp_impl(
        payload=payload,
        request=request,
        db=db,
        User=User,
        UserRole=UserRole,
        ApprovalStatus=ApprovalStatus,
        UserDevice=UserDevice,
        UserLoginHistory=UserLoginHistory,
        VerifyOtpRequestSchema=VerifyOtpRequestSchema,
        VerifyOtpResponseSchema=VerifyOtpResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        normalize_to_e164=normalize_to_e164,
        get_phone_number_variations=get_phone_number_variations,
        is_demo_phone_allowed=_is_demo_phone_allowed,
        get_otp_fail_count=_get_otp_fail_count,
        increment_otp_fail_count=_increment_otp_fail_count,
        clear_otp_fail_count=_clear_otp_fail_count,
        increment_metric=increment_metric,
        verify_otp_from_redis=verify_otp_from_redis,
        create_access_token=create_access_token,
        issue_refresh_token_for_user=issue_refresh_token_for_user,
        store_session_token=_store_session_token,
        format_to_local_phone=format_to_local_phone,
        is_hotspot_login_required=is_hotspot_login_required,
        resolve_binding_context=resolve_binding_context,
        apply_device_binding_for_login=apply_device_binding_for_login,
        sync_address_list_for_single_user=sync_address_list_for_single_user,
        build_status_error=_build_status_error,
        validation_error_details=_validation_error_details,
        set_auth_cookie=_set_auth_cookie,
        set_refresh_cookie=_set_refresh_cookie,
        settings_service=settings_service,
        generate_password_hash=generate_password_hash,
        secrets_module=secrets,
    )


@auth_bp.route("/auto-login", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("AUTO_LOGIN_RATE_LIMIT", "60 per minute"), key_func=_rate_limit_key_with_ip
)
def auto_login():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else {}
    return auto_login_impl(
        payload=payload,
        request=request,
        db=db,
        User=User,
        UserDevice=UserDevice,
        ApprovalStatus=ApprovalStatus,
        UserRole=UserRole,
        UserLoginHistory=UserLoginHistory,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        VerifyOtpResponseSchema=VerifyOtpResponseSchema,
        get_client_ip=get_client_ip,
        normalize_mac=normalize_mac,
        resolve_client_mac=resolve_client_mac,
        get_phone_number_variations=get_phone_number_variations,
        get_mikrotik_connection=get_mikrotik_connection,
        get_hotspot_active_session_by_ip=get_hotspot_active_session_by_ip,
        apply_device_binding_for_login=apply_device_binding_for_login,
        sync_address_list_for_single_user=sync_address_list_for_single_user,
        create_access_token=create_access_token,
        issue_refresh_token_for_user=issue_refresh_token_for_user,
        set_auth_cookie=_set_auth_cookie,
        set_refresh_cookie=_set_refresh_cookie,
        build_status_error=_build_status_error,
    )


@auth_bp.route("/session/consume", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("SESSION_CONSUME_RATE_LIMIT", "30 per minute"), key_func=_rate_limit_key_with_ip
)
def consume_session_token():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    return consume_session_token_impl(
        payload=payload,
        db=db,
        User=User,
        ApprovalStatus=ApprovalStatus,
        SessionTokenRequestSchema=SessionTokenRequestSchema,
        VerifyOtpResponseSchema=VerifyOtpResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        consume_session_token=_consume_session_token,
        build_status_error=_build_status_error,
        create_access_token=create_access_token,
        issue_refresh_token_for_user=issue_refresh_token_for_user,
        set_auth_cookie=_set_auth_cookie,
        set_refresh_cookie=_set_refresh_cookie,
        validation_error_details=_validation_error_details,
        user_agent=request.headers.get("User-Agent"),
    )


@auth_bp.route("/status-token/verify", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("SESSION_CONSUME_RATE_LIMIT", "30 per minute"), key_func=_rate_limit_key_with_ip
)
def verify_status_token():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    return verify_status_token_impl(
        payload=payload,
        StatusTokenVerifyRequestSchema=StatusTokenVerifyRequestSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        verify_status_token=_verify_status_token,
        validation_error_details=_validation_error_details,
    )


@auth_bp.route("/debug/binding", methods=["POST"])
@admin_required
def debug_binding(current_admin=None):
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() if request.form else None
    return debug_binding_impl(
        payload=payload,
        db=db,
        User=User,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        get_phone_number_variations=get_phone_number_variations,
        resolve_binding_context=resolve_binding_context,
    )


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user(current_user_id: uuid.UUID):
    return get_current_user_impl(
        current_user_id=current_user_id,
        db=db,
        User=User,
        UserMeResponseSchema=UserMeResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        is_demo_phone_allowed=_is_demo_phone_allowed,
        build_status_error=_build_status_error,
        create_access_token=create_access_token,
        set_auth_cookie=_set_auth_cookie,
        validation_error_details=_validation_error_details,
    )


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
    return update_user_profile_impl(
        current_user_id=current_user_id,
        db=db,
        User=User,
        UserRole=UserRole,
        ApprovalStatus=ApprovalStatus,
        request=request,
        UserProfileUpdateRequestSchema=UserProfileUpdateRequestSchema,
        UserMeResponseSchema=UserMeResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        is_demo_phone_allowed=_is_demo_phone_allowed,
        validation_error_details=_validation_error_details,
    )


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
        return error_response("An internal error occurred.", status_code=HTTPStatus.INTERNAL_SERVER_ERROR)


@auth_bp.route("/admin/login", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("ADMIN_LOGIN_RATE_LIMIT", "10 per minute;60 per hour"),
    key_func=_rate_limit_key_with_ip,
)
def admin_login():
    from app.infrastructure.http.schemas.auth_schemas import validate_phone_number

    return admin_login_impl(
        request=request,
        db=db,
        User=User,
        ApprovalStatus=ApprovalStatus,
        UserLoginHistory=UserLoginHistory,
        verify_password=check_password_hash,
        increment_metric=increment_metric,
        get_client_ip=get_client_ip,
        format_to_local_phone=format_to_local_phone,
        format_datetime_to_wita=format_datetime_to_wita,
        settings_service=settings_service,
        get_notification_message=get_notification_message,
        send_whatsapp_message=send_whatsapp_message,
        whatsapp_available=WHATSAPP_AVAILABLE,
        create_access_token=create_access_token,
        issue_refresh_token_for_user=issue_refresh_token_for_user,
        set_auth_cookie=_set_auth_cookie,
        set_refresh_cookie=_set_refresh_cookie,
        VerifyOtpResponseSchema=VerifyOtpResponseSchema,
        get_phone_number_variations=get_phone_number_variations,
        validate_phone_number=validate_phone_number,
    )


@auth_bp.route("/refresh", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("REFRESH_TOKEN_RATE_LIMIT", "60 per minute"), key_func=_rate_limit_key_with_ip
)
def refresh_access_token():
    return refresh_access_token_impl(
        request=request,
        current_app=current_app,
        db=db,
        User=User,
        ApprovalStatus=ApprovalStatus,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        rotate_refresh_token=rotate_refresh_token,
        create_access_token=create_access_token,
        set_auth_cookie=_set_auth_cookie,
        set_refresh_cookie=_set_refresh_cookie,
        build_status_error=_build_status_error,
    )


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
    return logout_user_impl(
        current_user_id=current_user_id,
        request=request,
        current_app=current_app,
        revoke_refresh_token=revoke_refresh_token,
        clear_auth_cookie=_clear_auth_cookie,
        clear_refresh_cookie=_clear_refresh_cookie,
    )
