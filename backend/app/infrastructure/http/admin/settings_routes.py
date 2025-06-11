# backend/app/infrastructure/http/admin/settings_routes.py
# Blueprint untuk rute-rute admin terkait pengaturan aplikasi.

from flask import Blueprint, jsonify, request, current_app
from http import HTTPStatus
from pydantic import ValidationError, BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting, User # User diperlukan untuk decorator admin_required
from app.infrastructure.http.decorators import super_admin_required
from app.services import settings_service

settings_management_bp = Blueprint('settings_management_api', __name__)

# --- Skema Pydantic untuk Pengaturan ---
class SettingSchema(BaseModel):
    setting_key: str = Field(..., description="Kunci unik pengaturan")
    setting_value: Optional[str] = Field(None, description="Nilai pengaturan")
    description: Optional[str] = Field(None, description="Deskripsi pengaturan")
    is_encrypted: bool = Field(False, description="Apakah nilai terenkripsi")

    model_config = ConfigDict(from_attributes=True) # Perbaikan: Gunakan ConfigDict

class SettingsUpdateSchema(BaseModel):
    settings: List[SettingSchema] = Field(..., description="Daftar pengaturan untuk diperbarui")

# --- Endpoints Pengaturan Aplikasi ---
@settings_management_bp.route('/settings', methods=['GET'])
@super_admin_required
def get_application_settings(current_admin: User):
    """Retrieve application settings."""
    try:
        settings_query = db.select(ApplicationSetting).order_by(ApplicationSetting.setting_key)
        settings = db.session.scalars(settings_query).all()
        response_data = [SettingSchema.from_orm(s).model_dump() for s in settings]
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve application settings: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while loading settings."}), HTTPStatus.INTERNAL_SERVER_ERROR

@settings_management_bp.route('/settings', methods=['PUT'])
@super_admin_required
def update_application_settings(current_admin: User):
    """Update application settings."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body cannot be empty."}), HTTPStatus.BAD_REQUEST
    try:
        validated_data = SettingsUpdateSchema.model_validate(json_data)
        settings_service.update_settings(validated_data.settings)
        db.session.commit()
        return jsonify({"message": "Settings updated successfully."}), HTTPStatus.OK
    except ValidationError as e:
        db.session.rollback()
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update settings by {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while saving settings."}), HTTPStatus.INTERNAL_SERVER_ERROR