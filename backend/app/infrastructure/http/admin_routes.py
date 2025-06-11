# backend/app/infrastructure/http/admin_routes.py
# VERSI FINAL: Disesuaikan kembali dengan Model A (Paket Fleksibel).
# Menghapus CRUD profil dan menyesuaikan skema & endpoint.
# PERBAIKAN: Penanganan Enum UserBlok dan UserKamar di API agar konsisten dengan string.

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone as dt_timezone, timedelta
from http import HTTPStatus
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
import uuid # PERBAIKAN: Tambahkan impor uuid

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, Package, ApprovalStatus, Transaction,
    TransactionStatus, NotificationRecipient, NotificationType, ApplicationSetting
)
from .decorators import admin_required, super_admin_required

# Mengambil skema yang tersisa jika masih ada
# dari .schemas.user_schemas import UserResponseSchema, UserUpdateByAdminSchema, UserCreateByAdminSchema
from app.utils.formatters import get_phone_number_variations
from app.services.notification_service import get_notification_message

# Import settings_service for ConfigKeys
from app.services import settings_service

# Define admin_bp for remaining routes
admin_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')

# --- Helper dan Konstanta yang mungkin masih digunakan di rute yang tersisa ---
class ConfigKeys:
    MIKROTIK_DEFAULT_PROFILE = 'MIKROTIK_DEFAULT_PROFILE'
    MIKROTIK_EXPIRED_PROFILE = 'MIKROTIK_EXPIRED_PROFILE'
    ENABLE_WHATSAPP_NOTIFICATIONS = 'ENABLE_WHATSAPP_NOTIFICATIONS'

# Removed: _generate_password, _send_whatsapp_notification, _handle_mikrotik_operation
# as they are primarily used by user management routes.
# If _send_whatsapp_notification or _handle_mikrotik_operation are needed
# by these remaining routes, they should be re-imported or defined here.


# --- Endpoints yang tersisa (dashboard stats, notif recipients, transactions) ---

@admin_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats(current_admin: User):
    """Provides key statistics for the admin dashboard, including weekly revenue."""
    try:
        total_users_query = select(func.count(User.id)).where(User.role == UserRole.USER)
        total_users = db.session.scalar(total_users_query) or 0

        pending_approvals_query = select(func.count(User.id)).where(User.approval_status == ApprovalStatus.PENDING_APPROVAL)
        pending_approvals = db.session.scalar(pending_approvals_query) or 0

        active_packages_query = select(func.count(Package.id)).where(Package.is_active == True)
        active_packages = db.session.scalar(active_packages_query) or 0

        today = datetime.now(dt_timezone.utc).date()
        start_of_month = today.replace(day=1)
        monthly_revenue_query = select(func.sum(Transaction.amount)).where(
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.created_at >= start_of_month
        )
        monthly_revenue = db.session.scalar(monthly_revenue_query) or Decimal('0.00')

        start_of_week = today - timedelta(days=today.weekday())
        weekly_revenue_query = select(func.sum(Transaction.amount)).where(
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.created_at >= start_of_week
        )
        weekly_revenue = db.session.scalar(weekly_revenue_query) or Decimal('0.00')

        stats = {
            "totalUsers": total_users,
            "pendingApprovals": pending_approvals,
            "activePackages": active_packages,
            "monthlyRevenue": float(monthly_revenue),
            "weeklyRevenue": float(weekly_revenue)
        }
        
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error in dashboard/stats endpoint: {e}", exc_info=True)
        return jsonify({"message": "Failed to load dashboard statistics."}), HTTPStatus.INTERNAL_SERVER_ERROR


# Skema Pydantic untuk notifikasi
class NotificationRecipientStatusSchema(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str
    is_subscribed: bool
    # model_config = ConfigDict(from_attributes=True) # Uncomment if used for ORM conversion

class NotificationRecipientUpdateSchema(BaseModel):
    notification_type: NotificationType
    subscribed_admin_ids: Optional[List[uuid.UUID]] = None

class NotificationUpdateResponseSchema(BaseModel):
    total_recipients: int


@admin_bp.route('/notification-recipients', methods=['GET'])
@super_admin_required
def get_notification_recipients(current_admin: User):
    """Retrieve list of notification recipients for new user registration."""
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

@admin_bp.route('/notification-recipients', methods=['POST'])
@super_admin_required
def update_notification_recipients(current_admin: User):
    """Update notification recipients for a specific notification type."""
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
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update notification recipients: {e}", exc_info=True)
        return jsonify({"message": "An internal error occurred while saving data."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/transactions', methods=['GET'])
@admin_required
def get_transactions_list(current_admin: User):
    """Retrieve a paginated, searchable, and filterable list of transactions."""
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
            # Join with User only if search_query is present and needs to search on User fields
            # This avoids unnecessary joins for purely transaction-related searches
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
                # Pastikan User.full_name hanya diakses jika join sudah dilakukan
                User.full_name.ilike(search_term) if Transaction.user_id is not None else False
            ]
            
            phone_variations = get_phone_number_variations(search_query)
            if phone_variations:
                for variation in phone_variations:
                    # Pastikan User.phone_number hanya diakses jika join sudah dilakukan
                    if Transaction.user_id is not None:
                        search_conditions.append(User.phone_number.ilike(f"%{variation}%"))
            else:
                # Pastikan User.phone_number hanya diakses jika join sudah dilakukan
                if Transaction.user_id is not None:
                    search_conditions.append(User.phone_number.ilike(search_term))
            
            query = query.where(or_(*search_conditions))

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

@admin_bp.route('/transactions/export', methods=['GET'])
@admin_required
def export_transactions(current_admin: User):
    """Endpoint for exporting transaction data (currently not implemented)."""
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

# --- Rute CRUD yang dihapus dari Model B: PROFILES ---
# @admin_bp.route('/profiles', methods=['GET'])
# @admin_required
# def get_profiles_list(current_admin: User):
#     """(Dihapus di Model A) Retrieve a list of package profiles, optionally paginated and searchable."""
#     return jsonify({"message": "Endpoint ini tidak tersedia di Model A."}), HTTPStatus.NOT_IMPLEMENTED

# @admin_bp.route('/profiles', methods=['POST'])
# @super_admin_required
# def create_profile(current_admin: User):
#     """(Dihapus di Model A) Create a new package profile."""
#     return jsonify({"message": "Endpoint ini tidak tersedia di Model A."}), HTTPStatus.NOT_IMPLEMENTED

# @admin_bp.route('/profiles/<uuid:profile_id>', methods=['PUT'])
# @super_admin_required
# def update_profile(current_admin: User, profile_id):
#     """(Dihapus di Model A) Update an existing package profile."""
#     return jsonify({"message": "Endpoint ini tidak tersedia di Model A."}), HTTPStatus.NOT_IMPLEMENTED

# @admin_bp.route('/profiles/<uuid:profile_id>', methods=['DELETE'])
# @super_admin_required
# def delete_profile(current_admin: User, profile_id):
#     """(Dihapus di Model A) Delete a package profile, preventing deletion if still used by packages."""
#     return jsonify({"message": "Endpoint ini tidak tersedia di Model A."}), HTTPStatus.NOT_IMPLEMENTED