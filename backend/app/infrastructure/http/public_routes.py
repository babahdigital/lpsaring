# backend/app/infrastructure/http/public_routes.py
from flask import Blueprint, jsonify
from http import HTTPStatus
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting
from .schemas.settings_schemas import SettingSchema

public_bp = Blueprint('public_api', __name__, url_prefix='/api/settings')

@public_bp.route('/public', methods=['GET'])
def get_public_settings():
    """
    Menyediakan pengaturan yang aman untuk diakses publik.
    Saat ini hanya status maintenance.
    """
    try:
        public_keys = ['MAINTENANCE_MODE_ACTIVE', 'MAINTENANCE_MODE_MESSAGE']
        settings_query = select(ApplicationSetting).where(ApplicationSetting.setting_key.in_(public_keys))
        settings = db.session.scalars(settings_query).all()
        response_data = [SettingSchema.from_orm(s).model_dump() for s in settings]
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        # Jika terjadi error, anggap tidak maintenance demi keamanan
        return jsonify([]), HTTPStatus.OK