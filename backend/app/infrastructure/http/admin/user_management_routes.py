# backend/app/infrastructure/http/admin/user_management_routes.py
# Blueprint untuk rute-rute admin terkait manajemen pengguna.

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select, cast, String as SQLAlchemyString
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone as dt_timezone, timedelta
from http import HTTPStatus
from pydantic import ValidationError
import uuid
import secrets
import string
import enum
from werkzeug.security import generate_password_hash

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, ApprovalStatus, UserBlok, UserKamar,
    PromoEvent, PromoEventType, PromoEventStatus
)
from app.infrastructure.http.decorators import admin_required, super_admin_required
from app.infrastructure.http.schemas.user_schemas import (
    UserResponseSchema, 
    UserCreateByAdminSchema,
    UserUpdateByAdminSchema,
    UserProfileUpdateRequestSchema
)
from app.utils.formatters import normalize_to_e164, format_to_local_phone, get_phone_number_variations
from app.services.notification_service import get_notification_message
from app.services import settings_service

try: from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message; WHATSAPP_AVAILABLE = True
except ImportError: WHATSAPP_AVAILABLE = False
try: from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection, delete_hotspot_user,
    activate_or_update_hotspot_user, set_hotspot_user_profile
); MIKROTIK_CLIENT_AVAILABLE = True
except ImportError: MIKROTIK_CLIENT_AVAILABLE = False

user_management_bp = Blueprint('user_management_api', __name__)

class ConfigKeys:
    MIKROTIK_DEFAULT_PROFILE = 'MIKROTIK_DEFAULT_PROFILE'
    MIKROTIK_EXPIRED_PROFILE = 'MIKROTIK_EXPIRED_PROFILE'
    ENABLE_WHATSAPP_NOTIFICATIONS = 'ENABLE_WHATSAPP_NOTIFICATIONS'
    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = 'MIKROTIK_SEND_LIMIT_BYTES_TOTAL'
    MIKROTIK_SEND_SESSION_TIMEOUT = 'MIKROTIK_SEND_SESSION_TIMEOUT'

def _generate_password(length=6, numeric_only=True):
    """Menghasilkan password acak."""
    characters = string.digits if numeric_only else string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for i in range(length))

def _send_whatsapp_notification(user_phone: str, template_key: str, context: dict):
    """Mengirim notifikasi WhatsApp jika diaktifkan."""
    if not WHATSAPP_AVAILABLE:
        current_app.logger.warning("WhatsApp client is not available. Skipping notification.")
        return False
    try:
        if settings_service.get_setting(ConfigKeys.ENABLE_WHATSAPP_NOTIFICATIONS, 'False') == 'True':
            message_body = get_notification_message(template_key, context)
            if message_body:
                return send_whatsapp_message(user_phone, message_body)
        else:
            current_app.logger.info("WhatsApp notifications are disabled in settings. Skipping.")
            return False
    except Exception as e:
        current_app.logger.error(f"Failed to send WhatsApp notification for template {template_key}: {e}", exc_info=True)
        return False
    return False

def _handle_mikrotik_operation(operation_func, **kwargs):
    """
    Menangani operasi Mikrotik dengan koneksi pool dan logging.
    """
    if not MIKROTIK_CLIENT_AVAILABLE:
        current_app.logger.warning("Mikrotik client not available. Skipping Mikrotik operation.")
        return False, "Mikrotik client not available."
    try:
        with get_mikrotik_connection() as api_conn:
            if api_conn:
                return operation_func(api_connection=api_conn, **kwargs)
            else:
                return False, "Failed to get Mikrotik connection."
    except Exception as e:
        current_app.logger.error(f"Exception during Mikrotik operation {operation_func.__name__}: {e}", exc_info=True)
        return False, f"Mikrotik Error: {str(e)}"

# --- FUNGSI HELPER BARU UNTUK PROMO ---
def _get_active_bonus_registration_promo():
    """
    Mencari event promo tipe BONUS_REGISTRATION yang sedang aktif dan belum kadaluarsa.
    Mengembalikan objek PromoEvent pertama yang ditemukan (terbaru).
    """
    now = datetime.now(dt_timezone.utc)
    query = select(PromoEvent).where(
        PromoEvent.status == PromoEventStatus.ACTIVE,
        PromoEvent.event_type == PromoEventType.BONUS_REGISTRATION,
        PromoEvent.start_date <= now,
        or_(
            PromoEvent.end_date == None,
            PromoEvent.end_date >= now
        )
    ).order_by(PromoEvent.created_at.desc())
    return db.session.execute(query).scalar_one_or_none()


def _create_admin_user_logic(data: UserCreateByAdminSchema, creator: User):
    """Logika untuk membuat pengguna dengan peran ADMIN."""
    password_portal = _generate_password(length=6, numeric_only=True)
    hashed_password = generate_password_hash(password_portal)
    new_user = User(
        full_name=data.full_name,
        phone_number=normalize_to_e164(data.phone_number),
        password_hash=hashed_password,
        role=UserRole.ADMIN,
        is_active=True,
        blok=data.blok,
        kamar=data.kamar,
        approval_status=ApprovalStatus.APPROVED,
        is_unlimited_user=False,
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
        quota_expiry_date=None
    )
    db.session.add(new_user)
    db.session.commit()
    db.session.refresh(new_user)
    context = {"phone_number": new_user.phone_number, "password": password_portal}
    _send_whatsapp_notification(new_user.phone_number, "admin_creation_success", context)
    return new_user

def _create_regular_user_logic(data: UserCreateByAdminSchema, creator: User):
    """Logika untuk membuat pengguna reguler."""
    new_user = User(
        full_name=data.full_name,
        phone_number=normalize_to_e164(data.phone_number),
        role=UserRole.USER,
        is_active=True,
        blok=data.blok,
        kamar=data.kamar,
        approval_status=ApprovalStatus.PENDING_APPROVAL,
        is_unlimited_user=False,
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
        quota_expiry_date=None
    )
    db.session.add(new_user)
    db.session.flush()
    current_app.logger.info(f"User {new_user.full_name} created with PENDING_APPROVAL.")
    db.session.commit()
    db.session.refresh(new_user)
    context = {"full_name": new_user.full_name, "phone_number": format_to_local_phone(new_user.phone_number)}
    _send_whatsapp_notification(new_user.phone_number, "user_registration_pending", context)
    return new_user

@user_management_bp.route('/users', methods=['POST'])
@admin_required
def create_user_by_admin(current_admin: User):
    """Membuat pengguna baru oleh admin (bisa admin atau pengguna reguler)."""
    data = request.json
    try:
        validated_data = UserCreateByAdminSchema.model_validate(data)
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    
    if db.session.scalar(select(User).filter_by(phone_number=normalize_to_e164(validated_data.phone_number))):
        return jsonify({"message": f"Phone number {validated_data.phone_number} is already registered."}), HTTPStatus.CONFLICT
    
    try:
        if validated_data.role == UserRole.ADMIN:
            if not current_admin.is_super_admin_role:
                return jsonify({"message": "You do not have permission to create users with ADMIN role."}), HTTPStatus.FORBIDDEN
            new_user = _create_admin_user_logic(validated_data, current_admin)
        else:
            new_user = _create_regular_user_logic(validated_data, current_admin)
        
        db.session.refresh(new_user)
        response_data = UserResponseSchema.from_orm(new_user).model_dump()
        if new_user.role == UserRole.USER:
            response_data['mikrotik_password'] = None 
        return jsonify(response_data), HTTPStatus.CREATED
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"Integrity error creating user: {e}", exc_info=True)
        return jsonify({"message": "Data conflict error (e.g., phone number already exists).", "error": str(e)}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"An internal error occurred while creating the user: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while creating the user."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/pending-count', methods=['GET'])
@admin_required
def get_pending_users_count(current_admin: User):
    """Mendapatkan jumlah pengguna dengan status persetujuan PENDING_APPROVAL."""
    try:
        count_query = select(func.count(User.id)).where(User.approval_status == ApprovalStatus.PENDING_APPROVAL)
        pending_count = db.session.scalar(count_query) or 0
        return jsonify({"pending_count": pending_count}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error in get_pending_users_count endpoint: {e}", exc_info=True)
        return jsonify({"message": "Failed to retrieve user count data."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    """Mendapatkan daftar semua pengguna dengan paginasi, pencarian, dan filter."""
    try:
        is_super_admin = current_admin.is_super_admin_role
        
        user_cols_to_select = [
            User.id,
            User.full_name,
            User.phone_number,
            User.blok,
            User.kamar,
            User.is_active,
            User.role,
            User.approval_status,
            User.mikrotik_password,
            User.is_unlimited_user,
            User.total_quota_purchased_mb,
            User.total_quota_used_mb,
            User.quota_expiry_date,
            User.created_at,
            User.updated_at,
            User.approved_at,
            User.device_brand,
            User.device_model,
            User.raw_user_agent,
            User.last_login_at
        ]

        base_query = db.select(*user_cols_to_select).select_from(User)

        if not is_super_admin:
            base_query = base_query.where(User.role == UserRole.USER)

        search_query = request.args.get('search', '').strip()
        search_conditions = []
        if search_query:
            search_term = f"%{search_query}%"
            search_conditions.append(User.full_name.ilike(search_term))
            phone_variations = get_phone_number_variations(search_query)
            if phone_variations:
                for variation in phone_variations:
                    search_conditions.append(User.phone_number.ilike(f"%{variation}%"))
            else:
                search_conditions.append(User.phone_number.ilike(search_term))
            if search_conditions:
                base_query = base_query.where(or_(*search_conditions))

        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        if hasattr(User, sort_by):
            column_to_sort = getattr(User, sort_by)
            base_query = base_query.order_by(column_to_sort.desc() if sort_order.lower() == 'desc' else column_to_sort.asc())
        else:
            base_query = base_query.order_by(User.created_at.desc())

        total_items_query = select(func.count(User.id))
        if not is_super_admin:
            total_items_query = total_items_query.where(User.role == UserRole.USER)
        if search_query and search_conditions:
             total_items_query = total_items_query.where(or_(*search_conditions))
        
        total_items = db.session.scalar(total_items_query) or 0

        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        offset = (page - 1) * per_page
        
        paginated_query = base_query.offset(offset).limit(per_page)
        
        raw_users = db.session.execute(paginated_query).all()
        
        users_data = [UserResponseSchema.from_orm(row).model_dump() for row in raw_users]
                
        return jsonify({"items": users_data, "totalItems": total_items}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error retrieving user list: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    """Memperbarui informasi pengguna oleh admin."""
    user_to_update = db.session.get(User, user_id) 
    if not user_to_update:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    if not current_admin.is_super_admin_role and user_to_update.is_admin_role:
        return jsonify({"message": "You do not have permission to edit ADMIN roles."}), HTTPStatus.FORBIDDEN
    
    data = request.get_json()
    try:
        validated_data = UserUpdateByAdminSchema.model_validate(data)
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    update_fields = validated_data.model_dump(exclude_unset=True)
    old_role = user_to_update.role
    new_role_val = validated_data.role

    if new_role_val and old_role != new_role_val:
        current_app.logger.info(f"Admin {current_admin.full_name} is changing role for user {user_to_update.full_name} from {old_role.value} to {new_role_val.value}")
        
        if old_role == UserRole.USER and new_role_val == UserRole.ADMIN:
            if not current_admin.is_super_admin_role:
                 return jsonify({"message": "Only Super Admins can upgrade users to Admin."}), HTTPStatus.FORBIDDEN

            user_to_update.previous_blok = user_to_update.blok
            user_to_update.previous_kamar = user_to_update.kamar
            user_to_update.role = UserRole.ADMIN
            user_to_update.blok = None
            user_to_update.kamar = None
            
            password_portal = _generate_password(length=6, numeric_only=True)
            user_to_update.password_hash = generate_password_hash(password_portal)
            
            context = {"full_name": user_to_update.full_name, "password": password_portal}
            _send_whatsapp_notification(user_to_update.phone_number, "user_upgrade_to_admin_with_password", context)
            
            mikrotik_username = format_to_local_phone(user_to_update.phone_number)
            if mikrotik_username:
                _handle_mikrotik_operation(delete_hotspot_user, username=mikrotik_username)
            user_to_update.mikrotik_password = None

        elif old_role == UserRole.ADMIN and new_role_val == UserRole.USER:
            user_to_update.role = UserRole.USER
            user_to_update.password_hash = None

            if user_to_update.previous_blok and user_to_update.previous_kamar:
                user_to_update.blok = user_to_update.previous_blok
                user_to_update.kamar = user_to_update.previous_kamar
                user_to_update.previous_blok = None
                user_to_update.previous_kamar = None
            elif not validated_data.blok or not validated_data.kamar:
                 return jsonify({"message": "Blok and Kamar are required when downgrading an admin to USER role if previous address is not available."}), HTTPStatus.BAD_REQUEST
            else:
                user_to_update.blok = validated_data.blok.value if validated_data.blok else None
                user_to_update.kamar = validated_data.kamar.value if validated_data.kamar else None

            new_hotspot_password = _generate_password(length=6, numeric_only=True)
            user_to_update.mikrotik_password = new_hotspot_password
            
            mikrotik_username = format_to_local_phone(user_to_update.phone_number)
            if mikrotik_username:
                _handle_mikrotik_operation(
                    activate_or_update_hotspot_user,
                    user_mikrotik_username=mikrotik_username,
                    mikrotik_profile_name=current_app.config.get(ConfigKeys.MIKROTIK_DEFAULT_PROFILE, 'default'),
                    hotspot_password=new_hotspot_password,
                    comment=f"Downgraded to USER by {current_admin.full_name}",
                    limit_bytes_total=int((user_to_update.total_quota_purchased_mb or 0) * 1024 * 1024),
                    session_timeout_seconds=int((user_to_update.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()) if user_to_update.quota_expiry_date and user_to_update.quota_expiry_date > datetime.now(dt_timezone.utc) else 0
                )

            context = {
                "full_name": user_to_update.full_name,
                "username": mikrotik_username,
                "password": new_hotspot_password
            }
            _send_whatsapp_notification(user_to_update.phone_number, "user_downgrade_to_user_with_password", context)
        else:
            return jsonify({"message": f"Role change from {old_role.value} to {new_role_val.value} is not supported."}), HTTPStatus.BAD_REQUEST

    update_fields.pop('role', None)

    for key, value in update_fields.items():
        if hasattr(user_to_update, key):
            if isinstance(value, enum.Enum):
                setattr(user_to_update, key, value.value)
            else:
                setattr(user_to_update, key, value)
    
    try:
        db.session.commit()
        db.session.refresh(user_to_update)
        return jsonify(UserResponseSchema.from_orm(user_to_update).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR

# --- PERBAIKAN PADA FUNGSI APPROVE_USER ---
@user_management_bp.route('/users/<uuid:user_id>/approve', methods=['PATCH'])
@admin_required
def approve_user(current_admin: User, user_id):
    """
    Menyetujui pengguna baru, memberikan bonus registrasi jika ada promo aktif,
    dan melakukan sinkronisasi ke Mikrotik secara robust.
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if user.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return jsonify({"message": "This user is not in pending approval status."}), HTTPStatus.CONFLICT
    if user.role == UserRole.USER and (not user.blok or not user.kamar):
        return jsonify({"message": "User with USER role must have Blok and Kamar defined before approval."}), HTTPStatus.BAD_REQUEST

    mikrotik_username = format_to_local_phone(user.phone_number)
    if not mikrotik_username:
        # Ini adalah kasus edge, tetapi penting untuk ditangani
        current_app.logger.error(f"Cannot approve user ID {user.id} because phone number '{user.phone_number}' cannot be formatted.")
        return jsonify({"message": "Cannot process approval. Invalid phone number format."}), HTTPStatus.BAD_REQUEST
        
    new_mikrotik_password = _generate_password(length=6, numeric_only=True)

    # --- LOGIKA PEMBERIAN BONUS REGISTRASI YANG LEBIH ROBUST ---
    bonus_given_mb = 0
    # Durasi default jika ada bonus, bisa juga diambil dari promo jika ada fieldnya
    bonus_duration_days = 30 
    
    active_bonus_promo = _get_active_bonus_registration_promo()
    if active_bonus_promo and active_bonus_promo.bonus_value_mb and active_bonus_promo.bonus_value_mb > 0:
        bonus_given_mb = active_bonus_promo.bonus_value_mb
        current_app.logger.info(f"Applying bonus {bonus_given_mb}MB from promo '{active_bonus_promo.name}' to user {user.full_name}.")
    else:
        current_app.logger.info(f"No active 'BONUS_REGISTRATION' promo found. User {user.full_name} will not receive a bonus quota.")

    # Tetapkan kuota dan tanggal kadaluarsa di DB
    user.total_quota_purchased_mb = bonus_given_mb
    if bonus_given_mb > 0:
        # Jika ada bonus, tetapkan tanggal kadaluarsa.
        # Logika ini bisa disesuaikan, misalnya memperpanjang jika sudah ada.
        user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=bonus_duration_days)
        current_app.logger.info(f"Setting new quota expiry date for {user.full_name} to {user.quota_expiry_date}.")
    else:
        # Jika tidak ada bonus, pastikan tanggal kadaluarsa adalah None.
        user.quota_expiry_date = None
        current_app.logger.info(f"User {user.full_name} has no bonus quota, quota_expiry_date is set to None.")

    # --- PERSIAPAN PARAMETER UNTUK MIKROTIK (LOGIKA INTI) ---
    # Pastikan nilai kuota adalah integer dan tidak negatif.
    mikrotik_limit_bytes_total = int(user.total_quota_purchased_mb or 0) * 1024 * 1024
    if mikrotik_limit_bytes_total < 0:
        mikrotik_limit_bytes_total = 0

    # Pastikan nilai timeout adalah integer dan tidak negatif.
    mikrotik_session_timeout_seconds = 0
    if user.quota_expiry_date:
        time_remaining = user.quota_expiry_date - datetime.now(dt_timezone.utc)
        mikrotik_session_timeout_seconds = max(0, int(time_remaining.total_seconds()))

    # --- LOG PENTING: Untuk memastikan nilai yang dikirim ke Mikrotik ---
    current_app.logger.info(
        f"Preparing to sync with Mikrotik for user '{mikrotik_username}' (ID: {user.id}). "
        f"Payload: "
        f"limit_bytes_total={mikrotik_limit_bytes_total}, "
        f"session_timeout_seconds={mikrotik_session_timeout_seconds}"
    )
    # --- AKHIR LOG PENTING ---

    mikrotik_success, mikrotik_message = _handle_mikrotik_operation(
        activate_or_update_hotspot_user,
        user_mikrotik_username=mikrotik_username,
        mikrotik_profile_name=settings_service.get_setting(ConfigKeys.MIKROTIK_DEFAULT_PROFILE, 'default'),
        hotspot_password=new_mikrotik_password,
        comment=f"Approved by {current_admin.full_name} | Bonus: {bonus_given_mb}MB",
        limit_bytes_total=mikrotik_limit_bytes_total,
        session_timeout_seconds=mikrotik_session_timeout_seconds
    )
    if not mikrotik_success:
        # Log error jika gagal, tapi proses tetap lanjut untuk update DB
        current_app.logger.error(f"Failed to activate user {user.full_name} in Mikrotik: {mikrotik_message}")
        # Jangan return di sini, agar status user di DB tetap terupdate.
        
    # Update status user di database, APAPUN hasil dari Mikrotik
    user.approval_status = ApprovalStatus.APPROVED
    user.is_active = True
    user.approved_at = datetime.now(dt_timezone.utc)
    user.approved_by_id = current_admin.id
    user.mikrotik_password = new_mikrotik_password
    user.is_unlimited_user = False
    user.total_quota_used_mb = 0

    try:
        db.session.commit()
        db.session.refresh(user)
    except Exception as e_db:
        db.session.rollback()
        current_app.logger.error(f"CRITICAL: Failed to commit user approval to DB for user {user_id} after Mikrotik operation. Error: {e_db}", exc_info=True)
        # Jika gagal simpan ke DB, ini adalah error serius
        return jsonify({
            "message": "User approval failed due to a database error. Please check logs.",
            "mikrotik_status": f"Operation attempted with message: {mikrotik_message}"
        }), HTTPStatus.INTERNAL_SERVER_ERROR

    # Kirim notifikasi setelah semua proses berhasil
    context = {
        "full_name": user.full_name,
        "username": mikrotik_username,
        "password": new_mikrotik_password,
        "bonus_mb": bonus_given_mb,
        "quota_expiry_date": user.quota_expiry_date.strftime('%d %B %Y %H:%M') if user.quota_expiry_date else 'Tidak Ada'
    }
    notification_sent = _send_whatsapp_notification(user.phone_number, "user_approve_success", context)
    
    return jsonify({
        "message": "User approved successfully.",
        "user": UserResponseSchema.from_orm(user).model_dump(),
        "mikrotik_status": "OK" if mikrotik_success else f"Warning: {mikrotik_message}",
        "notification_sent": notification_sent
    }), HTTPStatus.OK


@user_management_bp.route('/users/<uuid:user_id>/reject', methods=['POST'])
@admin_required
def reject_user(current_admin: User, user_id):
    """Menolak pendaftaran pengguna dan menghapus datanya."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if user.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return jsonify({"message": "This user is not in pending approval status (cannot be rejected)."}), HTTPStatus.CONFLICT
    
    mikrotik_status_action = "Not attempted."
    mikrotik_username_target = format_to_local_phone(user.phone_number)
    
    if MIKROTIK_CLIENT_AVAILABLE and mikrotik_username_target and user.mikrotik_password:
        try:
            current_app.logger.info(f"Admin '{current_admin.full_name}' attempting to move user '{mikrotik_username_target}' to expired profile (rejection).")
            with get_mikrotik_connection() as api_conn:
                if api_conn:
                    expired_profile_name = settings_service.get_setting(ConfigKeys.MIKROTIK_EXPIRED_PROFILE, 'expired')
                    success_profile, msg_profile = set_hotspot_user_profile(api_conn, mikrotik_username_target, expired_profile_name)
                    mikrotik_status_action = f"Mikrotik: {'Success' if success_profile else 'Failed'} moving to '{expired_profile_name}' profile ({msg_profile})."
                else:
                    mikrotik_status_action = "Mikrotik connection failed."
        except Exception as e_mt:
            mikrotik_status_action = f"Mikrotik exception: {str(e_mt)}"
            current_app.logger.error(f"Exception moving user {user.id} to expired Mikrotik profile on rejection: {e_mt}", exc_info=True)
    
    user_name_log = user.full_name
    user_phone_log = user.phone_number
    
    try:
        if WHATSAPP_AVAILABLE and user_phone_log and settings_service.get_setting(ConfigKeys.ENABLE_WHATSAPP_NOTIFICATIONS, 'False') == 'True':
            context = {"full_name": user_name_log}
            _send_whatsapp_notification(user_phone_log, "user_reject_notification", context)
            current_app.logger.info(f"Rejection notification sent to {user_phone_log}.")
    except Exception as e_notif:
        current_app.logger.error(f"Failed to send rejection notification for {user_phone_log}: {e_notif}", exc_info=True)
    
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({
            "message": f"User registration for {user_name_log} ({user_phone_log}) rejected and data deleted.",
            "mikrotik_status_action": mikrotik_status_action
        }), HTTPStatus.OK
    except Exception as e_db:
        db.session.rollback()
        current_app.logger.error(f"Failed to delete user from database after rejection: {e_db}", exc_info=True)
        return jsonify({"message": f"Failed to delete user from database. Error: {str(e_db)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_admin: User, user_id):
    """Menghapus pengguna secara permanen."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if user.id == current_admin.id:
        return jsonify({"message": "You cannot delete your own account."}), HTTPStatus.FORBIDDEN
    if user.is_admin_role and not current_admin.is_super_admin_role:
        return jsonify({"message": "Access denied: You do not have permission to delete an an_admin."}), HTTPStatus.FORBIDDEN
    if user.role == UserRole.SUPER_ADMIN and current_admin.role == UserRole.ADMIN:
        return jsonify({"message": "Access denied: Admin cannot delete Super Admin."}), HTTPStatus.FORBIDDEN
    if user.approval_status == ApprovalStatus.PENDING_APPROVAL:
        return jsonify({"message": "To reject a registration, use the 'Reject' action."}), HTTPStatus.BAD_REQUEST
    
    user_name_log = user.full_name
    user_phone_log = user.phone_number
    
    mikrotik_status = "Not attempted (client not available)."
    if MIKROTIK_CLIENT_AVAILABLE and format_to_local_phone(user_phone_log):
        try:
            with get_mikrotik_connection() as api_conn:
                if api_conn:
                    _, mikrotik_status = delete_hotspot_user(api_connection=api_conn, username=format_to_local_phone(user_phone_log))
                else:
                    mikrotik_status = "Mikrotik connection failed."
        except Exception as e_mt:
            mikrotik_status = f"Exception occurred: {str(e_mt)}"
            current_app.logger.error(f"Exception deleting user {user.id} from Mikrotik: {e_mt}", exc_info=True)
    
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({ "message": f"User {user_name_log} deleted successfully.", "mikrotik_status": mikrotik_status }), HTTPStatus.OK
    except Exception as e_db:
        db.session.rollback()
        current_app.logger.error(f"Failed to delete user from database. Error: {e_db}", exc_info=True)
        return jsonify({"message": f"Failed to delete user from database. Error: {str(e_db)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/me', methods=['PUT'])
@admin_required
def update_own_admin_profile(current_admin: User):
    """Memperbarui profil admin yang sedang login."""
    data = request.get_json()
    if not data:
        return jsonify({"message": "Data cannot be empty."}), HTTPStatus.BAD_REQUEST
    try:
        validated_data = UserProfileUpdateRequestSchema.model_validate(data)
        update_dict = validated_data.model_dump(exclude_unset=True)
        
        if 'full_name' in update_dict:
            current_admin.full_name = update_dict['full_name']
        if 'blok' in update_dict and validated_data.blok is not None:
            current_admin.blok = validated_data.blok
        if 'kamar' in update_dict and validated_data.kamar is not None:
            current_admin.kamar = validated_data.kamar
        
        db.session.commit()
        db.session.refresh(current_admin)
        return jsonify(UserResponseSchema.from_orm(current_admin).model_dump()), HTTPStatus.OK
    except (ValidationError, ValueError) as e:
        error_detail = e.errors() if isinstance(e, ValidationError) else str(e)
        return jsonify({"errors": error_detail}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update admin profile {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while saving the profile."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/generate-admin-password', methods=['POST'])
@admin_required
def generate_admin_password_for_user(current_admin: User, user_id):
    """Menghasilkan password portal baru untuk pengguna dengan peran ADMIN."""
    user_to_update = db.session.get(User, user_id)
    if not user_to_update:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if not user_to_update.is_admin_role:
        return jsonify({"message": "Only Admin roles can generate portal passwords."}), HTTPStatus.BAD_REQUEST
    if user_to_update.id != current_admin.id and not current_admin.is_super_admin_role:
        return jsonify({"message": "Access denied: You do not have permission to generate another admin's password."}), HTTPStatus.FORBIDDEN
    try:
        new_portal_password = _generate_password(length=6, numeric_only=True)
        user_to_update.password_hash = generate_password_hash(new_portal_password)
        db.session.commit()
        
        context = { "phone_number": user_to_update.phone_number, "password": new_portal_password }
        _send_whatsapp_notification(user_to_update.phone_number, "admin_password_generated", context)
        
        current_app.logger.info(f"Admin password for {user_to_update.full_name} generated and sent via WA.")
        return jsonify({"message": "New password generated and sent via WhatsApp."}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to generate admin password for {user_to_update.id}: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while generating password."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/reset-hotspot-password', methods=['POST'])
@admin_required
def admin_reset_hotspot_password(current_admin: User, user_id):
    """Mereset password hotspot pengguna reguler."""
    user_to_reset = db.session.get(User, user_id)
    if not user_to_reset:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if user_to_reset.role != UserRole.USER:
        return jsonify({"message": "Only regular users can have hotspot passwords reset."}), HTTPStatus.BAD_REQUEST
    
    try:
        new_mikrotik_password = _generate_password(length=6, numeric_only=True)
        mikrotik_success = False
        mikrotik_message = "Mikrotik client not configured or unavailable."
        
        if MIKROTIK_CLIENT_AVAILABLE:
            try:
                with get_mikrotik_connection() as api_conn:
                    if api_conn:
                        mikrotik_profile_name = settings_service.get_setting(ConfigKeys.MIKROTIK_DEFAULT_PROFILE, 'default')
                        mikrotik_username = format_to_local_phone(user_to_reset.phone_number)
                        
                        limit_bytes_total = int(user_to_reset.total_quota_purchased_mb or 0) * 1024 * 1024
                        if limit_bytes_total < 0: limit_bytes_total = 0
                        
                        session_timeout_seconds = 0
                        if user_to_reset.quota_expiry_date:
                            time_remaining = (user_to_reset.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()
                            session_timeout_seconds = max(0, int(time_remaining))
                        
                        current_app.logger.info(
                            f"Sending to Mikrotik (Reset Password) - User: {mikrotik_username}, "
                            f"Limit Bytes: {limit_bytes_total}, "
                            f"Timeout: {session_timeout_seconds}"
                        )

                        activate_success, msg = activate_or_update_hotspot_user(
                            api_connection=api_conn, 
                            user_mikrotik_username=mikrotik_username,
                            mikrotik_profile_name=mikrotik_profile_name, 
                            hotspot_password=new_mikrotik_password,
                            comment=f"Password reset by Admin {current_admin.full_name}",
                            limit_bytes_total=limit_bytes_total,
                            session_timeout_seconds=session_timeout_seconds
                        )
                        mikrotik_success = activate_success
                        mikrotik_message = msg
                    else:
                        mikrotik_message = "Failed to get Mikrotik connection pool."
            except Exception as e:
                current_app.logger.error(f"Exception during Mikrotik password reset for user {user_to_reset.id}: {e}", exc_info=True)
                mikrotik_message = f"Mikrotik Error: {str(e)}"
        
        user_to_reset.mikrotik_password = new_mikrotik_password
        db.session.commit()
        db.session.refresh(user_to_reset)
        current_app.logger.info(f"Local DB password for user {user_to_reset.id} has been updated by admin {current_admin.id}.")
        
        notification_sent = False
        context = {
            "full_name": user_to_reset.full_name,
            "username": format_to_local_phone(user_to_reset.phone_number),
            "password": new_mikrotik_password,
            "bonus_mb": user_to_reset.total_quota_purchased_mb,
            "quota_expiry_date": user_to_reset.quota_expiry_date.strftime('%d %B %Y %H:%M') if user_to_reset.quota_expiry_date else 'Tidak Ada'
        }
        notification_sent = _send_whatsapp_notification(user_to_reset.phone_number, "user_hotspot_password_reset_by_admin", context)
        
        if notification_sent:
            current_app.logger.info(f"Hotspot password reset notification sent to {user_to_reset.phone_number}.")
        else:
            current_app.logger.warning(f"Failed to send hotspot password reset notification to {user_to_reset.phone_number}.")
        
        final_message = "Password hotspot berhasil direset."
        if not mikrotik_success:
            final_message = f"Password berhasil disimpan, namun GAGAL sinkronisasi ke perangkat hotspot. Error: {mikrotik_message}"
        
        return jsonify({
            "success": True, "message": final_message,
            "mikrotik_synced": mikrotik_success,
            "notification_sent": notification_sent
        }), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Terjadi kesalahan internal saat mereset password untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Terjadi kesalahan internal saat mereset password."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/form-options/alamat', methods=['GET'])
@admin_required
def get_alamat_form_options(current_admin: User):
    """Mengambil opsi untuk dropdown 'blok' dan 'kamar'."""
    try:
        blok_options = [e.value for e in UserBlok]
        kamar_options = [e.value.replace('Kamar_', '') for e in UserKamar]
        return jsonify({"success": True, "bloks": blok_options, "kamars": kamar_options}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve address form options: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Failed to load form options."}), HTTPStatus.INTERNAL_SERVER_ERROR