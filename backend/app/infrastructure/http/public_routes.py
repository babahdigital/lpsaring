# backend/app/infrastructure/http/public_routes.py

from flask import Blueprint, jsonify, current_app
from http import HTTPStatus
from sqlalchemy import select, or_

# [PERBAIKAN 1] Impor 'limiter' dari ekstensi
from app.extensions import db, limiter
from app.infrastructure.db.models import ApplicationSetting

public_bp = Blueprint('public_api', __name__)

@public_bp.route('/public', methods=['GET'])
# Decorator rate limit
@limiter.limit("60 per minute;20 per 10 seconds")
def get_public_settings():
    """
    Menyediakan semua pengaturan publik (tidak terenkripsi) yang dibutuhkan
    oleh frontend untuk inisialisasi dalam format OBJECT tunggal.
    Contoh output: {"APP_NAME": "Portal Hotspot", "THEME": "light"}
    """
    try:
        # [PERBAIKAN UTAMA] Query diubah agar lebih toleran.
        # Ia akan mengambil semua pengaturan yang kolom `is_encrypted`-nya
        # BUKAN True. Ini secara efektif mencakup nilai False dan juga NULL (kosong).
        settings_query = select(ApplicationSetting).where(
            ApplicationSetting.is_encrypted.is_not(True)
        )
        
        settings_db = db.session.scalars(settings_query).all()

        # Ubah array hasil query menjadi sebuah object tunggal
        settings_map = {s.setting_key: s.setting_value for s in settings_db}

        # Kembalikan sebagai object JSON tunggal
        return jsonify(settings_map), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error fetching public settings: {e}", exc_info=True)
        # Jika terjadi error, kirim object kosong
        return jsonify({}), HTTPStatus.INTERNAL_SERVER_ERROR