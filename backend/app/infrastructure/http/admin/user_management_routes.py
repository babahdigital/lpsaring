# backend/app/infrastructure/http/admin/user_management_routes.py
import uuid
import json
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select
from http import HTTPStatus

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserBlok, UserKamar, RequestType
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.http.schemas.user_schemas import UserResponseSchema
from app.utils.formatters import get_phone_number_variations
from datetime import datetime, timezone, timedelta # Tambahkan impor ini


# [FIX] Menambahkan kembali impor yang hilang untuk endpoint /mikrotik-status
from app.utils.formatters import format_to_local_phone
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details

from app.services.user_management import (
    user_approval,
    user_deletion,
    user_profile as user_profile_service
)

user_management_bp = Blueprint('user_management_api', __name__)

# --- SEMUA ROUTE LAINNYA DI ATAS INI TIDAK BERUBAH ---
# (create_user, update_user, approve_user, dll. tetap sama)

@user_management_bp.route('/users', methods=['POST'])
@admin_required
def create_user_by_admin(current_admin: User):
    data = request.get_json()
    if not data: return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
    try:
        success, message, new_user = user_profile_service.create_user_by_admin(current_admin, data)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(new_user)
        return jsonify(UserResponseSchema.from_orm(new_user).model_dump()), HTTPStatus.CREATED
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    data = request.get_json()
    if not data: return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
    try:
        success, message, updated_user = user_profile_service.update_user_by_admin_comprehensive(user, current_admin, data)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(updated_user)
        return jsonify(UserResponseSchema.from_orm(updated_user).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/approve', methods=['PATCH'])
@admin_required
def approve_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    try:
        success, message = user_approval.approve_user_account(user, current_admin)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(user)
        return jsonify({"message": message, "user": UserResponseSchema.from_orm(user).model_dump()}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/reject', methods=['POST'])
@admin_required
def reject_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_approval.reject_user_account(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: 
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND

    try:
        # [PERUBAHAN] Panggil fungsi baru yang lebih cerdas
        success, message = user_deletion.process_user_removal(user, current_admin)
        
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.FORBIDDEN
        
        db.session.commit()
        return jsonify({"message": message}), HTTPStatus.OK

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat memproses penghapusan user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/reset-hotspot-password', methods=['POST'])
@admin_required
def admin_reset_hotspot_password(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_profile_service.reset_user_hotspot_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    db.session.refresh(user)
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/<uuid:user_id>/generate-admin-password', methods=['POST'])
@admin_required
def generate_admin_password_for_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_profile_service.generate_user_admin_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.FORBIDDEN
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK
    
@user_management_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    try:
        page, per_page = request.args.get('page', 1, type=int), min(request.args.get('itemsPerPage', 10, type=int), 100)
        search_query, role_filter = request.args.get('search', ''), request.args.get('role')
        sort_by, sort_order = request.args.get('sortBy', 'created_at'), request.args.get('sortOrder', 'desc')
        
        query = select(User)
        if not current_admin.is_super_admin_role: query = query.where(User.role != UserRole.SUPER_ADMIN)
        if role_filter: query = query.where(User.role == UserRole[role_filter.upper()])
        if search_query: query = query.where(or_(User.full_name.ilike(f"%{search_query}%"), User.phone_number.in_(get_phone_number_variations(search_query))))
        
        sort_col = getattr(User, sort_by, User.created_at)
        query = query.order_by(sort_col.desc() if sort_order == 'desc' else sort_col.asc())

        total = db.session.scalar(select(func.count()).select_from(query.subquery()))
        users = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()
        
        return jsonify({"items": [UserResponseSchema.from_orm(u).model_dump() for u in users], "totalItems": total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user list: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/form-options/alamat', methods=['GET'])
@admin_required
def get_alamat_form_options(current_admin: User):
    return jsonify({
        "bloks": [e.value for e in UserBlok],
        "kamars": [e.value.replace('Kamar_', '') for e in UserKamar]
    }), HTTPStatus.OK

# ================================================================
# === [DIKEMBALIKAN] Logika Live Check ke MikroTik dengan Error Handling Lengkap ===
# ================================================================
@user_management_bp.route('/users/<uuid:user_id>/mikrotik-status', methods=['GET'])
@admin_required
def check_mikrotik_status(current_admin: User, user_id: uuid.UUID):
    """
    Mengecek status live seorang pengguna di Mikrotik dengan penanganan error yang aman.
    """
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"message": "Pengguna tidak ditemukan di database."}), HTTPStatus.NOT_FOUND

        mikrotik_username = format_to_local_phone(user.phone_number)
        if not mikrotik_username:
            return jsonify({
                "exists_on_mikrotik": False,
                "message": "Format nomor telepon pengguna tidak valid."
            }), HTTPStatus.OK

        success, details, message = _handle_mikrotik_operation(
            get_hotspot_user_details,
            username=mikrotik_username
        )

        if not success:
            return jsonify({"message": f"Gagal terhubung ke Mikrotik: {message}"}), HTTPStatus.SERVICE_UNAVAILABLE

        user_exists = details is not None

        if user.mikrotik_user_exists != user_exists:
            user.mikrotik_user_exists = user_exists
            db.session.commit()

        return jsonify({
            "user_id": str(user.id),
            "exists_on_mikrotik": user_exists,
            "details": details
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal tak terduga pada server."}), HTTPStatus.INTERNAL_SERVER_ERROR