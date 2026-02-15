# backend/app/infrastructure/http/admin/user_management_routes.py
import uuid
from datetime import datetime, timezone as dt_timezone
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select
from http import HTTPStatus
from pydantic import ValidationError

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, UserBlok, UserKamar, ApprovalStatus
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.http.schemas.user_schemas import (
    UserResponseSchema,
    AdminSelfProfileUpdateRequestSchema,
)
from app.utils.formatters import get_phone_number_variations


# [FIX] Menambahkan kembali impor yang hilang untuk endpoint /mikrotik-status
from app.utils.formatters import format_to_local_phone
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details

from app.services import settings_service
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
    if not data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
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
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    data = request.get_json()
    if not data:
        return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
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
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
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
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
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
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
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
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_profile_service.generate_user_admin_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.FORBIDDEN
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/me', methods=['PUT'])
@admin_required
def update_my_profile(current_admin: User):
    if not request.is_json:
        return jsonify({"message": "Request body must be JSON."}), HTTPStatus.BAD_REQUEST

    try:
        update_data = AdminSelfProfileUpdateRequestSchema.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"message": "Invalid input.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    try:
        if update_data.phone_number and update_data.phone_number != current_admin.phone_number:
            variations = get_phone_number_variations(update_data.phone_number)
            existing_user = db.session.execute(
                select(User).where(User.phone_number.in_(variations), User.id != current_admin.id)
            ).scalar_one_or_none()
            if existing_user:
                return jsonify({"message": "Nomor telepon sudah digunakan."}), HTTPStatus.CONFLICT

            current_admin.phone_number = update_data.phone_number

        current_admin.full_name = update_data.full_name
        db.session.commit()
        db.session.refresh(current_admin)
        return jsonify(UserResponseSchema.from_orm(current_admin).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating admin profile {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR
    
@user_management_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    try:
        page = request.args.get('page', 1, type=int)
        per_page_raw = request.args.get('itemsPerPage', 10, type=int)
        if per_page_raw == -1:
            per_page = None
        else:
            per_page = min(max(int(per_page_raw or 10), 1), 100)
        search_query, role_filter = request.args.get('search', ''), request.args.get('role')
        sort_by, sort_order = request.args.get('sortBy', 'created_at'), request.args.get('sortOrder', 'desc')
        
        query = select(User)
        if not current_admin.is_super_admin_role:
            query = query.where(User.role != UserRole.SUPER_ADMIN)
        if role_filter:
            try:
                query = query.where(User.role == UserRole[role_filter.upper()])
            except KeyError:
                return jsonify({"message": "Role filter tidak valid."}), HTTPStatus.BAD_REQUEST
        if search_query:
            query = query.where(or_(User.full_name.ilike(f"%{search_query}%"), User.phone_number.in_(get_phone_number_variations(search_query))))
        
        sort_col = getattr(User, sort_by, User.created_at)
        query = query.order_by(sort_col.desc() if sort_order == 'desc' else sort_col.asc())

        total = db.session.scalar(select(func.count()).select_from(query.subquery()))

        if per_page is None:
            users = db.session.scalars(query).all()
        else:
            users = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()
        
        return jsonify({"items": [UserResponseSchema.from_orm(u).model_dump() for u in users], "totalItems": total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user list: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route('/users/inactive-cleanup-preview', methods=['GET'])
@admin_required
def get_inactive_cleanup_preview(current_admin: User):
    try:
        now_utc = datetime.now(dt_timezone.utc)
        deactivate_days = settings_service.get_setting_as_int('INACTIVE_DEACTIVATE_DAYS', 45)
        delete_days = settings_service.get_setting_as_int('INACTIVE_DELETE_DAYS', 90)
        limit = min(request.args.get('limit', 50, type=int), 200)

        users = db.session.scalars(
            select(User).where(
                User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        ).all()

        deactivate_candidates = []
        delete_candidates = []

        for user in users:
            last_activity = user.last_login_at or user.created_at
            if not last_activity:
                continue

            days_inactive = (now_utc - last_activity).days
            payload = {
                "id": str(user.id),
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "role": user.role.value,
                "is_active": user.is_active,
                "last_activity_at": last_activity.isoformat(),
                "days_inactive": days_inactive,
            }

            if days_inactive >= delete_days:
                delete_candidates.append(payload)
            elif user.is_active and days_inactive >= deactivate_days:
                deactivate_candidates.append(payload)

        delete_candidates.sort(key=lambda item: item["days_inactive"], reverse=True)
        deactivate_candidates.sort(key=lambda item: item["days_inactive"], reverse=True)

        return jsonify({
            "thresholds": {
                "deactivate_days": deactivate_days,
                "delete_days": delete_days,
            },
            "summary": {
                "deactivate_candidates": len(deactivate_candidates),
                "delete_candidates": len(delete_candidates),
            },
            "items": {
                "deactivate_candidates": deactivate_candidates[:limit],
                "delete_candidates": delete_candidates[:limit],
            },
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error preview cleanup pengguna tidak aktif: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat preview cleanup pengguna tidak aktif."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/form-options/alamat', methods=['GET'])
@admin_required
def get_alamat_form_options(current_admin: User):
    return jsonify({
        "bloks": [e.value for e in UserBlok],
        "kamars": [e.value.replace('Kamar_', '') for e in UserKamar]
    }), HTTPStatus.OK

@user_management_bp.route('/form-options/mikrotik', methods=['GET'])
@admin_required
def get_mikrotik_form_options(current_admin: User):
    try:
        default_server = (
            settings_service.get_setting('MIKROTIK_DEFAULT_SERVER', None)
            or settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'srv-user')
        )
        default_server_komandan = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'srv-komandan')
        active_profile = (
            settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', None)
            or settings_service.get_setting('MIKROTIK_USER_PROFILE', 'user')
            or settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        )
        defaults = {
            "server_user": default_server,
            "server_komandan": default_server_komandan or default_server,
            "server_admin": default_server,
            "server_support": default_server,
            "profile_user": active_profile,
            "profile_komandan": active_profile,
            "profile_default": settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default'),
            "profile_active": active_profile,
            "profile_fup": settings_service.get_setting('MIKROTIK_FUP_PROFILE', 'fup'),
            "profile_habis": settings_service.get_setting('MIKROTIK_HABIS_PROFILE', 'habis'),
            "profile_unlimited": settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited'),
            "profile_expired": settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired'),
            "profile_inactive": settings_service.get_setting('MIKROTIK_INACTIVE_PROFILE', 'inactive'),
        }

        server_candidates = [
            defaults.get("server_user"),
            defaults.get("server_komandan"),
            defaults.get("server_admin"),
            defaults.get("server_support"),
        ]
        profile_candidates = [
            defaults.get("profile_user"),
            defaults.get("profile_komandan"),
            defaults.get("profile_default"),
            defaults.get("profile_active"),
            defaults.get("profile_fup"),
            defaults.get("profile_habis"),
            defaults.get("profile_unlimited"),
            defaults.get("profile_expired"),
            defaults.get("profile_inactive"),
        ]

        def _unique(values):
            seen = set()
            result = []
            for value in values:
                if not value:
                    continue
                if value in seen:
                    continue
                seen.add(value)
                result.append(value)
            return result

        return jsonify({
            "serverOptions": _unique(server_candidates),
            "profileOptions": _unique(profile_candidates),
            "defaults": defaults,
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Gagal memuat opsi Mikrotik: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat opsi Mikrotik."}), HTTPStatus.INTERNAL_SERVER_ERROR

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

        operation_result = _handle_mikrotik_operation(
            get_hotspot_user_details,
            username=mikrotik_username,
        )

        success = False
        details = None
        mikrotik_message = ""

        if isinstance(operation_result, tuple):
            if len(operation_result) >= 3:
                success, details, mikrotik_message = operation_result[0], operation_result[1], operation_result[2]
            elif len(operation_result) == 2:
                success, details = operation_result
                mikrotik_message = str(details) if success is False else "Sukses"
            elif len(operation_result) == 1:
                success = bool(operation_result[0])
                mikrotik_message = "Hasil operasi Mikrotik tidak lengkap."

        if not success:
            current_app.logger.warning(
                "Live check Mikrotik tidak tersedia untuk user %s: %s",
                user_id,
                mikrotik_message,
            )
            return jsonify({
                "user_id": str(user.id),
                "exists_on_mikrotik": bool(user.mikrotik_user_exists),
                "details": None,
                "live_available": False,
                "message": "Live check MikroTik tidak tersedia. Menampilkan data lokal database.",
                "reason": mikrotik_message,
            }), HTTPStatus.OK

        user_exists = details is not None

        if user.mikrotik_user_exists != user_exists:
            user.mikrotik_user_exists = user_exists
            db.session.commit()

        return jsonify({
            "user_id": str(user.id),
            "exists_on_mikrotik": user_exists,
            "details": details,
            "live_available": True,
            "message": "Data live MikroTik berhasil dimuat." if user_exists else "Pengguna tidak ditemukan di MikroTik.",
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal tak terduga pada server."}), HTTPStatus.INTERNAL_SERVER_ERROR