# backend/app/infrastructure/http/auth_routes.py
import secrets
from flask import Blueprint, request, current_app
from pydantic import ValidationError
import uuid
from werkzeug.security import check_password_hash, generate_password_hash

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
from app.services.user_management.helpers import _generate_password, _handle_mikrotik_operation
from app.services.user_management.user_profile import _get_active_registration_bonus
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    get_mikrotik_connection,
    has_hotspot_ip_binding_for_user,
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
from app.infrastructure.http.auth_contexts.hotspot_status_handlers import get_hotspot_session_status_impl
from app.infrastructure.http.auth_contexts.admin_auth_handlers import (
    admin_login_impl,
    refresh_access_token_impl,
    logout_user_impl,
)
from app.infrastructure.http.auth_contexts.login_handlers import auto_login_impl
from app.infrastructure.http.auth_contexts.status_handlers import verify_status_token_impl, debug_binding_impl
from app.infrastructure.http.auth_contexts.verify_otp_handlers import verify_otp_impl
from app.infrastructure.http.auth_contexts.shared_helpers import (
    clear_auth_cookie_helper,
    clear_refresh_cookie_helper,
    clear_otp_fail_count,
    consume_session_token_value,
    generate_otp_code,
    get_otp_fail_count,
    increment_otp_fail_count,
    is_demo_mode_enabled,
    is_demo_phone_allowed,
    is_demo_phone_whitelisted,
    is_otp_cooldown_active,
    rate_limit_key_with_ip,
    rate_limit_key_with_phone,
    set_auth_cookie_helper,
    set_otp_cooldown,
    set_refresh_cookie_helper,
    store_otp_in_redis,
    store_session_token,
    validation_error_details,
    verify_otp_from_redis,
    verify_status_token_value,
    build_status_error_payload,
)
from app.infrastructure.http.auth_contexts.register_handlers import register_user_impl
from app.infrastructure.http.auth_contexts.account_handlers import (
    get_my_telegram_status_impl,
    unlink_my_telegram_impl,
    create_my_telegram_link_token_impl,
    reset_hotspot_password_impl,
    change_my_password_impl,
)

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

_set_auth_cookie = set_auth_cookie_helper
_clear_auth_cookie = clear_auth_cookie_helper
_set_refresh_cookie = set_refresh_cookie_helper
_clear_refresh_cookie = clear_refresh_cookie_helper
_rate_limit_key_with_phone = rate_limit_key_with_phone
_rate_limit_key_with_ip = rate_limit_key_with_ip
_validation_error_details = validation_error_details
_is_otp_cooldown_active = is_otp_cooldown_active
_is_demo_mode_enabled = is_demo_mode_enabled
_is_demo_phone_allowed = is_demo_phone_allowed
_is_demo_phone_whitelisted = is_demo_phone_whitelisted
_set_otp_cooldown = set_otp_cooldown
_get_otp_fail_count = get_otp_fail_count
_increment_otp_fail_count = increment_otp_fail_count
_clear_otp_fail_count = clear_otp_fail_count
_store_session_token = store_session_token
_consume_session_token = consume_session_token_value
_verify_status_token = verify_status_token_value


def _build_status_error(status: str, message: str):
    return build_status_error_payload(status=status, message=message, build_error_payload=build_error_payload)


def generate_otp(length: int = 6) -> str:
    return generate_otp_code(length=length)


# --- Routes ---


@auth_bp.route("/register", methods=["POST"])
@limiter.limit(
    lambda: current_app.config.get("REGISTER_RATE_LIMIT", "5 per minute;20 per hour"), key_func=_rate_limit_key_with_ip
)
def register_user():
    return register_user_impl(
        request=request,
        db=db,
        User=User,
        UserRole=UserRole,
        ApprovalStatus=ApprovalStatus,
        NotificationRecipient=NotificationRecipient,
        NotificationType=NotificationType,
        UserRegisterRequestSchema=UserRegisterRequestSchema,
        UserRegisterResponseSchema=UserRegisterResponseSchema,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        normalize_to_e164=normalize_to_e164,
        get_phone_number_variations=get_phone_number_variations,
        settings_service=settings_service,
        get_active_registration_bonus=_get_active_registration_bonus,
        get_notification_message=get_notification_message,
        send_whatsapp_message=send_whatsapp_message,
        whatsapp_available=WHATSAPP_AVAILABLE,
        validation_error_details=_validation_error_details,
    )


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
        is_demo_mode_enabled=_is_demo_mode_enabled,
        is_demo_phone_allowed=_is_demo_phone_allowed,
        is_demo_phone_whitelisted=_is_demo_phone_whitelisted,
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
        get_mikrotik_connection=get_mikrotik_connection,
        has_hotspot_ip_binding_for_user=has_hotspot_ip_binding_for_user,
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


@auth_bp.route("/hotspot-session-status", methods=["GET"])
@token_required
def get_hotspot_session_status(current_user_id: uuid.UUID):
    return get_hotspot_session_status_impl(
        current_user_id=current_user_id,
        db=db,
        User=User,
        AuthErrorResponseSchema=AuthErrorResponseSchema,
        format_to_local_phone=format_to_local_phone,
        is_hotspot_login_required=is_hotspot_login_required,
        get_mikrotik_connection=get_mikrotik_connection,
        has_hotspot_ip_binding_for_user=has_hotspot_ip_binding_for_user,
    )


@auth_bp.route("/me/telegram/status", methods=["GET"])
@token_required
def get_my_telegram_status(current_user_id: uuid.UUID):
    return get_my_telegram_status_impl(current_user_id=current_user_id, db=db, User=User)


@auth_bp.route("/me/telegram/unlink", methods=["POST"])
@token_required
def unlink_my_telegram(current_user_id: uuid.UUID):
    return unlink_my_telegram_impl(current_user_id=current_user_id, db=db, User=User)


@auth_bp.route("/me/telegram/link-token", methods=["POST"])
@token_required
def create_my_telegram_link_token(current_user_id: uuid.UUID):
    return create_my_telegram_link_token_impl(
        current_user_id=current_user_id,
        db=db,
        User=User,
        settings_service=settings_service,
        generate_user_link_token=generate_user_link_token,
        current_app=current_app,
    )


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
    return reset_hotspot_password_impl(
        current_user_id=current_user_id,
        db=db,
        User=User,
        ApprovalStatus=ApprovalStatus,
        WHATSAPP_AVAILABLE=WHATSAPP_AVAILABLE,
        settings_service=settings_service,
        _generate_password=_generate_password,
        format_to_local_phone=format_to_local_phone,
        _handle_mikrotik_operation=_handle_mikrotik_operation,
        activate_or_update_hotspot_user=activate_or_update_hotspot_user,
        get_notification_message=get_notification_message,
        send_whatsapp_message=send_whatsapp_message,
        error_response=error_response,
        current_app=current_app,
    )


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
    return change_my_password_impl(
        current_user_id=current_user_id,
        request=request,
        db=db,
        User=User,
        ChangePasswordRequestSchema=ChangePasswordRequestSchema,
        ValidationError=ValidationError,
        check_password_hash=check_password_hash,
        generate_password_hash=generate_password_hash,
        WHATSAPP_AVAILABLE=WHATSAPP_AVAILABLE,
        settings_service=settings_service,
        format_datetime_to_wita=format_datetime_to_wita,
        get_notification_message=get_notification_message,
        send_whatsapp_message=send_whatsapp_message,
        current_app=current_app,
    )


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
