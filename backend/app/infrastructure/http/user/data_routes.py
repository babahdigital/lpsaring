# backend/app/infrastructure/http/user/data_routes.py
# Berisi endpoint yang menyajikan data dan statistik penggunaan untuk pengguna.

from flask import Blueprint, request, jsonify, abort, current_app
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from http import HTTPStatus
import uuid

from app.extensions import db
from app.infrastructure.db.models import (
    User, DailyUsageLog, Transaction, TransactionStatus, Package, ApprovalStatus
)
from ..schemas.user_schemas import (
    UserQuotaResponse, WeeklyUsageResponse,
    MonthlyUsageResponse, MonthlyUsageData
)
from ..decorators import token_required

from app.utils.formatters import format_to_local_phone

data_bp = Blueprint('user_data_api', __name__, url_prefix='/api/users')

def _get_authenticated_user(user_id):
    """Helper untuk mengambil dan memvalidasi user dari ID token."""
    user = db.session.get(User, user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")
    return user

@data_bp.route('/me/quota', methods=['GET'])
@token_required
def get_my_quota_status(current_user_id):
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
        current_app.logger.error(f"Error pada get_my_quota_status: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data kuota.")

@data_bp.route('/me/weekly-usage', methods=['GET'])
@token_required
def get_my_weekly_usage(current_user_id):
    _get_authenticated_user(current_user_id)
    try:
        today = date.today()
        start_date = today - timedelta(days=6)
        stmt = select(DailyUsageLog.log_date, DailyUsageLog.usage_mb)\
            .where(DailyUsageLog.user_id == current_user_id, DailyUsageLog.log_date >= start_date, DailyUsageLog.log_date <= today)\
            .order_by(DailyUsageLog.log_date.asc())
        usage_logs = db.session.execute(stmt).all()
        usage_dict = {log.log_date: float(log.usage_mb or 0.0) for log in usage_logs}
        weekly_data_points = [usage_dict.get(start_date + timedelta(days=i), 0.0) for i in range(7)]
        return jsonify(WeeklyUsageResponse(weekly_data=weekly_data_points).model_dump()), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_weekly_usage: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data penggunaan mingguan.")


@data_bp.route('/me/monthly-usage', methods=['GET'])
@token_required
def get_my_monthly_usage(current_user_id):
    user = _get_authenticated_user(current_user_id)
    try:
        num_months_to_show = int(request.args.get('months', 12))
        num_months_to_show = min(max(num_months_to_show, 1), 24)
        today = date.today()
        start_month_date = (today.replace(day=1) - relativedelta(months=(num_months_to_show - 1)))
        
        month_year_col = func.to_char(DailyUsageLog.log_date, 'YYYY-MM').label('month_year')
        stmt = select(month_year_col, func.sum(DailyUsageLog.usage_mb).label('total_usage_mb'))\
            .where(DailyUsageLog.user_id == current_user_id, DailyUsageLog.log_date >= start_month_date)\
            .group_by(month_year_col).order_by(month_year_col.asc())
        
        usage_by_month_dict = {row.month_year: float(row.total_usage_mb or 0.0) for row in db.session.execute(stmt).all()}
        
        monthly_data_list = []
        for i in range(num_months_to_show):
            current_loop_date = start_month_date + relativedelta(months=i)
            month_year_str = current_loop_date.strftime('%Y-%m')
            usage = usage_by_month_dict.get(month_year_str, 0.0)
            monthly_data_list.append(MonthlyUsageData(month_year=month_year_str, usage_mb=usage))
        
        return jsonify(MonthlyUsageResponse(monthly_data=monthly_data_list).model_dump(mode='json')), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_monthly_usage: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data penggunaan bulanan.")

@data_bp.route('/me/weekly-spending', methods=['GET'])
@token_required
def get_my_weekly_spending_summary(current_user_id):
    _get_authenticated_user(current_user_id)
    try:
        today = date.today()
        categories = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"]
        daily_spending_data = []
        total_this_week = 0.0
        
        for i in range(7):
            current_date_in_loop = today - timedelta(days=(6 - i))
            daily_total = db.session.scalar(select(func.sum(Transaction.amount)).where(
                Transaction.user_id == current_user_id,
                Transaction.status == TransactionStatus.SUCCESS,
                func.date(Transaction.payment_time) == current_date_in_loop
            )) or 0.0
            daily_spending_data.append(float(daily_total))
            total_this_week += float(daily_total)

        return jsonify({"categories": categories, "series": [{"name": "Pengeluaran", "data": daily_spending_data}], "total_this_week": total_this_week}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_weekly_spending_summary: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data pengeluaran mingguan.")

@data_bp.route('/me/transactions', methods=['GET'])
@token_required
def get_my_transactions(current_user_id):
    _get_authenticated_user(current_user_id)
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        query = select(Transaction).options(
            selectinload(Transaction.package)
        ).where(Transaction.user_id == current_user_id).order_by(desc(Transaction.created_at))
            
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

        transactions_data = []
        for tx in pagination.items:
            pkg_name = tx.package.name if tx.package else 'Paket Tidak Ditemukan'
            
            transactions_data.append({
                'id': str(tx.id),
                'midtrans_order_id': tx.midtrans_order_id,
                'package_name': pkg_name,
                'amount': float(tx.amount if tx.amount is not None else 0.0),
                'status': tx.status.value if tx.status else 'UNKNOWN',
                'payment_method': tx.payment_method,
                'created_at': tx.created_at.isoformat() if tx.created_at else None,
                'updated_at': tx.updated_at.isoformat() if tx.updated_at else None
            })

        # --- PERBAIKAN FINAL: Menambahkan 'success: True' pada respons ---
        return jsonify({
            "success": True, # Kunci ini yang ditunggu oleh frontend
            'transactions': transactions_data,
            'pagination': {
                'page': pagination.page, 
                'per_page': pagination.per_page, 
                'total_pages': pagination.pages, 
                'total_items': pagination.total
            }
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_transactions: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil riwayat transaksi.")