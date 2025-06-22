# backend/app/infrastructure/http/auth_routes.py
import random
import string
import secrets
from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from http import HTTPStatus
from datetime import datetime, timedelta, timezone as dt_timezone
from jose import jwt, JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
import uuid
from werkzeug.security import check_password_hash, generate_password_hash
from typing import Optional

from .decorators import token_required
from app.utils.request_utils import get_client_ip
from .schemas.auth_schemas import (
    RequestOtpRequestSchema, VerifyOtpRequestSchema,
    RequestOtpResponseSchema, VerifyOtpResponseSchema, AuthErrorResponseSchema,
    UserRegisterRequestSchema, UserRegisterResponseSchema,
    ChangePasswordRequestSchema
)
from app.infrastructure.http.schemas.user_schemas import UserMeResponseSchema, UserProfileUpdateRequestSchema
from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, ApprovalStatus, UserLoginHistory,
    NotificationRecipient, NotificationType, PromoEvent, PromoEventStatus
)
from app.infrastructure.gateways.whatsapp_client import send_otp_whatsapp
from user_agents import parse as parse_user_agent
from app.services.notification_service import get_notification_message
from app.services import settings_service
from app.utils.formatters import format_datetime_to_wita, format_to_local_phone

# --- [PERBAIKAN KUNCI] ---
# 1. Impor helper password dari lokasi yang benar
from app.services.user_management.helpers import _generate_password
from app.services.user_management.user_profile import _get_active_registration_bonus

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    def send_whatsapp_message(to: str, body: str) -> bool:
        current_app.logger.warning("WhatsApp client not available. Dummy send_whatsapp_message called.")
        return False

try:
    from app.infrastructure.gateways.mikrotik_client import (
        get_mikrotik_connection,
        activate_or_update_hotspot_user,
        delete_hotspot_user
    )
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    MIKROTIK_CLIENT_AVAILABLE = False
    def get_mikrotik_connection(): return None
    def activate_or_update_hotspot_user(api_connection, user_mikrotik_username: str, mikrotik_profile_name: str, hotspot_password: str, comment:str="", limit_bytes_total: Optional[int] = None, session_timeout_seconds: Optional[int] = None, force_update_profile: bool = False): return False, "Mikrotik client not available"
    def delete_hotspot_user(api_connection, username: str): return False, "Mikrotik client not available"


auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# --- Helper functions ---

def generate_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))

def store_otp_in_redis(phone_number: str, otp: str) -> bool:
    try:
        key = f"otp:{phone_number}"
        expire_seconds = current_app.config.get('OTP_EXPIRE_SECONDS', 300)
        redis_client = current_app.redis_client_otp
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
        redis_client = current_app.redis_client_otp
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

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire_delta = timedelta(minutes=current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 120))
    expire_at_utc = datetime.now(dt_timezone.utc) + expire_delta
    to_encode.update({"exp": expire_at_utc, "iat": datetime.now(dt_timezone.utc)})
    return jwt.encode(to_encode, current_app.config['JWT_SECRET_KEY'], algorithm=current_app.config['JWT_ALGORITHM'])

# --- Routes ---

@auth_bp.route('/register', methods=['POST'])
def register_user():
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        normalized_phone_number = data_input.phone_number
        if db.session.execute(select(User.id).filter_by(phone_number=normalized_phone_number)).scalar_one_or_none():
            return jsonify(AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()), HTTPStatus.CONFLICT
        
        ua_string = request.headers.get('User-Agent')
        device_brand, device_model, raw_ua = None, None, None
        if ua_string:
            raw_ua = ua_string[:1024]
            ua_info = parse_user_agent(ua_string)
            device_brand = getattr(ua_info.device, 'brand', None)
            device_model = getattr(ua_info.device, 'model', None)
        
        new_user_obj = User(
            phone_number=normalized_phone_number, 
            full_name=data_input.full_name, 
            approval_status=ApprovalStatus.PENDING_APPROVAL, 
            is_active=False,
            device_brand=device_brand, 
            device_model=device_model, 
            raw_user_agent=raw_ua,
            is_unlimited_user=False
        )
        
        if data_input.register_as_komandan:
            new_user_obj.role = UserRole.KOMANDAN
            new_user_obj.mikrotik_server_name = 'srv-komandan'
        else:
            new_user_obj.role = UserRole.USER
            new_user_obj.mikrotik_server_name = 'srv-user'
            new_user_obj.blok = data_input.blok
            new_user_obj.kamar = data_input.kamar

        # --- [PERBAIKAN] Logika pemberian bonus registrasi otomatis saat user mendaftar mandiri ---
        active_bonus = _get_active_registration_bonus()
        if active_bonus and active_bonus.bonus_value_mb and active_bonus.bonus_duration_days:
            current_app.logger.info(f"Menerapkan bonus registrasi '{active_bonus.name}' untuk pendaftar baru {new_user_obj.full_name}")
            new_user_obj.total_quota_purchased_mb = active_bonus.bonus_value_mb
            new_user_obj.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=active_bonus.bonus_duration_days)
        else:
            new_user_obj.total_quota_purchased_mb = 0
            new_user_obj.quota_expiry_date = None
        # --- Akhir Perbaikan ---

        db.session.add(new_user_obj)
        db.session.commit()
        db.session.refresh(new_user_obj)

        try:
            if WHATSAPP_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
                user_context = {"full_name": new_user_obj.full_name}
                user_message = get_notification_message("user_self_register_pending", user_context)
                send_whatsapp_message(new_user_obj.phone_number, user_message)

                recipients_query = select(User).join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id).where(
                    NotificationRecipient.notification_type == NotificationType.NEW_USER_REGISTRATION, User.is_active == True
                )
                recipients = db.session.scalars(recipients_query).all()
                if recipients:
                    admin_context = {
                        "full_name": new_user_obj.full_name, 
                        "phone_number": new_user_obj.phone_number,
                        "blok": new_user_obj.blok if new_user_obj.blok else 'N/A',
                        "kamar": new_user_obj.kamar if new_user_obj.kamar else 'N/A',
                        "role": new_user_obj.role.value
                    }
                    admin_message = get_notification_message("new_user_registration_to_admin", admin_context)
                    for admin in recipients:
                        send_whatsapp_message(admin.phone_number, admin_message)
        except Exception as e_notify:
            current_app.logger.error(f"Failed to send new user registration notifications: {e_notify}", exc_info=True)
        
        return jsonify(UserRegisterResponseSchema(message="Registration successful. Your account is awaiting Admin approval.", user_id=new_user_obj.id, phone_number=new_user_obj.phone_number).model_dump()), HTTPStatus.CREATED
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Invalid input.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except IntegrityError:
        db.session.rollback()
        return jsonify(AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /register: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="An unexpected error occurred during registration.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/request-otp', methods=['POST'])
def request_otp():
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data = RequestOtpRequestSchema.model_validate(request.json)
        user_for_otp = db.session.execute(select(User).filter_by(phone_number=data.phone_number)).scalar_one_or_none()
        if not user_for_otp:
            return jsonify(AuthErrorResponseSchema(error="Phone number is not registered.").model_dump()), HTTPStatus.NOT_FOUND
        if not user_for_otp.is_active or user_for_otp.approval_status != ApprovalStatus.APPROVED:
            return jsonify(AuthErrorResponseSchema(error="Login failed. Your account is not active or approved yet.").model_dump()), HTTPStatus.FORBIDDEN
        
        otp_generated = generate_otp()
        if not store_otp_in_redis(data.phone_number, otp_generated):
            return jsonify(AuthErrorResponseSchema(error="Failed to process OTP request.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        
        send_otp_whatsapp(data.phone_number, otp_generated)
        
        return jsonify(RequestOtpResponseSchema().model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Invalid input.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /request-otp: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data = VerifyOtpRequestSchema.model_validate(request.json)
        if not verify_otp_from_redis(data.phone_number, data.otp):
            return jsonify(AuthErrorResponseSchema(error="Invalid or expired OTP code.").model_dump()), HTTPStatus.UNAUTHORIZED
        
        user_to_login = db.session.execute(select(User).filter_by(phone_number=data.phone_number)).scalar_one_or_none()
        if not user_to_login:
            return jsonify(AuthErrorResponseSchema(error="User not found after OTP verification.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        if not user_to_login.is_active or user_to_login.approval_status != ApprovalStatus.APPROVED:
            return jsonify(AuthErrorResponseSchema(error="Account is not active or approved.").model_dump()), HTTPStatus.FORBIDDEN
        
        user_to_login.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = UserLoginHistory(user_id=user_to_login.id, ip_address=get_client_ip(), user_agent_string=request.headers.get('User-Agent'))
        db.session.add(new_login_entry)
        
        db.session.commit()

        jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
        access_token = create_access_token(data=jwt_payload)
        return jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Invalid input.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /verify-otp: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not user.is_active:
        return jsonify(AuthErrorResponseSchema(error="User account is not active.").model_dump()), HTTPStatus.FORBIDDEN
    try:
        return jsonify(UserMeResponseSchema.model_validate(user).model_dump(mode='json')), HTTPStatus.OK
    except ValidationError as e:
        current_app.logger.error(f"[/me] Pydantic validation FAILED for user {user.id}: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="User data on server is invalid.", details=e.errors()).model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/me/profile', methods=['PUT'])
@token_required
def update_user_profile(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user: return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return jsonify(AuthErrorResponseSchema(error="Your account is not active or approved to update profile.").model_dump()), HTTPStatus.FORBIDDEN

    try:
        update_data = UserProfileUpdateRequestSchema.model_validate(request.get_json())
        user.full_name = update_data.full_name
        if user.role == UserRole.USER:
            user.blok = update_data.blok
            user.kamar = update_data.kamar
        db.session.commit()
        return jsonify(UserMeResponseSchema.model_validate(user).model_dump(mode='json')), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Invalid input.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update user profile {user.id}: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="An internal error occurred.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        
@auth_bp.route('/users/me/reset-hotspot-password', methods=['POST'])
@token_required
def reset_hotspot_password(current_user_id: uuid.UUID):
    current_user = db.session.get(User, current_user_id)
    if not current_user: return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if current_user.is_admin_role: return jsonify({"message": "Access denied. This feature is not for admin roles."}), HTTPStatus.FORBIDDEN
    if not current_user.is_active or current_user.approval_status != ApprovalStatus.APPROVED: return jsonify({"message": "Your account is not active or approved. Cannot reset password."}), HTTPStatus.FORBIDDEN

    try:
        # --- [PERBAIKAN KUNCI] ---
        # 2. Menggunakan helper yang konsisten untuk membuat password.
        new_mikrotik_password = _generate_password(length=6, numeric_only=True)

        if MIKROTIK_CLIENT_AVAILABLE:
            with get_mikrotik_connection() as mikrotik_conn:
                if mikrotik_conn:
                    profile_key = 'MIKROTIK_KOMANDAN_PROFILE' if current_user.role == UserRole.KOMANDAN else 'MIKROTIK_USER_PROFILE'
                    fallback_profile = 'komandan' if current_user.role == UserRole.KOMANDAN else 'user'
                    mikrotik_profile_name = settings_service.get_setting(profile_key, fallback_profile)
                    
                    activate_or_update_hotspot_user(
                        api_connection=mikrotik_conn,
                        user_mikrotik_username=format_to_local_phone(current_user.phone_number),
                        mikrotik_profile_name=mikrotik_profile_name,
                        hotspot_password=new_mikrotik_password,
                        comment=f"Password reset by user via Portal",
                        server=current_user.mikrotik_server_name
                    )
        current_user.mikrotik_password = new_mikrotik_password
        db.session.commit()

        if WHATSAPP_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            context = {"full_name": current_user.full_name, "username": format_to_local_phone(current_user.phone_number), "password": new_mikrotik_password}
            message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
            send_whatsapp_message(current_user.phone_number, message_body)
            
        return jsonify({"success": True, "message": "New hotspot password successfully generated and sent via WhatsApp!"}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Internal error while resetting hotspot password for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An internal error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    if not request.is_json: return jsonify({"message": "Request body must be JSON."}), HTTPStatus.BAD_REQUEST
    data = request.get_json()
    username_input = data.get('username')
    password = data.get('password')
    if not username_input or not password: return jsonify({"message": "Username and password are required."}), HTTPStatus.BAD_REQUEST
    
    try:
        from app.infrastructure.http.schemas.auth_schemas import validate_phone_number
        normalized_phone = validate_phone_number(username_input)
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    
    user_to_login = db.session.execute(db.select(User).filter(User.phone_number == normalized_phone)).scalar_one_or_none()
    
    if not user_to_login or not user_to_login.is_admin_role or not user_to_login.password_hash or not check_password_hash(user_to_login.password_hash, password):
        return jsonify({"message": "Invalid username or password."}), HTTPStatus.UNAUTHORIZED
    
    user_to_login.last_login_at = datetime.now(dt_timezone.utc)
    new_login_entry = UserLoginHistory(user_id=user_to_login.id, ip_address=get_client_ip(), user_agent_string=request.headers.get('User-Agent'))
    db.session.add(new_login_entry)
    db.session.commit()
    
    jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
    access_token = create_access_token(data=jwt_payload)
    return jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump()), HTTPStatus.OK

@auth_bp.route('/me/change-password', methods=['POST'])
@token_required
def change_my_password(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user: return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

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
        if WHATSAPP_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            change_time_wita = format_datetime_to_wita(datetime.now(dt_timezone.utc))
            context = {"phone_number": user.phone_number, "change_time": change_time_wita}
            message_body = get_notification_message("password_change_notification", context)
            send_whatsapp_message(user.phone_number, message_body)
    except Exception as e_notif:
        current_app.logger.error(f"Failed to send password change notification for admin {user.id}: {e_notif}", exc_info=True)

    return jsonify({"message": "Password changed successfully."}), HTTPStatus.OK

@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout_user(current_user_id: uuid.UUID):
    current_app.logger.info(f"User {current_user_id} initiated logout.")
    return jsonify({"message": "Logout successful"}), HTTPStatus.OK