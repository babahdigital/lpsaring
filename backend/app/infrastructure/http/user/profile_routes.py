# backend/app/infrastructure/http/user/profile_routes.py
# Berisi endpoint yang berhubungan dengan manajemen profil dan keamanan pengguna.

import uuid
from flask import Blueprint, request, jsonify, abort, current_app
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus
from typing import Optional
from datetime import datetime, timezone as dt_timezone

from app.extensions import db
from app.services import settings_service
from app.services.notification_service import get_notification_message

# --- PERBAIKAN IMPORT DI SINI ---
# Impor fungsi dari lokasi yang benar di modul service, bukan dari file rute lain.
from app.services.transaction_service import generate_random_password
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.utils.formatters import format_to_local_phone
# -----------------------------

from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserLoginHistory
from ..schemas.user_schemas import UserProfileResponseSchema, UserProfileUpdateRequestSchema
from ..decorators import token_required


profile_bp = Blueprint('user_profile_api', __name__, url_prefix='/api/users')

@profile_bp.route('/me/profile', methods=['GET', 'PUT'])
@token_required
def handle_my_profile(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")

    if request.method == 'GET':
        profile_data = UserProfileResponseSchema.model_validate(user)
        return jsonify(profile_data.model_dump(mode='json')), HTTPStatus.OK

    elif request.method == 'PUT':
        if user.role != UserRole.USER:
            abort(HTTPStatus.FORBIDDEN, description="Endpoint ini hanya untuk pengguna biasa (USER).")

        json_data = request.get_json(silent=True)
        if not json_data:
            return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

        try:
            update_data = UserProfileUpdateRequestSchema.model_validate(json_data)
            user_updated = False

            if update_data.full_name is not None and user.full_name != update_data.full_name:
                user.full_name, user_updated = update_data.full_name, True
            if hasattr(update_data, 'blok') and user.blok != (update_data.blok.value if update_data.blok else None):
                user.blok, user_updated = (update_data.blok.value if update_data.blok else None), True
            if hasattr(update_data, 'kamar') and user.kamar != (update_data.kamar.value if update_data.kamar else None):
                user.kamar, user_updated = (update_data.kamar.value if update_data.kamar else None), True

            if user_updated:
                db.session.commit()
            
            resp_data = UserProfileResponseSchema.model_validate(user)
            return jsonify(resp_data.model_dump(mode='json')), HTTPStatus.OK

        except ValidationError as e:
            return jsonify({"message": "Data input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
        except Exception as e:
            db.session.rollback()
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan internal: {str(e)}")

@profile_bp.route('/me/reset-hotspot-password', methods=['POST'])
@token_required
def reset_my_hotspot_password(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user: abort(HTTPStatus.NOT_FOUND, "Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, "Akun Anda belum aktif atau disetujui.")
    
    if user.is_admin_role:
        abort(HTTPStatus.FORBIDDEN, "Fitur ini tidak untuk role Admin. Gunakan panel admin untuk mereset.")

    mikrotik_username = format_to_local_phone(user.phone_number)
    if not mikrotik_username:
        abort(HTTPStatus.BAD_REQUEST, "Format nomor telepon tidak valid.")

    # Perbaikan: Menyesuaikan pemanggilan fungsi dengan menghapus argumen 'numeric_only' yang tidak ada.
    new_password = generate_random_password(length=6)
    
    with get_mikrotik_connection() as api_conn:
        if not api_conn: abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal koneksi ke sistem hotspot.")
        
        mikrotik_profile_name = ""
        if hasattr(user, 'current_package_profile_name') and user.current_package_profile_name:
             mikrotik_profile_name = user.current_package_profile_name
        else: # Fallback jika profil saat ini tidak tersimpan di user
             mikrotik_profile_name = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')

        success, msg = activate_or_update_hotspot_user(
            api_connection=api_conn, user_mikrotik_username=mikrotik_username,
            mikrotik_profile_name=mikrotik_profile_name, hotspot_password=new_password,
            comment=f"Password Reset by User: {user.full_name}", force_update_profile=False
        )
        if not success:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, f"Gagal update password di sistem hotspot: {msg}")

    try:
        user.mikrotik_password = new_password
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menyimpan password baru.")

    context = {"full_name": user.full_name, "username": mikrotik_username, "password": new_password}
    message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
    send_whatsapp_message(user.phone_number, message_body)

    return jsonify({"message": "Password hotspot berhasil direset dan dikirim via WhatsApp."}), HTTPStatus.OK

@profile_bp.route('/me/login-history', methods=['GET'])
@token_required
def get_my_login_history(current_user_id):
    try:
        limit = min(max(int(request.args.get('limit', '7')), 1), 20)
        login_records = db.session.query(UserLoginHistory)\
            .filter(UserLoginHistory.user_id == current_user_id)\
            .order_by(UserLoginHistory.login_time.desc())\
            .limit(limit).all()
            
        history_data = [
            {
                "login_time": r.login_time.isoformat() if r.login_time else None, 
                "ip_address": r.ip_address, 
                "user_agent_string": r.user_agent_string
            } for r in login_records
        ]
        
        return jsonify(history_data), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error di get_my_login_history: {e}", exc_info=True)
        return jsonify({"message": f"Gagal mengambil riwayat: {e}"}), HTTPStatus.INTERNAL_SERVER_ERROR