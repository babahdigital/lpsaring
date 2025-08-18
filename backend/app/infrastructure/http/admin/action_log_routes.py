# backend/app/infrastructure/http/admin/action_log_routes.py
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false

from flask import Blueprint, jsonify, request, current_app, Response
from sqlalchemy import select, func, or_
from sqlalchemy.orm import aliased, contains_eager
from http import HTTPStatus
import json
import csv
import io
from datetime import datetime

from app.extensions import db
from app.infrastructure.db.models import AdminActionLog, User, AdminActionType
from app.infrastructure.http.decorators import admin_required, super_admin_required
from app.infrastructure.http.schemas.api_schemas import AdminActionLogResponseSchema

action_log_bp = Blueprint('action_log_api', __name__)

def _build_log_query(apply_filters=True):
    """Helper function untuk membangun query dasar log dengan filter."""
    AdminUser = aliased(User, name='admin_user')
    TargetUser = aliased(User, name='target_user')

    query = (
        select(AdminActionLog)
        .outerjoin(AdminUser, AdminActionLog.admin_id == AdminUser.id)
        .outerjoin(TargetUser, AdminActionLog.target_user_id == TargetUser.id)
        .options(
            contains_eager(AdminActionLog.admin.of_type(AdminUser)),
            contains_eager(AdminActionLog.target_user.of_type(TargetUser))
        )
    )

    if apply_filters:
        search_query = request.args.get('search', '').strip()
        admin_id = request.args.get('admin_id')
        target_user_id = request.args.get('target_user_id')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        if search_query:
            search_term = f"%{search_query}%"
            # [PERBAIKAN] Pencarian pada beberapa kolom, bukan hanya 'details'
            query = query.where(or_(
                AdminActionLog.details.ilike(search_term),
                AdminActionLog.action_type.ilike(search_term),
                AdminUser.full_name.ilike(search_term),
                TargetUser.full_name.ilike(search_term)
            ))

        if admin_id:
            query = query.where(AdminActionLog.admin_id == admin_id)
        if target_user_id:
            query = query.where(AdminActionLog.target_user_id == target_user_id)
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.split('T')[0] + "T00:00:00")
                query = query.where(AdminActionLog.created_at >= start_date)
            except (ValueError, TypeError):
                pass # Abaikan jika format tanggal salah
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.split('T')[0] + "T23:59:59")
                query = query.where(AdminActionLog.created_at <= end_date)
            except (ValueError, TypeError):
                pass # Abaikan jika format tanggal salah
            
    return query

@action_log_bp.route('/action-logs', methods=['GET'])
@admin_required
def get_action_logs(current_admin: User):
    """Endpoint untuk mengambil log aktivitas admin dengan paginasi dan filter lengkap."""
    try:
        # [PERBAIKAN UTAMA] Logika untuk menangani itemsPerPage = -1
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('itemsPerPage', 15, type=int)
        
        sort_by_key = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')

        base_query = _build_log_query()

        # Pemetaan untuk sorting pada kolom relasi
        sortable_columns = {
            'created_at': AdminActionLog.created_at,
            'action_type': AdminActionLog.action_type,
            'admin': aliased(User, name='admin_user').full_name,
            'target_user': aliased(User, name='target_user').full_name,
        }
        
        sort_column = sortable_columns.get(sort_by_key, AdminActionLog.created_at)
        base_query = base_query.order_by(sort_column.desc() if sort_order.lower() == 'desc' else sort_column.asc())
        
        # Hitung total item sebelum paginasi
        count_query = select(func.count(AdminActionLog.id)).select_from(base_query.subquery())
        total_items = db.session.scalar(count_query) or 0
        
        # Terapkan paginasi hanya jika per_page positif
        if per_page > 0:
            paginated_query = base_query.offset((page - 1) * per_page).limit(per_page)
        else:
            # Jika per_page adalah -1 (atau nilai negatif lainnya), ambil semua data
            paginated_query = base_query
        
        logs = db.session.scalars(paginated_query).unique().all()
        
        logs_data = [AdminActionLogResponseSchema.from_orm(log).model_dump(mode='json') for log in logs]
        
        return jsonify({"items": logs_data, "totalItems": total_items}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data log."}), HTTPStatus.INTERNAL_SERVER_ERROR

@action_log_bp.route('/action-logs/export', methods=['GET'])
@admin_required
def export_action_logs(current_admin: User):
    """Endpoint untuk mengekspor log ke format CSV atau TXT."""
    file_format = request.args.get('format', 'csv').lower()
    
    try:
        # Untuk ekspor, kita selalu ambil semua log tanpa limit
        base_query = _build_log_query().order_by(AdminActionLog.created_at.desc())
        logs = db.session.scalars(base_query).unique().all()

        output = io.StringIO()
        if file_format == 'csv':
            writer = csv.writer(output)
            writer.writerow(['Waktu', 'Admin Pelaku', 'No. HP Admin', 'Aksi', 'Detail Aksi', 'Target Pengguna', 'No. HP Target'])
            for log in logs:
                writer.writerow([
                    log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    log.admin.full_name if log.admin else 'N/A',
                    log.admin.phone_number if log.admin else 'N/A',
                    log.action_type.value if log.action_type else 'N/A',
                    json.dumps(log.details) if isinstance(log.details, dict) else log.details,
                    log.target_user.full_name if log.target_user else 'N/A',
                    log.target_user.phone_number if log.target_user else 'N/A'
                ])
            mimetype = 'text/csv'
            filename = f'log_aktivitas_{datetime.now().strftime("%Y%m%d")}.csv'
        else: # TXT format
            for log in logs:
                output.write(f"Waktu         : {log.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
                output.write(f"Admin Pelaku  : {log.admin.full_name if log.admin else 'N/A'}\n")
                output.write(f"Aksi          : {log.action_type.value if log.action_type else 'N/A'}\n")
                output.write(f"Detail        : {json.dumps(log.details) if isinstance(log.details, dict) else log.details}\n")
                output.write(f"Target        : {log.target_user.full_name if log.target_user else 'N/A'}\n")
                output.write("-" * 30 + "\n")
            mimetype = 'text/plain'
            filename = f'log_aktivitas_{datetime.now().strftime("%Y%m%d")}.txt'
            
        return Response(
            output.getvalue(),
            mimetype=mimetype,
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        current_app.logger.error(f"Error exporting action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengekspor data log."}), HTTPStatus.INTERNAL_SERVER_ERROR

@action_log_bp.route('/action-logs', methods=['DELETE'])
@super_admin_required
def clear_all_logs(current_admin: User):
    """Endpoint untuk menghapus semua log aktivitas."""
    try:
        num_deleted = db.session.query(AdminActionLog).delete()
        db.session.commit()
        current_app.logger.info(f"Super Admin {current_admin.full_name} cleared all ({num_deleted}) action logs.")
        return jsonify({"message": f"Berhasil menghapus {num_deleted} catatan log."}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal menghapus log."}), HTTPStatus.INTERNAL_SERVER_ERROR