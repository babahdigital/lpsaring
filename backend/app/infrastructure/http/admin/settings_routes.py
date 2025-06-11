# backend/app/infrastructure/http/admin/settings_routes.py
# VERSI FINAL: Disesuaikan agar sinkron dengan Frontend dan memiliki validasi yang kuat.

from flask import Blueprint, jsonify, request, current_app
from http import HTTPStatus
from pydantic import ValidationError, BaseModel, Field, ConfigDict
from typing import Optional, Dict

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting, User
from app.infrastructure.http.decorators import super_admin_required
from app.services import settings_service

# Blueprint ini sudah didaftarkan dengan prefix /api/admin di __init__.py
settings_management_bp = Blueprint('settings_management_api', __name__)

# --- Skema Pydantic untuk Pengaturan ---

class SettingSchema(BaseModel):
    """Skema untuk menampilkan data pengaturan individual."""
    setting_key: str = Field(..., description="Kunci unik pengaturan")
    setting_value: Optional[str] = Field(None, description="Nilai pengaturan")
    description: Optional[str] = Field(None, description="Deskripsi pengaturan")
    is_encrypted: bool = Field(False, description="Apakah nilai terenkripsi")
    model_config = ConfigDict(from_attributes=True)

class SettingsUpdateSchema(BaseModel):
    """
    PERBAIKAN: Skema disesuaikan untuk menerima dictionary, bukan list.
    Ini sesuai dengan payload yang dikirim dari frontend: { "settings": { "key": "value", ... } }
    """
    settings: Dict[str, str] = Field(..., description="Dictionary pengaturan key-value untuk diperbarui")

# --- Endpoints Pengaturan Aplikasi ---

@settings_management_bp.route('/settings', methods=['GET'])
@super_admin_required
def get_application_settings(current_admin: User):
    """Mengambil semua pengaturan aplikasi untuk admin."""
    try:
        settings_query = db.select(ApplicationSetting).order_by(ApplicationSetting.setting_key)
        settings = db.session.scalars(settings_query).all()
        response_data = [SettingSchema.model_validate(s).model_dump() for s in settings]
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Gagal mengambil pengaturan aplikasi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat memuat pengaturan."}), HTTPStatus.INTERNAL_SERVER_ERROR

@settings_management_bp.route('/settings', methods=['PUT'])
@super_admin_required
def update_application_settings(current_admin: User):
    """Memperbarui pengaturan aplikasi dengan validasi yang kuat."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
    
    try:
        # Validasi struktur payload utama
        validated_data = SettingsUpdateSchema.model_validate(json_data)
        settings = validated_data.settings
        
        # PERBAIKAN: Logika validasi bisnis ditambahkan di sini
        errors = []
        
        # Validasi Maintenance Mode
        if 'MAINTENANCE_MODE_ACTIVE' in settings:
            is_active_str = settings['MAINTENANCE_MODE_ACTIVE']
            if is_active_str not in ['True', 'False']:
                errors.append({"field": "MAINTENANCE_MODE_ACTIVE", "message": "Nilai harus 'True' atau 'False'"})
            
            # Jika mode maintenance aktif, pesannya wajib diisi
            elif is_active_str == 'True':
                if not settings.get('MAINTENANCE_MODE_MESSAGE'):
                    errors.append({"field": "MAINTENANCE_MODE_MESSAGE", "message": "Pesan maintenance wajib diisi jika mode diaktifkan"})

        # Validasi Notifikasi WhatsApp
        if 'ENABLE_WHATSAPP_NOTIFICATIONS' in settings:
            is_enabled_str = settings['ENABLE_WHATSAPP_NOTIFICATIONS']
            if is_enabled_str not in ['True', 'False']:
                errors.append({"field": "ENABLE_WHATSAPP_NOTIFICATIONS", "message": "Nilai harus 'True' atau 'False'"})

            # Jika notifikasi WA aktif, API Key wajib diisi
            elif is_enabled_str == 'True':
                if not settings.get('WHATSAPP_API_KEY'):
                    errors.append({"field": "WHATSAPP_API_KEY", "message": "API Key WhatsApp wajib diisi jika notifikasi diaktifkan"})
        
        # Jika ditemukan error validasi, kembalikan response 422
        if errors:
            return jsonify({"errors": errors}), HTTPStatus.UNPROCESSABLE_ENTITY
            
        # Jika semua validasi lolos, lanjutkan proses update
        settings_service.update_settings_from_dict(settings)
        db.session.commit()
        
        return jsonify({"message": "Pengaturan berhasil diperbarui."}), HTTPStatus.OK
        
    except ValidationError as e:
        # Menangkap error validasi dari Pydantic jika struktur dasar salah
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui pengaturan oleh {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat menyimpan pengaturan."}), HTTPStatus.INTERNAL_SERVER_ERROR