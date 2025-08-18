# backend/app/infrastructure/http/admin/user_management_routes.py
# VERSI FINAL: Memperbaiki error 422 dengan menggunakan Pydantic untuk serialisasi.
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false

import uuid
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone as dt_timezone, timedelta
from http import HTTPStatus
from decimal import Decimal
from pydantic import ValidationError
from typing import List

from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, ApprovalStatus, UserBlok, UserKamar, Package, Transaction,
    TransactionStatus, QuotaRequest, RequestStatus, NotificationRecipient, NotificationType
)
from app.infrastructure.http.decorators import admin_required, super_admin_required
from app.infrastructure.http.schemas.user_schemas import UserResponseSchema
from app.infrastructure.http.schemas.api_schemas import (
    NotificationRecipientStatusSchema,
    NotificationRecipientUpdateSchema, NotificationUpdateResponseSchema
)
from app.utils.formatters import get_phone_number_variations, format_to_local_phone
from app.services.user_management import (
    user_approval, user_deletion, user_profile as user_profile_service
)
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details
from app.tasks import sync_single_user_status

user_management_bp = Blueprint('user_management_api', __name__)

@user_management_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        search_query = request.args.get('search', '').strip()
        role_filter = request.args.get('role')
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')

        # [PERBAIKAN KUNCI 1] Query sekarang mengambil seluruh objek User, bukan kolom terpisah.
        # Ini penting agar Pydantic bisa bekerja dengan data lengkap.
        query = select(User)

        if not current_admin.is_super_admin_role:
            query = query.where(User.role != UserRole.SUPER_ADMIN)
        if role_filter:
            query = query.where(User.role == UserRole[role_filter.upper()])
        if search_query:
            variations = get_phone_number_variations(search_query)
            query = query.where(or_(
                User.full_name.ilike(f"%{search_query}%"),
                User.phone_number.in_(variations)
            ))

        sortable_columns = {
            'created_at': User.created_at, 'full_name': User.full_name,
            'approval_status': User.approval_status, 'role': User.role, 'is_active': User.is_active
        }
        sort_col = sortable_columns.get(sort_by, User.created_at)
        query = query.order_by(sort_col.desc() if sort_order == 'desc' else sort_col.asc())

        # Gunakan db.paginate untuk efisiensi
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        users_list = pagination.items
        total = pagination.total

        # [PERBAIKAN KUNCI 2] Gunakan UserResponseSchema untuk mengubah setiap objek User
        # menjadi JSON yang bersih dan aman. Ini menghilangkan pembuatan dictionary manual.
        users_data = [UserResponseSchema.from_orm(user).model_dump() for user in users_list]

        return jsonify({"items": users_data, "totalItems": total}), HTTPStatus.OK
    
    except Exception as e:
        current_app.logger.error(f"Error di get_users_list: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR

# --- Rute lain tidak diubah, hanya get_users_list yang diperbaiki ---

@user_management_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats(current_admin: User):
    try:
        now_utc = datetime.now(dt_timezone.utc)
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_this_week = start_of_today_utc - timedelta(days=now_utc.weekday())
        start_of_last_week = start_of_this_week - timedelta(days=7)

        revenue_today = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc)) or Decimal('0.00')
        revenue_month = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc)) or Decimal('0.00')
        revenue_week = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_this_week)) or Decimal('0.00')
        revenue_last_week = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_last_week, Transaction.created_at < start_of_this_week)) or Decimal('0.00')
        
        transactions_week = db.session.scalar(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_this_week)) or 0
        transactions_last_week = db.session.scalar(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_last_week, Transaction.created_at < start_of_this_week)) or 0
        
        new_registrants = db.session.scalar(select(func.count(User.id)).where(User.approval_status == ApprovalStatus.PENDING_APPROVAL)) or 0
        active_users = db.session.scalar(select(func.count(User.id)).where(User.is_active == True)) or 0
        expiring_soon_users = db.session.scalar(select(func.count(User.id)).where(User.quota_expiry_date.between(now_utc, now_utc + timedelta(days=7)))) or 0
        
        kuota_terjual_gb = db.session.scalar(select(func.sum(Package.data_quota_gb)).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc)) or 0
        
        latest_transactions_q = select(Transaction).options(db.selectinload(Transaction.user).load_only(User.full_name, User.phone_number), db.selectinload(Transaction.package).load_only(Package.name)).where(Transaction.status == TransactionStatus.SUCCESS).order_by(desc(Transaction.created_at)).limit(5)
        latest_transactions = db.session.scalars(latest_transactions_q).all()
        transaksi_terakhir_data = [{"id": str(tx.id), "amount": float(tx.amount), "created_at": tx.created_at.isoformat(), "package": {"name": tx.package.name if tx.package else "N/A"}, "user": {"full_name": tx.user.full_name if tx.user else "Pengguna Dihapus", "phone_number": tx.user.phone_number if tx.user else None}} for tx in latest_transactions]

        top_packages_q = select(Package.name, func.count(Transaction.id).label('sales_count')).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc).group_by(Package.name).order_by(desc('sales_count')).limit(5)
        top_packages = db.session.execute(top_packages_q).all()
        paket_terlaris_data = [{"name": name, "count": count} for name, count in top_packages]
        
        pending_requests_count = db.session.scalar(select(func.count(QuotaRequest.id)).where(QuotaRequest.status == RequestStatus.PENDING)) or 0

        days_range = [start_of_today_utc - timedelta(days=i) for i in range(29, -1, -1)]
        revenue_per_day_q = db.session.query(func.date(Transaction.created_at), func.sum(Transaction.amount)).filter(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc - timedelta(days=30)).group_by(func.date(Transaction.created_at)).all()
        
        revenue_map = {d.strftime('%Y-%m-%d'): float(v) for d, v in revenue_per_day_q}
        pendapatan_per_hari = [revenue_map.get(day.strftime('%Y-%m-%d'), 0) for day in days_range]

        stats = {
            "pendapatanHariIni": float(revenue_today), "pendapatanBulanIni": float(revenue_month),
            "pendaftarBaru": new_registrants, "penggunaAktif": active_users, "akanKadaluwarsa": expiring_soon_users,
            "kuotaTerjualMb": float(kuota_terjual_gb) * 1024, "transaksiTerakhir": transaksi_terakhir_data, "paketTerlaris": paket_terlaris_data,
            "permintaanTertunda": pending_requests_count, "pendapatanMingguIni": float(revenue_week), "pendapatanMingguLalu": float(revenue_last_week),
            "transaksiMingguIni": transactions_week, "transaksiMingguLalu": transactions_last_week,
            "pendapatanPerHari": pendapatan_per_hari
        }
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error di endpoint dashboard/stats: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat statistik dasbor."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/form-options/alamat', methods=['GET'])
@admin_required
def get_alamat_form_options(current_admin: User):
    return jsonify({"bloks": [e.value for e in UserBlok], "kamars": [e.value.replace('Kamar_', '') for e in UserKamar]}), HTTPStatus.OK
    
@user_management_bp.route('/users', methods=['POST'])
@admin_required
def create_user_by_admin(current_admin: User):
    data = request.get_json()
    if not data: 
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
    
    success, message, new_user = user_profile_service.create_user_by_admin(current_admin, data)
    
    if not success:
        db.session.rollback()
        if "sudah terdaftar" in message:
            return jsonify({"message": message}), HTTPStatus.CONFLICT
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    
    try:
        db.session.commit()
        db.session.refresh(new_user)
        sync_single_user_status.delay(user_id=str(new_user.id))
        return jsonify(UserResponseSchema.from_orm(new_user).model_dump()), HTTPStatus.CREATED
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat commit pembuatan user: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan data ke database."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    data = request.get_json()
    if not data: return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
    try:
        if data.get("toggle_status"):
            new_active_status = data.get("is_active", user.is_active)
            user.is_active = new_active_status
            user.is_blocked = not new_active_status
            db.session.commit()
            sync_single_user_status.delay(user_id=str(user.id))
            message = "Status pengguna berhasil diperbarui dan sinkronisasi ke MikroTik sedang diproses."
            db.session.refresh(user)
            return jsonify({"message": message, "user": UserResponseSchema.from_orm(user).model_dump()}), HTTPStatus.OK

        success, message, updated_user = user_profile_service.update_user_by_admin_comprehensive(user, current_admin, data)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        
        db.session.commit()
        sync_single_user_status.delay(user_id=str(user.id))

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
    if not user: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    try:
        success, message = user_deletion.process_user_removal(user, current_admin)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.FORBIDDEN
        db.session.commit()
        return jsonify({"message": message}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
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

@user_management_bp.route('/users/<uuid:user_id>/mikrotik-status', methods=['GET'])
@admin_required
def check_mikrotik_status(current_admin: User, user_id: uuid.UUID):
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"message": "Pengguna tidak ditemukan di database."}), HTTPStatus.NOT_FOUND

        mikrotik_username = format_to_local_phone(user.phone_number)
        if not mikrotik_username:
            return jsonify({"exists_on_mikrotik": False, "message": "Format nomor telepon pengguna tidak valid."}), HTTPStatus.OK

        success, details, message = get_hotspot_user_details(username=mikrotik_username)

        if not success:
            return jsonify({"message": f"Gagal terhubung ke Mikrotik: {message}"}), HTTPStatus.SERVICE_UNAVAILABLE

        user_exists = details is not None
        if user.mikrotik_user_exists != user_exists:
            user.mikrotik_user_exists = user_exists
            db.session.commit()

        return jsonify({"user_id": str(user.id), "exists_on_mikrotik": user_exists, "details": details}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal tak terduga pada server."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/notification-recipients', methods=['GET'])
@super_admin_required
def get_notification_recipients(current_admin: User):
    try:
        all_admins_query = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN])).order_by(User.full_name.asc())
        all_admins = db.session.scalars(all_admins_query).all()
        subscribed_admin_ids_query = select(NotificationRecipient.admin_user_id).where(NotificationRecipient.notification_type == NotificationType.NEW_USER_REGISTRATION)
        subscribed_admin_ids = set(db.session.scalars(subscribed_admin_ids_query).all())
        response_data = []
        for admin in all_admins:
            status_data = NotificationRecipientStatusSchema(id=admin.id, full_name=admin.full_name, phone_number=admin.phone_number, is_subscribed=(admin.id in subscribed_admin_ids))
            response_data.append(status_data.model_dump())
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error retrieving notification recipient list: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while retrieving data."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/notification-recipients', methods=['POST'])
@super_admin_required
def update_notification_recipients(current_admin: User):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body cannot be empty."}), HTTPStatus.BAD_REQUEST
    try:
        update_data = NotificationRecipientUpdateSchema.model_validate(json_data)
        notification_type = update_data.notification_type
        db.session.execute(db.delete(NotificationRecipient).where(NotificationRecipient.notification_type == notification_type))
        new_recipients = []
        if update_data.subscribed_admin_ids:
            valid_admin_ids_q = select(User.id).where(User.id.in_(update_data.subscribed_admin_ids), User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
            valid_admin_ids = db.session.scalars(valid_admin_ids_q).all()
            for admin_id in valid_admin_ids:
                new_recipients.append(NotificationRecipient(admin_user_id=admin_id, notification_type=notification_type))
            if new_recipients:
                db.session.add_all(new_recipients)
        db.session.commit()
        response = NotificationUpdateResponseSchema(total_recipients=len(new_recipients))
        return jsonify(response.model_dump()), HTTPStatus.OK
    except ValidationError as e:
        current_app.logger.error(f"Pydantic validation error in update_notification_recipients: {e.errors()}", exc_info=True)
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update notification recipients: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while saving data."}), HTTPStatus.INTERNAL_SERVER_ERROR
        
@user_management_bp.route('/transactions', methods=['GET'])
@admin_required
def get_transactions_list(current_admin: User):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        search_query = request.args.get('search', '').strip()
        user_id_filter = request.args.get('user_id')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        query = db.select(Transaction).options(
            selectinload(Transaction.user),
            selectinload(Transaction.package)
        )
        
        if search_query:
            query = query.outerjoin(User, Transaction.user_id == User.id)

        if user_id_filter:
            try:
                user_uuid = uuid.UUID(user_id_filter)
                query = query.where(Transaction.user_id == user_uuid)
            except ValueError:
                return jsonify({"message": "Invalid user_id format."}), HTTPStatus.BAD_REQUEST
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.where(Transaction.created_at >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.where(Transaction.created_at < (end_date + timedelta(days=1)))

        if search_query:
            search_term = f"%{search_query}%"
            search_conditions = [
                Transaction.midtrans_order_id.ilike(search_term),
                User.full_name.ilike(search_term) if Transaction.user_id is not None else False
            ]
            
            phone_variations = get_phone_number_variations(search_query)
            if phone_variations:
                for variation in phone_variations:
                    if Transaction.user_id is not None:
                        search_conditions.append(User.phone_number.ilike(f"%{variation}%"))
            else:
                if Transaction.user_id is not None:
                    search_conditions.append(User.phone_number.ilike(search_term))
            
            query = query.where(or_(*[c for c in search_conditions if c is not False]))

        sortable_columns = {
            'created_at': Transaction.created_at,
            'amount': Transaction.amount,
            'status': Transaction.status,
            'order_id': Transaction.midtrans_order_id,
        }
        if sort_by in sortable_columns:
            column_to_sort = sortable_columns[sort_by]
            query = query.order_by(column_to_sort.desc() if sort_order.lower() == 'desc' else column_to_sort.asc())
        else:
            query = query.order_by(Transaction.created_at.desc())

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        transactions_data = []
        for tx in pagination.items:
            transactions_data.append({
                "id": str(tx.id),
                "order_id": tx.midtrans_order_id,
                "amount": float(tx.amount) if tx.amount is not None else 0,
                "status": tx.status.value if tx.status else 'UNKNOWN',
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "user": {
                    "full_name": tx.user.full_name if tx.user else "N/A",
                    "phone_number": tx.user.phone_number if tx.user else "N/A"
                },
                "package_name": tx.package.name if tx.package else "N/A"
            })
        return jsonify({
            "items": transactions_data,
            "totalItems": pagination.total
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error retrieving transaction list: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while retrieving transaction data."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/transactions/export', methods=['GET'])
@admin_required
def export_transactions(current_admin: User):
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    user_id_filter = request.args.get('user_id')
    export_format = request.args.get('format')
    if not all([start_date_str, end_date_str, export_format]):
        return jsonify({"message": "start_date, end_date, and format parameters are required."}), HTTPStatus.BAD_REQUEST
    current_app.logger.info(f"Admin {current_admin.id} requested transaction export from {start_date_str} to {end_date_str} for user '{user_id_filter or 'All'}' in {export_format} format.")
    return jsonify({
        "message": f"Export function for {export_format} is under development.",
        "params_received": {
            "start": start_date_str,
            "end": end_date_str,
            "user_id": user_id_filter,
            "format": export_format
        }
    }), HTTPStatus.NOT_IMPLEMENTED