# backend/app/infrastructure/http/auth_routes.py
# VERSI FINAL: Menggunakan decorator dari file terpisah dan menghapus pengelolaan sesi manual.

from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from http import HTTPStatus
import random
import string
from datetime import datetime, timedelta, timezone as dt_timezone
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select
from functools import wraps
import uuid
import enum
from typing import Optional, Dict, Any
from werkzeug.security import check_password_hash, generate_password_hash
import logging
import sys

# --- PERUBAHAN KUNCI: Impor decorator dari file baru ---
from .decorators import token_required

# Impor lokal lainnya
from app.utils.request_utils import get_client_ip
from .schemas.auth_schemas import (
    RequestOtpRequestSchema, VerifyOtpRequestSchema,
    RequestOtpResponseSchema, VerifyOtpResponseSchema, AuthErrorResponseSchema,
    UserRegisterRequestSchema, UserRegisterResponseSchema, validate_phone_number
)
from .schemas.user_schemas import UserMeResponseSchema
from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserLoginHistory
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message, send_otp_whatsapp
from app.infrastructure.gateways.mikrotik_client import format_to_local_phone
from user_agents import parse as parse_user_agent

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# --- DEFINISI DECORATOR DIPINDAHKAN ---
# Definisi untuk token_required dan admin_required sekarang berada di dalam 
# file 'app/infrastructure/http/decorators.py' untuk mencegah circular import.


# --- Helper Functions (TIDAK BERUBAH) ---
def generate_otp(length: int = 6) -> str:
    """Generates a random numeric OTP."""
    return "".join(random.choices(string.digits, k=length))

def store_otp_in_redis(phone_number: str, otp: str) -> bool:
    """Stores OTP in Redis with an expiration time."""
    try:
        key = f"otp:{phone_number}"
        expire_seconds = current_app.config.get('OTP_EXPIRE_SECONDS', 300)
        redis_client = current_app.redis_client_otp
        if redis_client is None:
            current_app.logger.error(f"Redis client for OTP (redis_client_otp) is not initialized.")
            return False
        redis_client.setex(key, expire_seconds, otp)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to store OTP in Redis for {phone_number}: {e}", exc_info=True)
        return False

def verify_otp_from_redis(phone_number: str, otp_code: str) -> bool:
    """Verifies OTP from Redis and deletes it if valid."""
    try:
        key = f"otp:{phone_number}"
        redis_client = current_app.redis_client_otp
        if redis_client is None:
            current_app.logger.error(f"Redis client for OTP (redis_client_otp) is not initialized.")
            return False
        stored_otp = redis_client.get(key)
        if stored_otp and stored_otp.decode('utf-8') == otp_code:
            redis_client.delete(key)
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve OTP from Redis for {phone_number}: {e}", exc_info=True)
        return False

def create_access_token(data: dict) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire_delta = timedelta(minutes=current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 120))
    expire_at_utc = datetime.now(dt_timezone.utc) + expire_delta
    to_encode.update({"exp": expire_at_utc, "iat": datetime.now(dt_timezone.utc)})
    return jwt.encode(to_encode, current_app.config['JWT_SECRET_KEY'], algorithm=current_app.config['JWT_ALGORITHM'])


# === Endpoint /register (DIPERBAIKI) ===
@auth_bp.route('/register', methods=['POST'])
def register_user():
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        normalized_phone_number = data_input.phone_number

        if db.session.execute(select(User.id).filter_by(phone_number=normalized_phone_number)).scalar_one_or_none():
            return jsonify(AuthErrorResponseSchema(error="Nomor telepon sudah terdaftar.").model_dump()), HTTPStatus.CONFLICT

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
            blok=data_input.blok,
            kamar=data_input.kamar,
            role=UserRole.USER,
            approval_status=ApprovalStatus.PENDING_APPROVAL,
            is_active=False,
            device_brand=device_brand,
            device_model=device_model,
            raw_user_agent=raw_ua
        )
        db.session.add(new_user_obj)
        db.session.commit()
        db.session.refresh(new_user_obj)
        
        # (Logika notifikasi WhatsApp Anda ditempatkan di sini jika diperlukan)

        return jsonify(UserRegisterResponseSchema(
            message="Registrasi berhasil. Akun Anda sedang menunggu persetujuan Admin.",
            user_id=new_user_obj.id,
            phone_number=new_user_obj.phone_number
        ).model_dump()), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except IntegrityError:
        db.session.rollback()
        return jsonify(AuthErrorResponseSchema(error="Nomor telepon sudah terdaftar.").model_dump()), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /register: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan tidak terduga saat registrasi.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR


# === Endpoint /request-otp (DIPERBAIKI) ===
@auth_bp.route('/request-otp', methods=['POST'])
def request_otp():
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data = RequestOtpRequestSchema.model_validate(request.json)
        user_for_otp = db.session.execute(select(User).filter_by(phone_number=data.phone_number)).scalar_one_or_none()
        if not user_for_otp:
            return jsonify(AuthErrorResponseSchema(error="Nomor telepon belum terdaftar.").model_dump()), HTTPStatus.NOT_FOUND
        if not user_for_otp.is_active or user_for_otp.approval_status != ApprovalStatus.APPROVED:
            return jsonify(AuthErrorResponseSchema(error="Login gagal. Akun Anda belum aktif atau belum disetujui.").model_dump()), HTTPStatus.FORBIDDEN
        otp_generated = generate_otp()
        if not store_otp_in_redis(data.phone_number, otp_generated):
            return jsonify(AuthErrorResponseSchema(error="Gagal memproses permintaan OTP.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        send_otp_whatsapp(data.phone_number, otp_generated)
        return jsonify(RequestOtpResponseSchema().model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /request-otp: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tidak terduga.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

# === Endpoint /verify-otp (DIPERBAIKI) ===
@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data = VerifyOtpRequestSchema.model_validate(request.json)
        if not verify_otp_from_redis(data.phone_number, data.otp):
            return jsonify(AuthErrorResponseSchema(error="Kode OTP tidak valid atau telah kedaluwarsa.").model_dump()), HTTPStatus.UNAUTHORIZED
        user_to_login = db.session.execute(select(User).filter_by(phone_number=data.phone_number)).scalar_one_or_none()
        if not user_to_login:
            return jsonify(AuthErrorResponseSchema(error="Pengguna tidak ditemukan.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        if not user_to_login.is_active or user_to_login.approval_status != ApprovalStatus.APPROVED:
            return jsonify(AuthErrorResponseSchema(error="Akun belum aktif atau disetujui.").model_dump()), HTTPStatus.FORBIDDEN

        user_to_login.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = UserLoginHistory(user_id=user_to_login.id, ip_address=get_client_ip(), user_agent_string=request.headers.get('User-Agent'))
        db.session.add(new_login_entry)
        db.session.commit()
        
        jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
        access_token = create_access_token(data=jwt_payload)
        return jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /verify-otp: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tidak terduga.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR


# === Endpoint /me (DIPERBAIKI) ===
@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user_id: uuid.UUID):
    # Gunakan get() daripada execute(scalar_one_or_none)
    user = db.session.get(User, current_user_id)
    if not user:
        current_app.logger.error(f"User {current_user_id} tidak ditemukan di database")
        return jsonify(AuthErrorResponseSchema(error="Pengguna tidak ditemukan.").model_dump()), HTTPStatus.NOT_FOUND
    if not user.is_active:
        return jsonify(AuthErrorResponseSchema(error="Akun pengguna tidak aktif.").model_dump()), HTTPStatus.FORBIDDEN
    try:
        user_data_response = UserMeResponseSchema.model_validate(user)
    except ValidationError as e:
        current_app.logger.error(f"[/me] Pydantic validation FAILED for user {user.id}: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Data pengguna di server tidak valid.", details=e.errors()).model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    return jsonify(user_data_response.model_dump(mode='json')), HTTPStatus.OK

# === Endpoint /admin/login (TIDAK BERUBAH) ===
@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    if not request.is_json: return jsonify(AuthErrorResponseSchema(error="Request body harus JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    data = request.get_json()
    username_input = data.get('username')
    password = data.get('password')
    if not username_input or not password:
        return jsonify(AuthErrorResponseSchema(error="Username dan password wajib diisi.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        normalized_phone = validate_phone_number(username_input)
    except ValueError:
        return jsonify(AuthErrorResponseSchema(error="Format nomor telepon tidak valid.").model_dump()), HTTPStatus.BAD_REQUEST
    
    user_to_login = db.session.execute(db.select(User).filter(User.phone_number == normalized_phone)).scalar_one_or_none()
    
    if (not user_to_login or not user_to_login.is_admin_role or not user_to_login.password_hash or not check_password_hash(user_to_login.password_hash, password)):
        current_app.logger.warning(f"Login admin gagal untuk '{normalized_phone}'.")
        return jsonify(AuthErrorResponseSchema(error="Username atau password salah.").model_dump()), HTTPStatus.UNAUTHORIZED

    jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
    access_token = create_access_token(data=jwt_payload)
    current_app.logger.info(f"Login admin BERHASIL untuk user '{normalized_phone}' (ID: {user_to_login.id}).")
    return jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump()), HTTPStatus.OK

# === Endpoint /me/change-password (TIDAK BERUBAH) ===
@auth_bp.route('/me/change-password', methods=['POST'])
@token_required
def change_my_password(current_user_id: uuid.UUID):
    user = db.session.get(User, current_user_id)
    if not user or not user.is_admin_role:
        return jsonify({"message": "Fitur ini hanya untuk Admin."}), HTTPStatus.FORBIDDEN
    data = request.get_json()
    if not data or 'current_password' not in data or 'new_password' not in data:
        return jsonify({"message": "Password saat ini dan password baru wajib diisi."}), HTTPStatus.BAD_REQUEST
    if not user.password_hash or not check_password_hash(user.password_hash, data['current_password']):
        return jsonify({"message": "Password saat ini salah."}), HTTPStatus.UNAUTHORIZED
    if len(data['new_password']) < 6:
        return jsonify({"message": "Password baru minimal 6 karakter."}), HTTPStatus.BAD_REQUEST
    user.password_hash = generate_password_hash(data['new_password'])
    db.session.commit()
    return jsonify({"message": "Password berhasil diubah."}), HTTPStatus.OK

# === Endpoint /logout (DIPERBAIKI) ===
@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout_user(current_user_id: uuid.UUID):
    current_app.logger.info(f"User {current_user_id} initiated logout.")
    return jsonify({"message": "Logout successful"}), HTTPStatus.OK