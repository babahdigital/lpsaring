# backend/app/infrastructure/http/user/profile_routes.py
# Berisi endpoint yang berhubungan dengan manajemen profil dan keamanan pengguna.

from flask import Blueprint, request, jsonify, abort, current_app
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
import uuid
from typing import Optional
from datetime import date, datetime, timezone as dt_timezone
from http import HTTPStatus

from app.extensions import db
from app.services import settings_service
from app.services.notification_service import get_notification_message

# Impor model
from app.infrastructure.db.models import (
    User, UserRole, ApprovalStatus, UserLoginHistory
)

# --- PERBAIKAN IMPORT PATH ---
# Impor skema dari direktori induk (http)
from ..schemas.user_schemas import (
    UserProfileResponseSchema,
    UserProfileUpdateRequestSchema
)

# Impor decorator dari direktori induk (http)
from ..decorators import token_required

# Impor helper dari direktori induk (http)
from ..transactions_routes import generate_random_password
# -----------------------------

# Impor helper dari path absolut (sudah benar)
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    activate_or_update_hotspot_user,
    format_to_local_phone
)
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message


# --- DEFINISI BLUEPRINT ---
profile_bp = Blueprint('user_profile_api', __name__, url_prefix='/api/users')

# --- API Endpoint Profil Pengguna (GET & PUT) ---
@profile_bp.route('/me/profile', methods=['GET', 'PUT'])
@token_required
def handle_my_profile(current_user_id):
    user_uuid = current_user_id
    user = db.session.get(User, user_uuid)
    if not user:
        current_app.logger.warning(f"[Profile] User {user_uuid} dari token tidak ditemukan.")
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        current_app.logger.warning(f"[Profile GET/PUT] User {user_uuid} tidak aktif/approved. Status: active={user.is_active}, approval={user.approval_status.value if user.approval_status else 'N/A'}")
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui untuk melihat/mengubah profil.")

    # GET Method
    if request.method == 'GET':
        current_app.logger.info(f"GET /api/users/me/profile by user ID: {user_uuid}")
        try:
            profile_data = UserProfileResponseSchema.model_validate(user)
            if profile_data.kamar and isinstance(profile_data.kamar, str) and profile_data.kamar.startswith("Kamar_") and profile_data.kamar[6:].isdigit():
                profile_data.kamar = profile_data.kamar[6:]
            return jsonify(profile_data.model_dump(mode='json')), HTTPStatus.OK
        except Exception as e:
            current_app.logger.error(f"[Profile GET] Error serialisasi profil user {user_uuid}: {e}", exc_info=True)
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Error mengambil data profil: {str(e)}")

    # PUT Method
    elif request.method == 'PUT':
        current_app.logger.info(f"PUT /api/users/me/profile by user ID: {user_uuid}")
        if user.role != UserRole.USER:
            current_app.logger.warning(f"[Profile PUT] User {user_uuid} (role: {user.role.value}) mencoba update profil via endpoint /me/profile. Akses ditolak.")
            abort(HTTPStatus.FORBIDDEN, description="Endpoint ini hanya untuk pengguna biasa (USER). Admin harus menggunakan endpoint/tools lain.")

        json_data = request.get_json(silent=True)
        if not json_data:
            return jsonify({"success": False, "message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

        try:
            update_data = UserProfileUpdateRequestSchema.model_validate(json_data)
            user_updated = False

            if update_data.full_name is not None and user.full_name != update_data.full_name:
                user.full_name = update_data.full_name
                user_updated = True

            new_blok_val_for_db = update_data.blok.value if update_data.blok else None
            new_kamar_val_for_db = update_data.kamar.value if update_data.kamar else None

            if user.blok != new_blok_val_for_db:
                user.blok = new_blok_val_for_db
                user_updated = True
            
            if user.kamar != new_kamar_val_for_db:
                user.kamar = new_kamar_val_for_db
                user_updated = True

            if user_updated:
                db.session.commit()
                current_app.logger.info(f"[Profile PUT] Profil user {user_uuid} berhasil diupdate.")
                resp_data = UserProfileResponseSchema.model_validate(user)
                if resp_data.kamar and isinstance(resp_data.kamar, str) and resp_data.kamar.startswith("Kamar_") and resp_data.kamar[6:].isdigit():
                    resp_data.kamar = resp_data.kamar[6:]
                return jsonify(resp_data.model_dump(mode='json')), HTTPStatus.OK
            else:
                current_app.logger.info(f"[Profile PUT] Tidak ada perubahan data untuk user {user_uuid}.")
                resp_data = UserProfileResponseSchema.model_validate(user)
                if resp_data.kamar and isinstance(resp_data.kamar, str) and resp_data.kamar.startswith("Kamar_") and resp_data.kamar[6:].isdigit():
                    resp_data.kamar = resp_data.kamar[6:]
                return jsonify(resp_data.model_dump(mode='json')), HTTPStatus.OK

        except ValidationError as e:
            current_app.logger.warning(f"[Profile PUT] Validasi Pydantic gagal untuk user {user_uuid}: {e.errors()}")
            return jsonify({"success": False, "message": "Data input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
        except SQLAlchemyError as e_sql:
            if db.session.is_active: db.session.rollback()
            current_app.logger.error(f"[Profile PUT] Error database (sebelum commit) user {user_uuid}: {e_sql}", exc_info=True)
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan database saat memproses update profil.")
        except Exception as e:
            if db.session.is_active: db.session.rollback()
            current_app.logger.error(f"[Profile PUT] Error tidak terduga user {user_uuid}: {e}", exc_info=True)
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan internal saat update profil.")

    return abort(HTTPStatus.METHOD_NOT_ALLOWED)

# --- API Endpoint Reset Password Hotspot ---
@profile_bp.route('/me/reset-hotspot-password', methods=['POST'])
@token_required
def reset_my_hotspot_password(current_user_id):
    current_app.logger.info(f"POST /api/users/me/reset-hotspot-password requested by user ID: {current_user_id}")
    user_uuid = current_user_id
    user = db.session.get(User, user_uuid)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui untuk mereset password hotspot.")

    if user.role != UserRole.USER:
        abort(HTTPStatus.FORBIDDEN, description="Fitur ini hanya untuk pengguna biasa.")

    mikrotik_username = format_to_local_phone(user.phone_number)
    if not mikrotik_username:
        return jsonify({"success": False, "message": "Data pengguna tidak lengkap (nomor telepon tidak ada)."}), HTTPStatus.INTERNAL_SERVER_ERROR

    new_password_numeric = generate_random_password(length=6)
    current_app.logger.info(f"[Reset Pass] Generate password 6 digit numerik baru '{new_password_numeric}' untuk user {mikrotik_username} (ID: {user_uuid}).")

    mt_update_success = False
    mt_update_message = "Mikrotik client not available."
    try:
        with get_mikrotik_connection() as api_conn:
            if not api_conn:
                mt_update_message = "Gagal koneksi Mikrotik."
            else:
                mikrotik_profile_name = current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default')
                
                limit_bytes_total = user.total_quota_purchased_mb * 1024 * 1024 if user.total_quota_purchased_mb is not None else 0
                session_timeout_seconds = 0
                if user.quota_expiry_date:
                    time_remaining = (user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()
                    session_timeout_seconds = max(0, int(time_remaining))

                kamar_val_for_comment = user.kamar if user.kamar else 'N/A'
                blok_val_for_comment = user.blok if user.blok else 'N/A'
                comment_for_mikrotik = f"Password Reset: {user.full_name or 'N/A'} | Blk {blok_val_for_comment} Km {kamar_val_for_comment} | ID:{str(user.id)[:8]}"

                mt_update_success, mt_update_message = activate_or_update_hotspot_user(
                    api_connection=api_conn,
                    user_mikrotik_username=mikrotik_username,
                    mikrotik_profile_name=mikrotik_profile_name,
                    hotspot_password=new_password_numeric,
                    comment=comment_for_mikrotik,
                    limit_bytes_total=limit_bytes_total,
                    session_timeout_seconds=session_timeout_seconds,
                    force_update_profile=True
                )
    except Exception as e_mt:
        mt_update_message = f"Error koneksi/update Mikrotik: {str(e_mt)}"
        current_app.logger.error(f"[Reset Pass] Error Mikrotik untuk user {mikrotik_username}: {e_mt}", exc_info=True)

    if not mt_update_success:
         return jsonify({"success": False, "message": f"Gagal update password di sistem hotspot: {mt_update_message}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    try:
        user.mikrotik_password = new_password_numeric
        db.session.commit()
    except SQLAlchemyError as e_db:
        if db.session.is_active: db.session.rollback()
        return jsonify({"success": False, "message": "Password hotspot telah diperbarui di sistem, tapi gagal sinkronisasi ke akun Anda."}), HTTPStatus.INTERNAL_SERVER_ERROR

    notification_success = False
    if user.phone_number:
        try:
            if settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
                username_for_wa_display = format_to_local_phone(mikrotik_username) or mikrotik_username
                context = {
                    "full_name": user.full_name,
                    "username": username_for_wa_display,
                    "password": new_password_numeric
                }
                message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
                notification_success = send_whatsapp_message(user.phone_number, message_body)
        except Exception as e_wa:
            current_app.logger.error(f"[Reset Pass] Error mengirim notifikasi WhatsApp ke {user.phone_number}: {e_wa}", exc_info=True)

    final_message = "Password hotspot berhasil direset."
    if user.phone_number and notification_success:
        final_message += " Password baru telah dikirim via WhatsApp."
    elif user.phone_number and not notification_success:
        final_message += f" Namun, gagal mengirim notifikasi WhatsApp. Password baru Anda adalah: {new_password_numeric}"
    else:
        final_message += f" Password baru Anda adalah: {new_password_numeric}"

    return jsonify({"success": True, "message": final_message, "new_password_for_testing": new_password_numeric if current_app.debug else None}), HTTPStatus.OK
    
# --- API Endpoint: GET Riwayat Login Pengguna ---
@profile_bp.route('/me/login-history', methods=['GET'])
@token_required
def get_my_login_history(current_user_id):
    current_app.logger.info(f"GET /api/users/me/login-history requested by user ID: {current_user_id}")
    user_uuid = current_user_id
    try:
        limit_str = request.args.get('limit', '7')
        try:
            limit = int(limit_str)
        except ValueError:
            current_app.logger.warning(f"[LoginHistory] Invalid limit parameter '{limit_str}'. Defaulting to 7.")
            limit = 7
            
        limit = min(max(limit, 1), 20)
        current_app.logger.debug(f"[LoginHistory] Fetching last {limit} login records for user {user_uuid}.")

        login_records = db.session.query(UserLoginHistory)\
            .filter(UserLoginHistory.user_id == user_uuid)\
            .order_by(UserLoginHistory.login_time.desc())\
            .limit(limit)\
            .all()
            
        current_app.logger.debug(f"[LoginHistory] Found {len(login_records)} login records for user {user_uuid}.")
        history_data = []
        for record in login_records:
            history_data.append({
                "login_time": record.login_time.isoformat() if record.login_time else None,
                "ip_address": record.ip_address,
                "user_agent_string": record.user_agent_string
            })
        return jsonify({"success": True, "history": history_data}), HTTPStatus.OK

    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[LoginHistory] DB error for user {user_uuid}: {e_sql}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal mengambil riwayat akses dari database."}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        current_app.logger.error(f"[LoginHistory] Error proses untuk user {user_uuid}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Terjadi kesalahan saat memproses riwayat akses."}), HTTPStatus.INTERNAL_SERVER_ERROR