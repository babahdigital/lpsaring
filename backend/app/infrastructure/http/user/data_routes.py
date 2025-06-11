# backend/app/infrastructure/http/user/data_routes.py
# Berisi endpoint yang menyajikan data dan statistik penggunaan untuk pengguna.

from flask import Blueprint, request, jsonify, abort, current_app
from sqlalchemy import select, desc, func
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from http import HTTPStatus

from app.extensions import db

# Impor model
from app.infrastructure.db.models import (
    User, DailyUsageLog, Transaction, TransactionStatus, Package, ApprovalStatus
)

# --- PERBAIKAN IMPORT PATH ---
# Impor skema dari direktori induk (http)
from ..schemas.user_schemas import (
    UserQuotaResponse, WeeklyUsageResponse,
    MonthlyUsageResponse, MonthlyUsageData
)

# Impor decorator dari direktori induk (http)
from ..decorators import token_required
# -----------------------------

# Impor helper dari path absolut (sudah benar)
from app.infrastructure.gateways.mikrotik_client import format_to_local_phone

# --- DEFINISI BLUEPRINT ---
data_bp = Blueprint('user_data_api', __name__, url_prefix='/api/users')

# --- Helper Function ---
def _get_authenticated_user(user_id):
    """Helper untuk mengambil dan memvalidasi user dari ID token."""
    user = db.session.get(User, user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")
    return user

# --- ENDPOINTS ---

@data_bp.route('/me/quota', methods=['GET'])
@token_required
def get_my_quota_status(current_user_id):
    current_app.logger.info(f"GET /api/users/me/quota requested by user ID: {current_user_id}")
    user = _get_authenticated_user(current_user_id)
    try:
        purchased_mb = int(user.total_quota_purchased_mb or 0)
        used_mb = int(user.total_quota_used_mb or 0)
        remaining_mb = max(0, purchased_mb - used_mb)
        hotspot_username = format_to_local_phone(user.phone_number)
        last_sync_time = user.updated_at

        quota_data = UserQuotaResponse(
            total_quota_purchased_mb=purchased_mb,
            total_quota_used_mb=used_mb,
            remaining_mb=remaining_mb,
            hotspot_username=hotspot_username,
            last_sync_time=last_sync_time,
            is_unlimited_user=user.is_unlimited_user,
            quota_expiry_date=user.quota_expiry_date
        )
        return jsonify(quota_data.model_dump(mode='json')), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"[Quota] Error saat memproses data kuota user {current_user_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data kuota.")

@data_bp.route('/me/weekly-usage', methods=['GET'])
@token_required
def get_my_weekly_usage(current_user_id):
    current_app.logger.info(f"GET /api/users/me/weekly-usage requested by user ID: {current_user_id}")
    _get_authenticated_user(current_user_id)
    try:
        today = date.today()
        start_date = today - timedelta(days=6)

        stmt = select(DailyUsageLog.log_date, DailyUsageLog.usage_mb)\
            .where(DailyUsageLog.user_id == current_user_id,
                   DailyUsageLog.log_date >= start_date,
                   DailyUsageLog.log_date <= today)\
            .order_by(DailyUsageLog.log_date.asc())

        usage_logs = db.session.execute(stmt).all()
        usage_dict = {log.log_date: float(log.usage_mb or 0.0) for log in usage_logs}

        weekly_data_points = []
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            usage = usage_dict.get(current_date, 0.0)
            weekly_data_points.append(max(0.0, usage))

        return jsonify(WeeklyUsageResponse(weekly_data=weekly_data_points).model_dump()), HTTPStatus.OK
    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[Weekly Usage] Error database user {current_user_id}: {e_sql}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil data penggunaan mingguan dari database.")
    except Exception as e:
        current_app.logger.error(f"[Weekly Usage] Error proses user {current_user_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data penggunaan mingguan.")

@data_bp.route('/me/monthly-usage', methods=['GET'])
@token_required
def get_my_monthly_usage(current_user_id):
    current_app.logger.info(f"GET /api/users/me/monthly-usage requested by user ID: {current_user_id}.")
    user = _get_authenticated_user(current_user_id)
    try:
        num_months_to_show = int(request.args.get('months', 12))
    except ValueError:
        num_months_to_show = 12
    num_months_to_show = min(max(num_months_to_show, 1), 24)

    today = date.today()
    first_day_of_current_month = today.replace(day=1)
    start_month_date_for_loop = first_day_of_current_month - relativedelta(months=(num_months_to_show - 1))

    month_year_col = func.to_char(DailyUsageLog.log_date, 'YYYY-MM').label('month_year')
    stmt = select(month_year_col, func.sum(DailyUsageLog.usage_mb).label('total_usage_mb'))\
        .where(DailyUsageLog.user_id == current_user_id, DailyUsageLog.log_date >= start_month_date_for_loop)\
        .group_by(month_year_col).order_by(month_year_col.asc())

    try:
        monthly_results = db.session.execute(stmt).all()
        usage_by_month_dict: Dict[str, float] = {row.month_year: float(row.total_usage_mb or 0.0) for row in monthly_results}
    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[Monthly Usage] Database query error for user {current_user_id}: {e_sql}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil data penggunaan bulanan dari database.")

    monthly_data_list: List[MonthlyUsageData] = []
    for i in range(num_months_to_show):
        current_loop_date = start_month_date_for_loop + relativedelta(months=i)
        month_year_str = current_loop_date.strftime('%Y-%m')
        usage = usage_by_month_dict.get(month_year_str, 0.0)
        monthly_data_list.append(MonthlyUsageData(month_year=month_year_str, usage_mb=max(0.0, usage)))

    return jsonify(MonthlyUsageResponse(monthly_data=monthly_data_list).model_dump(mode='json')), HTTPStatus.OK

@data_bp.route('/me/weekly-spending', methods=['GET'])
@token_required
def get_my_weekly_spending_summary(current_user_id):
    current_app.logger.info(f"GET /api/users/me/weekly-spending requested by user ID: {current_user_id}")
    _get_authenticated_user(current_user_id)
    try:
        today = date.today()
        day_names_id = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"]
        categories = []
        daily_spending_data = []
        total_this_week = 0.0
        
        for i in range(7):
            current_date_in_loop = today - timedelta(days=(6 - i))
            categories.append(day_names_id[current_date_in_loop.weekday()])
            daily_total_query = db.session.query(func.sum(Transaction.amount))\
                .filter(Transaction.user_id == current_user_id, Transaction.status == TransactionStatus.SUCCESS,
                        func.date(Transaction.payment_time) == current_date_in_loop).scalar()
            daily_total = float(daily_total_query or 0.0)
            daily_spending_data.append(daily_total)
            total_this_week += daily_total

        response_data = {"success": True, "categories": categories, "series": [{"name": "Pengeluaran", "data": daily_spending_data}], "total_this_week": total_this_week}
        return jsonify(response_data), HTTPStatus.OK
    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[WeeklySpending] Error database user {current_user_id}: {e_sql}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal mengambil data pengeluaran mingguan dari database."}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        current_app.logger.error(f"[WeeklySpending] Error proses user {current_user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal memproses data pengeluaran mingguan."}), HTTPStatus.INTERNAL_SERVER_ERROR

@data_bp.route('/me/transactions', methods=['GET'])
@token_required
def get_my_transactions(current_user_id):
    current_app.logger.info(f"GET /api/users/me/transactions requested by user ID: {current_user_id}")
    _get_authenticated_user(current_user_id)
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc').lower()

        valid_sort_keys = {'created_at': Transaction.created_at, 'amount': Transaction.amount, 'status': Transaction.status}
        sort_column = valid_sort_keys.get(sort_by, Transaction.created_at)
        query_order = desc(sort_column) if sort_order == 'desc' else sort_column.asc()

        query = db.session.query(Transaction, Package.name).join(Package, Transaction.package_id == Package.id)\
            .filter(Transaction.user_id == current_user_id).order_by(query_order)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        transactions_data = [{
            'id': str(tx.id), 'midtrans_order_id': tx.midtrans_order_id, 'package_name': pkg_name,
            'amount': float(tx.amount), 'status': tx.status.name, 'payment_method': tx.payment_method,
            'created_at': tx.created_at.isoformat(), 'updated_at': tx.updated_at.isoformat(),
            'payment_expiry_time': tx.expiry_time.isoformat() if tx.expiry_time else None,
            'payment_settlement_time': tx.payment_time.isoformat() if tx.payment_time else None
        } for tx, pkg_name in pagination.items]

        return jsonify({
            'success': True, 'transactions': transactions_data,
            'pagination': {'page': pagination.page, 'per_page': pagination.per_page, 'total_pages': pagination.pages, 'total_items': pagination.total}
        }), HTTPStatus.OK
    except SQLAlchemyError as e_sql:
         current_app.logger.error(f"[Transactions] Error database user {current_user_id}: {e_sql}", exc_info=True)
         abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil riwayat transaksi dari database.")
    except Exception as e:
        current_app.logger.error(f"[Transactions] Error proses user {current_user_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data riwayat transaksi.")