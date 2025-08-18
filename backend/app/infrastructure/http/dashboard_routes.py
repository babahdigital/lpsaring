# backend/app/infrastructure/http/dashboard_routes.py
# PENYEMPURNAAN: Beralih ke Flask-JWT-Extended untuk autentikasi.

from flask import Blueprint, jsonify, request, abort, current_app
from sqlalchemy import select, desc, func
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from http import HTTPStatus
from flask_jwt_extended import jwt_required, get_current_user # [PERBAIKAN] Impor baru

from app.extensions import db
from app.infrastructure.db.models import User, DailyUsageLog, Transaction, TransactionStatus
from .schemas.user_schemas import UserQuotaResponse, WeeklyUsageResponse, MonthlyUsageResponse, MonthlyUsageData
# [DIHAPUS] Impor decorator lama tidak diperlukan lagi.
# from .decorators import token_required

dashboard_bp = Blueprint('dashboard_api', __name__)

@dashboard_bp.route('/quota', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_quota_status():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        quota_data = UserQuotaResponse.model_validate(current_user)
        return jsonify(quota_data.model_dump(mode='json')), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_quota_status: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data kuota.")

@dashboard_bp.route('/weekly-usage', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_weekly_usage():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        today = date.today()
        start_date = today - timedelta(days=6)
        stmt = select(DailyUsageLog.log_date, DailyUsageLog.usage_mb)\
            .where(DailyUsageLog.user_id == current_user.id, DailyUsageLog.log_date >= start_date)\
            .order_by(DailyUsageLog.log_date.asc())
        
        usage_logs = db.session.execute(stmt).all()
        usage_dict = {log.log_date: float(log.usage_mb or 0.0) for log in usage_logs}
        
        weekly_data_points = [usage_dict.get(start_date + timedelta(days=i), 0.0) for i in range(7)]
        
        response_data = WeeklyUsageResponse(weekly_data=weekly_data_points)
        return jsonify(response_data.model_dump()), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_weekly_usage: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data penggunaan mingguan.")

@dashboard_bp.route('/monthly-usage', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_monthly_usage():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        num_months_to_show = int(request.args.get('months', 12))
        num_months_to_show = min(max(num_months_to_show, 1), 24)
        today = date.today()
        start_month_date = (today.replace(day=1) - relativedelta(months=(num_months_to_show - 1)))
        
        month_year_col = func.to_char(DailyUsageLog.log_date, 'YYYY-MM').label('month_year')
        stmt = select(month_year_col, func.sum(DailyUsageLog.usage_mb).label('total_usage_mb'))\
            .where(DailyUsageLog.user_id == current_user.id, DailyUsageLog.log_date >= start_month_date)\
            .group_by(month_year_col).order_by(month_year_col.asc())
        
        usage_by_month_dict = {row.month_year: float(row.total_usage_mb or 0.0) for row in db.session.execute(stmt).all()}
        
        monthly_data_list = []
        for i in range(num_months_to_show):
            current_loop_date = start_month_date + relativedelta(months=i)
            month_year_str = current_loop_date.strftime('%Y-%m')
            usage = usage_by_month_dict.get(month_year_str, 0.0)
            monthly_data_list.append(MonthlyUsageData(month_year=month_year_str, usage_mb=usage))
        
        response_data = MonthlyUsageResponse(monthly_data=monthly_data_list)
        return jsonify(response_data.model_dump(mode='json')), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_monthly_usage: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data penggunaan bulanan.")

@dashboard_bp.route('/weekly-spending', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_weekly_spending_summary():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        today = date.today()
        categories = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"]
        day_of_week_today = today.isoweekday() % 7 
        ordered_categories = [categories[(day_of_week_today - 6 + i) % 7] for i in range(7)]
        
        daily_spending_data = [0.0] * 7
        total_this_week = 0.0
        
        start_date = today - timedelta(days=6)
        
        stmt = select(func.date(Transaction.payment_time).label('payment_date'), func.sum(Transaction.amount).label('daily_total'))\
            .where(
                Transaction.user_id == current_user.id,
                Transaction.status == TransactionStatus.SUCCESS,
                func.date(Transaction.payment_time) >= start_date
            ).group_by('payment_date')

        results = db.session.execute(stmt).all()
        spending_dict = {res.payment_date: float(res.daily_total) for res in results}
        
        for i in range(7):
            current_date_in_loop = today - timedelta(days=(6 - i))
            spending = spending_dict.get(current_date_in_loop, 0.0)
            daily_spending_data[i] = spending
            total_this_week += spending

        return jsonify({
            "categories": ordered_categories, 
            "series": [{"name": "Pengeluaran", "data": daily_spending_data}], 
            "total_this_week": total_this_week
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_weekly_spending_summary: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses data pengeluaran mingguan.")