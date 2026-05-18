# backend/app/infrastructure/http/admin/action_log_routes.py

from flask import Blueprint, jsonify, request, current_app, Response
from sqlalchemy import select, func, or_
from sqlalchemy.orm import aliased, contains_eager
from http import HTTPStatus
import json
import csv
import io
from datetime import datetime, timezone as dt_timezone

from app.extensions import db
from app.infrastructure.db.models import AdminActionLog, User
from app.infrastructure.http.decorators import admin_required, super_admin_required
from .schemas import AdminActionLogResponseSchema
from app.utils.formatters import format_app_datetime, format_app_date


def _parse_admin_date_to_utc(date_str: str, end_of_day: bool = False) -> datetime:
    """Sprint 25 BUG-1: Parse `YYYY-MM-DD` dari admin input → datetime aware UTC.

    Admin client kirim "2026-01-01" mengacu ke tanggal lokal WITA. Sebelumnya
    `datetime.fromisoformat(...)` return naive → Postgres TIMESTAMPTZ
    interpret sebagai UTC → effective filter mundur 8 jam dari intent admin.

    Cara fix: parse sebagai date lokal app (WITA), set jam awal/akhir, lalu
    convert ke UTC supaya aware datetime cocok dengan `DateTime(timezone=True)`
    column type.
    """
    date_part = date_str.split("T")[0]
    naive = datetime.fromisoformat(date_part + ("T23:59:59.999999" if end_of_day else "T00:00:00"))
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        tz_name = current_app.config.get("APP_TIMEZONE", "Asia/Makassar")
        local_aware = naive.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        # Fallback: anggap UTC bila ZoneInfo gagal.
        local_aware = naive.replace(tzinfo=dt_timezone.utc)
    return local_aware.astimezone(dt_timezone.utc)


action_log_bp = Blueprint("action_log_api", __name__)


def _build_log_query(apply_filters=True):
    """Helper function untuk membangun query dasar log dengan filter."""
    AdminUser = aliased(User, name="admin_user")
    TargetUser = aliased(User, name="target_user")

    query = (
        select(AdminActionLog)
        .outerjoin(AdminUser, AdminActionLog.admin_id == AdminUser.id)
        .outerjoin(TargetUser, AdminActionLog.target_user_id == TargetUser.id)
        .options(
            contains_eager(AdminActionLog.admin.of_type(AdminUser)),
            contains_eager(AdminActionLog.target_user.of_type(TargetUser)),
        )
    )

    if apply_filters:
        search_query = request.args.get("search", "").strip()
        source_filter = request.args.get("source", "").strip()
        admin_id = request.args.get("admin_id")
        target_user_id = request.args.get("target_user_id")
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")

        if search_query:
            search_term = f"%{search_query}%"
            # [PERBAIKAN] Pencarian pada beberapa kolom, bukan hanya 'details'
            query = query.where(
                or_(
                    AdminActionLog.details.ilike(search_term),
                    AdminActionLog.action_type.ilike(search_term),
                    AdminUser.full_name.ilike(search_term),
                    TargetUser.full_name.ilike(search_term),
                )
            )

        if source_filter:
            query = query.where(AdminActionLog.details.ilike(f"%{source_filter}%"))

        if admin_id:
            query = query.where(AdminActionLog.admin_id == admin_id)
        if target_user_id:
            query = query.where(AdminActionLog.target_user_id == target_user_id)
        if start_date_str:
            try:
                # Sprint 25 BUG-1: parse sebagai date WITA → convert ke UTC
                # supaya filter dengan TIMESTAMPTZ column tidak mundur 8 jam.
                start_date = _parse_admin_date_to_utc(start_date_str, end_of_day=False)
                query = query.where(AdminActionLog.created_at >= start_date)
            except (ValueError, TypeError):
                pass  # Abaikan jika format tanggal salah
        if end_date_str:
            try:
                end_date = _parse_admin_date_to_utc(end_date_str, end_of_day=True)
                query = query.where(AdminActionLog.created_at <= end_date)
            except (ValueError, TypeError):
                pass  # Abaikan jika format tanggal salah

    return query


@action_log_bp.route("/action-logs", methods=["GET"])
@admin_required
def get_action_logs(current_admin: User):  # noqa: ARG001
    """Endpoint untuk mengambil log aktivitas admin dengan paginasi dan filter lengkap."""
    try:
        # [PERBAIKAN UTAMA] Logika untuk menangani itemsPerPage = -1
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("itemsPerPage", 15, type=int)
        # Audit-6: Hard cap supaya admin tidak bisa request unbounded result yang
        # OOM gunicorn worker (admin_action_logs bisa ribuan baris). -1 / 0 → cap.
        _MAX_ITEMS_PER_PAGE = 200
        if per_page <= 0 or per_page > _MAX_ITEMS_PER_PAGE:
            per_page = _MAX_ITEMS_PER_PAGE

        sort_by_key = request.args.get("sortBy", "created_at")
        sort_order = request.args.get("sortOrder", "desc")

        base_query = _build_log_query()

        # Pemetaan untuk sorting pada kolom relasi
        sortable_columns = {
            "created_at": AdminActionLog.created_at,
            "action_type": AdminActionLog.action_type,
            "admin": aliased(User, name="admin_user").full_name,
            "target_user": aliased(User, name="target_user").full_name,
        }

        sort_column = sortable_columns.get(sort_by_key, AdminActionLog.created_at)
        base_query = base_query.order_by(sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc())

        # Hitung total item sebelum paginasi
        count_query = select(func.count()).select_from(base_query.subquery())
        total_items = db.session.scalar(count_query) or 0

        # Audit-6: per_page sudah di-cap di atas, selalu apply limit/offset.
        paginated_query = base_query.offset((page - 1) * per_page).limit(per_page)

        logs = db.session.scalars(paginated_query).unique().all()

        logs_data = [AdminActionLogResponseSchema.model_validate(log).model_dump(mode="json") for log in logs]

        return jsonify({"items": logs_data, "totalItems": total_items}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data log."}), HTTPStatus.INTERNAL_SERVER_ERROR


@action_log_bp.route("/action-logs/export", methods=["GET"])
@admin_required
def export_action_logs(current_admin: User):  # noqa: ARG001
    """Endpoint untuk mengekspor log ke format CSV atau TXT."""
    file_format = request.args.get("format", "csv").lower()

    try:
        # Audit-6: Hard cap supaya export tidak OOM gunicorn worker pada DB besar.
        # Admin perlu filter date range bila log > MAX_EXPORT_ROWS.
        _MAX_EXPORT_ROWS = 50_000
        base_query = _build_log_query().order_by(AdminActionLog.created_at.desc())

        count_query = select(func.count()).select_from(base_query.subquery())
        total_rows = int(db.session.scalar(count_query) or 0)
        if total_rows > _MAX_EXPORT_ROWS:
            return jsonify(
                {
                    "message": (
                        f"Export ditolak: total {total_rows} baris melebihi batas {_MAX_EXPORT_ROWS}. "
                        "Persempit dengan filter rentang tanggal atau admin tertentu."
                    )
                }
            ), HTTPStatus.UNPROCESSABLE_ENTITY

        logs = db.session.scalars(base_query.limit(_MAX_EXPORT_ROWS)).unique().all()

        output = io.StringIO()
        if file_format == "csv":
            writer = csv.writer(output)
            writer.writerow(
                ["Waktu", "Admin Pelaku", "No. HP Admin", "Aksi", "Detail Aksi", "Target Pengguna", "No. HP Target"]
            )

            def _csv_safe(value):
                """Sprint 25: CSV formula injection prevention.
                Excel/LibreOffice eksekusi formula bila cell dimulai dengan
                `=`, `+`, `-`, `@`. Prefix dengan apostrophe supaya jadi text.
                """
                if value is None:
                    return ""
                text = str(value)
                if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
                    return "'" + text
                return text

            for log in logs:
                writer.writerow(
                    [
                        _csv_safe(format_app_datetime(log.created_at)),
                        _csv_safe(log.admin.full_name if log.admin else "N/A"),
                        _csv_safe(log.admin.phone_number if log.admin else "N/A"),
                        _csv_safe(log.action_type.value if log.action_type else "N/A"),
                        _csv_safe(json.dumps(log.details) if isinstance(log.details, dict) else log.details),
                        _csv_safe(log.target_user.full_name if log.target_user else "N/A"),
                        _csv_safe(log.target_user.phone_number if log.target_user else "N/A"),
                    ]
                )
            mimetype = "text/csv"
            filename = f"log_aktivitas_{format_app_date(datetime.now()).replace('-', '')}.csv"
        else:  # TXT format
            for log in logs:
                output.write(f"Waktu         : {format_app_datetime(log.created_at)}\n")
                output.write(f"Admin Pelaku  : {log.admin.full_name if log.admin else 'N/A'}\n")
                output.write(f"Aksi          : {log.action_type.value if log.action_type else 'N/A'}\n")
                output.write(
                    f"Detail        : {json.dumps(log.details) if isinstance(log.details, dict) else log.details}\n"
                )
                output.write(f"Target        : {log.target_user.full_name if log.target_user else 'N/A'}\n")
                output.write("-" * 30 + "\n")
            mimetype = "text/plain"
            filename = f"log_aktivitas_{format_app_date(datetime.now()).replace('-', '')}.txt"

        return Response(
            output.getvalue(), mimetype=mimetype, headers={"Content-disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        current_app.logger.error(f"Error exporting action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengekspor data log."}), HTTPStatus.INTERNAL_SERVER_ERROR


@action_log_bp.route("/action-logs", methods=["DELETE"])
@super_admin_required
def clear_all_logs(current_admin: User):
    """Endpoint untuk menghapus log aktivitas. Mendukung filter tanggal opsional."""
    try:
        before_date_str = request.args.get("before_date")
        query = db.session.query(AdminActionLog)
        if before_date_str:
            try:
                # Sprint 25 BUG-1: parse ke UTC aware supaya tidak under-delete
                # 8 jam (admin pikir delete sampai jam 23:59 WITA → kena 15:59 UTC).
                before_date = _parse_admin_date_to_utc(before_date_str, end_of_day=True)
                query = query.filter(AdminActionLog.created_at <= before_date)
            except (ValueError, TypeError):
                return jsonify({"message": "Format before_date tidak valid (YYYY-MM-DD)."}), HTTPStatus.BAD_REQUEST
        num_deleted = query.delete(synchronize_session=False)
        db.session.commit()
        scope = f" sebelum {before_date_str}" if before_date_str else ""
        current_app.logger.info(f"Super Admin {current_admin.full_name} cleared {num_deleted} action logs{scope}.")
        return jsonify({"message": f"Berhasil menghapus {num_deleted} catatan log{scope}."}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing action logs: {e}", exc_info=True)
        return jsonify({"message": "Gagal menghapus log."}), HTTPStatus.INTERNAL_SERVER_ERROR
