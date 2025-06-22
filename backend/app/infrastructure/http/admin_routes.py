# backend/app/infrastructure/http/admin/admin_routes.py
import json
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone as dt_timezone, timedelta
from http import HTTPStatus
from pydantic import ValidationError
from typing import List
from decimal import Decimal
import uuid

from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, Package, ApprovalStatus, Transaction,
    TransactionStatus, NotificationRecipient, NotificationType,
    QuotaRequest, RequestStatus, AdminActionLog
)
from .decorators import admin_required, super_admin_required
from .schemas.notification_schemas import NotificationRecipientUpdateSchema
from app.utils.formatters import get_phone_number_variations

admin_bp = Blueprint('admin_api', __name__)

@admin_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats(current_admin: User):
    """Menyediakan statistik komprehensif untuk dasbor admin."""
    try:
        now_utc = datetime.now(dt_timezone.utc)
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        seven_days_from_now = now_utc + timedelta(days=7)

        revenue_today = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc)) or Decimal('0.00')
        revenue_month = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc)) or Decimal('0.00')
        new_registrants = db.session.scalar(select(func.count(User.id)).where(User.approval_status == ApprovalStatus.PENDING_APPROVAL)) or 0
        active_users = db.session.scalar(select(func.count(User.id)).where(User.approval_status == ApprovalStatus.APPROVED)) or 0
        expiring_soon_users = db.session.scalar(select(func.count(User.id)).where(User.quota_expiry_date.between(now_utc, seven_days_from_now))) or 0
        
        kuota_terjual_gb = db.session.scalar(select(func.sum(Package.data_quota_gb)).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc, Package.data_quota_gb > 0)) or Decimal('0.0')
        kuota_terjual_mb = float(kuota_terjual_gb) * 1024

        latest_transactions_q = select(Transaction).options(selectinload(Transaction.user).load_only(User.full_name), selectinload(Transaction.package).load_only(Package.name)).where(Transaction.status == TransactionStatus.SUCCESS).order_by(desc(Transaction.created_at)).limit(5)
        latest_transactions = db.session.scalars(latest_transactions_q).all()
        transaksi_terakhir_data = [{"id": str(tx.id), "amount": float(tx.amount), "package": {"name": tx.package.name if tx.package else "N/A"}, "user": {"full_name": tx.user.full_name if tx.user else "Pengguna Dihapus"}} for tx in latest_transactions]
        
        top_packages_q = select(Package.name, func.count(Transaction.id).label('sales_count')).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc).group_by(Package.name).order_by(desc('sales_count')).limit(5)
        top_packages = db.session.execute(top_packages_q).all()
        paket_terlaris_data = [{"name": name, "count": count} for name, count in top_packages]
        
        pending_requests_count = db.session.scalar(select(func.count(QuotaRequest.id)).where(QuotaRequest.status == RequestStatus.PENDING)) or 0

        stats = {
            "pendapatanHariIni": float(revenue_today), "pendapatanBulanIni": float(revenue_month),
            "pendaftarBaru": new_registrants, "penggunaAktif": active_users, "akanKadaluwarsa": expiring_soon_users,
            "kuotaTerjualMb": kuota_terjual_mb, "transaksiTerakhir": transaksi_terakhir_data, "paketTerlaris": paket_terlaris_data,
            "permintaanTertunda": pending_requests_count,
        }
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error di endpoint dashboard/stats: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat statistik dasbor."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/notification-recipients', methods=['GET'])
@super_admin_required
def get_notification_recipients(current_admin: User):
    """Mengambil daftar admin dan status langganan mereka untuk tipe notifikasi tertentu."""
    notification_type_str = request.args.get('type', 'NEW_USER_REGISTRATION')
    try:
        notification_type = NotificationType[notification_type_str.upper()]
    except KeyError:
        return jsonify({"message": f"Tipe notifikasi tidak valid: {notification_type_str}"}), HTTPStatus.BAD_REQUEST

    try:
        all_admins_query = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN])).order_by(User.full_name.asc())
        all_admins = db.session.scalars(all_admins_query).all()
        
        subscribed_admin_ids_query = select(NotificationRecipient.admin_user_id).where(NotificationRecipient.notification_type == notification_type)
        subscribed_admin_ids = set(db.session.scalars(subscribed_admin_ids_query).all())
        
        response_data = []
        for admin in all_admins:
            status_data = {
                "id": str(admin.id), 
                "full_name": admin.full_name, 
                "phone_number": admin.phone_number, 
                "is_subscribed": admin.id in subscribed_admin_ids
            }
            response_data.append(status_data)
        
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar penerima notifikasi untuk tipe {notification_type.name}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat mengambil data."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/notification-recipients', methods=['POST'])
@super_admin_required
def update_notification_recipients(current_admin: User):
    """Memperbarui daftar penerima untuk tipe notifikasi tertentu dari payload."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
    
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
        return jsonify({"message": "Pengaturan notifikasi berhasil disimpan.", "total_recipients": len(new_recipients)}), HTTPStatus.OK
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui penerima notifikasi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat menyimpan data."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/transactions', methods=['GET'])
@admin_required
def get_transactions_list(current_admin: User):
    """Mengambil daftar transaksi dengan paginasi dan filter."""
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
            phone_variations = get_phone_number_variations(search_query)
            query = query.where(or_(
                Transaction.midtrans_order_id.ilike(search_term),
                User.full_name.ilike(search_term),
                User.phone_number.in_(phone_variations) if phone_variations else User.phone_number.ilike(search_term)
            ))

        sortable_columns = {'created_at': Transaction.created_at, 'amount': Transaction.amount, 'status': Transaction.status}
        if sort_by in sortable_columns:
            query = query.order_by(desc(sortable_columns[sort_by]) if sort_order == 'desc' else sortable_columns[sort_by])
        else:
            query = query.order_by(desc(Transaction.created_at))

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        transactions_data = [{"id": str(tx.id), "order_id": tx.midtrans_order_id, "amount": float(tx.amount), "status": tx.status.value, "created_at": tx.created_at.isoformat(), "user": {"full_name": tx.user.full_name if tx.user else "N/A", "phone_number": tx.user.phone_number if tx.user else "N/A"}, "package_name": tx.package.name if tx.package else "N/A"} for tx in pagination.items]
        
        return jsonify({"items": transactions_data, "totalItems": pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar transaksi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/transactions/export', methods=['GET'])
@admin_required
def export_transactions(current_admin: User):
    """Endpoint untuk ekspor data transaksi (belum diimplementasikan)."""
    return jsonify({"message": "Fungsi ekspor sedang dalam pengembangan."}), HTTPStatus.NOT_IMPLEMENTED

# --- Endpoint /action-logs DIHAPUS DARI SINI ---
# Logika ini sekarang sepenuhnya ditangani oleh action_log_routes.py