# ========================================================================
# File: backend/app/infrastructure/http/public_routes.py
# Perbaikan: Mengubah format response menjadi Array agar sesuai dengan
# ekspektasi frontend (store/settings.ts) dan mengatasi error .reduce().
# ========================================================================
from flask import Blueprint, jsonify, current_app
from http import HTTPStatus
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting
from .schemas.settings_schemas import SettingSchema

public_bp = Blueprint('public_api', __name__, url_prefix='/api/settings')

@public_bp.route('/public', methods=['GET'])
def get_public_settings():
    """
    Menyediakan semua pengaturan publik (tidak terenkripsi) yang dibutuhkan
    oleh frontend untuk inisialisasi.
    Format output adalah Array of Objects, sesuai dengan tipe `SettingSchema[]`.
    """
    try:
        # Ambil semua pengaturan yang TIDAK dienkripsi dari database
        settings_query = select(ApplicationSetting).where(
            ApplicationSetting.is_encrypted == False
        )
        settings_db = db.session.scalars(settings_query).all()

        # Konversi hasil ke format yang diharapkan frontend
        # yaitu: [{setting_key: 'KEY_A', setting_value: 'VALUE_A'}, {setting_key: 'KEY_B', setting_value: 'VALUE_B'}]
        public_settings = [
            SettingSchema.model_validate(s).model_dump() for s in settings_db
        ]

        # Kembalikan sebagai array JSON
        return jsonify(public_settings), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error fetching public settings: {e}", exc_info=True)
        # Jika terjadi error, kirim array kosong agar frontend tidak crash
        return jsonify([]), HTTPStatus.INTERNAL_SERVER_ERROR