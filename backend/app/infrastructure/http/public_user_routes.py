# backend/app/infrastructure/http/public_user_routes.py
# Berisi endpoint publik yang berhubungan dengan pengguna, tidak memerlukan autentikasi.

from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus

from app.extensions import db
from app.infrastructure.db.models import User

# --- PERBAIKAN IMPORT PATH ---
# Impor skema dari direktori yang sama (http), lalu ke subdirektori schemas
from .schemas.user_schemas import PhoneCheckRequest, PhoneCheckResponse, WhatsappValidationRequest
# -----------------------------

# --- DEFINISI BLUEPRINT ---
public_user_bp = Blueprint('public_user_api', __name__, url_prefix='/api/users')


# --- ENDPOINTS ---
@public_user_bp.route('/check-or-register', methods=['POST'])
def check_or_register_phone():
    current_app.logger.info("POST /api/users/check-or-register endpoint requested.")
    try:
        json_data = request.get_json(silent=True)
        if not json_data:
             current_app.logger.warning("[Check Phone] Request body is empty or not JSON.")
             return jsonify({"success": False, "message": "Request body tidak boleh kosong dan harus JSON."}), HTTPStatus.BAD_REQUEST
        req_data = PhoneCheckRequest.model_validate(json_data)
        phone_number = req_data.phone_number
        full_name = req_data.full_name
        current_app.logger.debug(f"[Check Phone] Request validated for: {phone_number}, Name: {full_name}")
    except ValidationError as e:
        current_app.logger.warning(f"[Check Phone] Invalid payload: {e.errors()}")
        return jsonify({"success": False, "message": "Data input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
         current_app.logger.warning(f"[Check Phone] Failed to parse request JSON: {e}", exc_info=True)
         return jsonify({"success": False, "message": "Format request tidak valid."}), HTTPStatus.BAD_REQUEST

    try:
        user = db.session.execute(select(User).filter_by(phone_number=phone_number)).scalar_one_or_none()

        if not user:
            current_app.logger.info(f"[Check Phone] Nomor {phone_number} belum terdaftar.")
            return jsonify(PhoneCheckResponse(user_exists=False, message="Nomor telepon belum terdaftar.").model_dump()), HTTPStatus.OK
        else:
            current_app.logger.info(f"[Check Phone] Pengguna ditemukan untuk nomor {phone_number} (ID: {user.id})")
            if not user.full_name and full_name:
                 try:
                      user.full_name = full_name
                      db.session.commit()
                      current_app.logger.info(f"[Check Phone] Nama pengguna {user.id} diupdate menjadi: {full_name}")
                 except SQLAlchemyError as e_update:
                      db.session.rollback()
                      current_app.logger.error(f"[Check Phone] Gagal update nama untuk user {user.id}: {e_update}", exc_info=True)
            return jsonify(PhoneCheckResponse(user_exists=True, user_id=user.id).model_dump()), HTTPStatus.OK

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"[Check Phone] Error database untuk nomor {phone_number}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal proses database (check-or-register)."}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        if db.session.is_active: db.session.rollback()
        current_app.logger.error(f"[Check Phone] Error tidak terduga untuk nomor {phone_number}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Kesalahan internal server (check-or-register)."}), HTTPStatus.INTERNAL_SERVER_ERROR

@public_user_bp.route('/validate-whatsapp', methods=['POST'])
def validate_whatsapp_number():
    """
    [SEMPURNA] Endpoint untuk validasi real-time yang melakukan 2 hal:
    1. Mengecek apakah nomor valid dan terdaftar di WhatsApp (via Fonnte).
    2. Mengecek apakah nomor tersebut SUDAH TERDAFTAR di database pengguna.
    """
    current_app.logger.info("POST /api/users/validate-whatsapp (v2) endpoint requested.")
    
    try:
        json_data = request.get_json()
        if not json_data:
            return jsonify({"isValid": False, "message": "Request body harus JSON."}), HTTPStatus.BAD_REQUEST
        
        req_data = WhatsappValidationRequest.model_validate(json_data)
        phone_number_e164 = req_data.phone_number 
    except ValidationError as e:
        error_detail = e.errors()[0]
        error_message = error_detail.get('msg', 'Input tidak valid.')
        return jsonify({"isValid": False, "message": error_message}), HTTPStatus.UNPROCESSABLE_ENTITY

    # --- LANGKAH 1: Cek apakah nomor sudah ada di database ---
    user_exists = db.session.scalar(select(User.id).filter_by(phone_number=phone_number_e164))
    if user_exists:
        current_app.logger.warning(f"[Validate WA] Nomor {phone_number_e164} sudah terdaftar di database.")
        return jsonify({"isValid": False, "message": "Nomor telepon ini sudah terdaftar."}), HTTPStatus.OK

    # --- LANGKAH 2: Jika belum ada, baru cek ke Fonnte ---
    fonnte_token = current_app.config.get('WHATSAPP_API_KEY')
    if not fonnte_token:
        current_app.logger.error("[Validate WA] WHATSAPP_API_KEY tidak diatur.")
        return jsonify({"isValid": False, "message": "Layanan validasi tidak terkonfigurasi."}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    target_number = phone_number_e164.lstrip('+')
    try:
        response = requests.post(
            'https://api.fonnte.com/validate',
            headers={'Authorization': fonnte_token},
            data={'target': target_number}
        )
        response.raise_for_status()
        fonnte_data = response.json()
        
        if fonnte_data.get('status') is True:
            if target_number in fonnte_data.get('registered', []):
                return jsonify({"isValid": True}), HTTPStatus.OK
            else:
                return jsonify({"isValid": False, "message": "Nomor tidak aktif di WhatsApp."}), HTTPStatus.OK
        else:
            reason = fonnte_data.get('reason', 'alasan tidak diketahui')
            return jsonify({"isValid": False, "message": f"Validasi gagal: {reason}"}), HTTPStatus.BAD_REQUEST

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"[Validate WA] Gagal menghubungi Fonnte API: {e}", exc_info=True)
        return jsonify({"isValid": False, "message": "Tidak dapat menghubungi layanan validasi."}), HTTPStatus.SERVICE_UNAVAILABLE
    except Exception as e:
        current_app.logger.error(f"[Validate WA] Terjadi error tidak terduga: {e}", exc_info=True)
        return jsonify({"isValid": False, "message": "Terjadi kesalahan internal saat validasi."}), HTTPStatus.INTERNAL_SERVER_ERROR