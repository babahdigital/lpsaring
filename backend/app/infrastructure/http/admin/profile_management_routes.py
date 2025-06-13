# backend/app/infrastructure/http/admin/profile_management_routes.py
# Blueprint untuk rute-rute admin terkait manajemen profil teknis Mikrotik.

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError
from http import HTTPStatus
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from typing import Optional, List
import uuid

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import PackageProfile, Package, User
from app.infrastructure.http.decorators import super_admin_required

profile_management_bp = Blueprint('profile_management_api', __name__)

# --- Skema Pydantic untuk Profil ---
class ProfileSchema(BaseModel):
    id: uuid.UUID
    profile_name: str
    description: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ProfileCreateUpdateSchema(BaseModel):
    profile_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


# --- Rute CRUD untuk Profil (PackageProfile) ---

@profile_management_bp.route('/profiles', methods=['GET'])
@super_admin_required
def get_profiles_list(current_admin: User):
    """Mengambil daftar semua profil teknis dengan paginasi."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        
        query = db.select(PackageProfile).order_by(PackageProfile.profile_name.asc())
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            "items": [ProfileSchema.from_orm(p).model_dump() for p in pagination.items],
            "totalItems": pagination.total
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error retrieving profile list: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat daftar profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@profile_management_bp.route('/profiles', methods=['POST'])
@super_admin_required
def create_profile(current_admin: User):
    """Membuat profil teknis baru."""
    try:
        profile_data = ProfileCreateUpdateSchema.model_validate(request.get_json())
        
        new_profile = PackageProfile(
            profile_name=profile_data.profile_name,
            description=profile_data.description
        )
        db.session.add(new_profile)
        db.session.commit()
        
        return jsonify(ProfileSchema.from_orm(new_profile).model_dump()), HTTPStatus.CREATED
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": f"Nama profil '{request.get_json().get('profile_name')}' sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyimpan profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@profile_management_bp.route('/profiles/<uuid:profile_id>', methods=['PUT'])
@super_admin_required
def update_profile(current_admin: User, profile_id: uuid.UUID):
    """Memperbarui profil teknis yang ada."""
    profile = db.session.get(PackageProfile, profile_id)
    if not profile:
        return jsonify({"message": "Profil tidak ditemukan."}), HTTPStatus.NOT_FOUND

    # --- LOGIKA PROTEKSI UNTUK PROFIL 'default' ---
    if profile.profile_name.lower() == 'default':
        return jsonify({"message": "Profil 'default' adalah profil sistem dan tidak dapat diubah."}), HTTPStatus.FORBIDDEN

    try:
        profile_data = ProfileCreateUpdateSchema.model_validate(request.get_json())
        
        profile.profile_name = profile_data.profile_name
        profile.description = profile_data.description
        
        db.session.commit()
        return jsonify(ProfileSchema.from_orm(profile).model_dump()), HTTPStatus.OK
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": f"Nama profil '{request.get_json().get('profile_name')}' sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal memperbarui profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@profile_management_bp.route('/profiles/<uuid:profile_id>', methods=['DELETE'])
@super_admin_required
def delete_profile(current_admin: User, profile_id: uuid.UUID):
    """Menghapus profil teknis."""
    profile = db.session.get(PackageProfile, profile_id)
    if not profile:
        return jsonify({"message": "Profil tidak ditemukan."}), HTTPStatus.NOT_FOUND

    # --- LOGIKA PROTEKSI UNTUK PROFIL 'default' ---
    if profile.profile_name.lower() == 'default':
        return jsonify({"message": "Profil 'default' adalah profil sistem dan tidak dapat dihapus."}), HTTPStatus.FORBIDDEN

    # Periksa apakah profil sedang digunakan oleh paket apa pun
    package_using_profile = db.session.query(Package.id).filter_by(profile_id=profile_id).first()
    if package_using_profile:
        return jsonify({"message": "Profil tidak dapat dihapus karena masih digunakan oleh satu atau lebih paket jualan."}), HTTPStatus.CONFLICT

    try:
        db.session.delete(profile)
        db.session.commit()
        return jsonify({"message": "Profil berhasil dihapus."}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menghapus profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal menghapus profil."}), HTTPStatus.INTERNAL_SERVER_ERROR