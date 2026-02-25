# backend/app/infrastructure/http/admin/admin_routes.py
from flask import Blueprint, jsonify, current_app
from sqlalchemy import func, or_, select, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone as dt_timezone, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from http import HTTPStatus
from decimal import Decimal
import json
import uuid
import os
import pathlib
import subprocess  # noqa: F401
from sqlalchemy.engine import make_url

from app.extensions import db
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.infrastructure.gateways.telegram_client import send_telegram_message
from app.infrastructure.db.models import (
    User,
    UserRole,
    Package,
    ApprovalStatus,
    Transaction,
    TransactionStatus,
    AdminActionLog,
    AdminActionType,
    QuotaRequest,
    RequestStatus,
    TransactionEvent,
    TransactionEventSource,
)
from .decorators import admin_required, super_admin_required
from .transactions_routes import (
    extract_action_url,
    extract_qr_code_url,
    extract_va_number,
    get_midtrans_core_api_client,
    get_midtrans_snap_client,
    safe_parse_midtrans_datetime,
)
from .admin_contexts.backups import (
    list_backups_impl,
    create_backup_impl,
    download_backup_impl,
    upload_backup_impl,
    restore_backup_impl,
)
from .admin_contexts.notifications import (
    send_whatsapp_test_impl,
    send_telegram_test_impl,
    send_whatsapp_broadcast_impl,
    get_notification_recipients_impl,
    update_notification_recipients_impl,
)
from .admin_contexts.transactions import (
    get_transactions_list_impl,
    get_transaction_detail_impl,
    export_transactions_impl,
)
from .admin_contexts.billing import create_bill_impl, midtrans_selftest_impl
from .admin_contexts.reports import get_transaction_admin_report_pdf_impl
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations, format_to_local_phone
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package

admin_bp = Blueprint("admin_api", __name__)

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    WEASYPRINT_AVAILABLE = False


def _get_local_tz() -> dt_timezone:
    try:
        offset_hours = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))
    except Exception:
        offset_hours = 8
    offset_hours = max(-12, min(offset_hours, 14))
    return dt_timezone(timedelta(hours=offset_hours))


def _parse_local_date_range_to_utc(start_date_str: str, end_date_str: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM-DD as *local dates* and return [start_utc, end_utc) datetime range."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    if end_date < start_date:
        raise ValueError("end_date < start_date")

    local_tz = _get_local_tz()
    start_local = datetime.combine(start_date, dt_time.min).replace(tzinfo=local_tz)
    end_local = datetime.combine(end_date + timedelta(days=1), dt_time.min).replace(tzinfo=local_tz)
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)


def _format_dt_local(value: datetime | None, *, with_seconds: bool = False) -> str:
    if not value:
        return "-"
    try:
        if getattr(value, "tzinfo", None) is None:
            value = value.replace(tzinfo=dt_timezone.utc)
        local_tz = _get_local_tz()
        local_dt = value.astimezone(local_tz)
        fmt = "%d %b %Y %H:%M:%S" if with_seconds else "%d %b %Y %H:%M"
        offset_hours = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8) or 8)
        sign = "+" if offset_hours >= 0 else "-"
        tz_label = current_app.config.get("APP_TIMEZONE_LABEL") or "WITA"
        return f"{local_dt.strftime(fmt)} {tz_label} (UTC{sign}{abs(offset_hours)})"
    except Exception:
        try:
            return value.isoformat()
        except Exception:
            return "-"


def _get_backup_dir() -> str:
    backup_dir = current_app.config.get("BACKUP_DIR", "/app/backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _build_pg_dump_command(output_path: str) -> list[str]:
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        raise RuntimeError("DATABASE_URL tidak disetel")

    url = make_url(db_url)
    if url.drivername not in ("postgresql", "postgresql+psycopg2"):
        raise RuntimeError("Backup hanya didukung untuk PostgreSQL")

    if not url.username or not url.database:
        raise RuntimeError("Konfigurasi database tidak lengkap untuk backup")

    host = url.host or "localhost"
    port = url.port or 5432
    return [
        "pg_dump",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        url.username,
        "-F",
        "c",
        "-f",
        output_path,
        url.database,
    ]


def _build_pg_restore_command(input_path: str) -> list[str]:
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        raise RuntimeError("DATABASE_URL tidak disetel")

    url = make_url(db_url)
    if url.drivername not in ("postgresql", "postgresql+psycopg2"):
        raise RuntimeError("Restore hanya didukung untuk PostgreSQL")

    if not url.username or not url.database:
        raise RuntimeError("Konfigurasi database tidak lengkap untuk restore")

    host = url.host or "localhost"
    port = url.port or 5432
    return [
        "pg_restore",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        url.username,
        "-d",
        url.database,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        input_path,
    ]


def _build_psql_restore_command(input_path: str) -> list[str]:
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        raise RuntimeError("DATABASE_URL tidak disetel")

    url = make_url(db_url)
    if url.drivername not in ("postgresql", "postgresql+psycopg2"):
        raise RuntimeError("Restore hanya didukung untuk PostgreSQL")

    if not url.username or not url.database:
        raise RuntimeError("Konfigurasi database tidak lengkap untuk restore")

    host = url.host or "localhost"
    port = url.port or 5432
    return [
        "psql",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        url.username,
        "-d",
        url.database,
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        input_path,
    ]


def _build_psql_statement_command(statement: str) -> list[str]:
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        raise RuntimeError("DATABASE_URL tidak disetel")

    url = make_url(db_url)
    if url.drivername not in ("postgresql", "postgresql+psycopg2"):
        raise RuntimeError("Restore hanya didukung untuk PostgreSQL")

    if not url.username or not url.database:
        raise RuntimeError("Konfigurasi database tidak lengkap untuk restore")

    host = url.host or "localhost"
    port = url.port or 5432
    return [
        "psql",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        url.username,
        "-d",
        url.database,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        statement,
    ]


def _sanitize_sql_dump_for_restore(file_path: pathlib.Path) -> tuple[pathlib.Path, int]:
    original_content = file_path.read_text(encoding="utf-8", errors="replace")
    filtered_lines = []
    removed_lines = 0
    for line in original_content.splitlines(keepends=True):
        if line.lstrip().startswith("pg_dump:"):
            removed_lines += 1
            continue
        filtered_lines.append(line)

    if removed_lines == 0:
        return file_path, 0

    sanitized_name = f"{file_path.stem}.sanitized_{uuid.uuid4().hex}{file_path.suffix}"
    sanitized_path = file_path.parent / sanitized_name
    sanitized_path.write_text("".join(filtered_lines), encoding="utf-8")
    return sanitized_path, removed_lines


@admin_bp.route("/dashboard/stats", methods=["GET"])
@admin_required
def get_dashboard_stats(current_admin: User):
    """Menyediakan statistik komprehensif untuk dasbor admin."""
    try:
        tz_local = ZoneInfo("Asia/Makassar")
        now_local = datetime.now(tz_local)
        now_utc = now_local.astimezone(dt_timezone.utc)

        start_of_today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday_local = start_of_today_local - timedelta(days=1)
        start_of_month_local = start_of_today_local.replace(day=1)

        # Minggu kalender: Senin 00:00 WIB s.d. saat ini
        start_of_week_local = start_of_today_local - timedelta(days=start_of_today_local.weekday())
        start_of_prev_week_local = start_of_week_local - timedelta(days=7)

        start_of_today_utc = start_of_today_local.astimezone(dt_timezone.utc)
        start_of_yesterday_utc = start_of_yesterday_local.astimezone(dt_timezone.utc)
        start_of_month_utc = start_of_month_local.astimezone(dt_timezone.utc)
        start_30_days_utc = start_of_today_utc - timedelta(days=29)

        start_of_week_utc = start_of_week_local.astimezone(dt_timezone.utc)
        start_of_prev_week_utc = start_of_prev_week_local.astimezone(dt_timezone.utc)

        # Tetap dipakai untuk kebutuhan lain (mis. card kuota 7 hari)
        start_7_days_utc = start_of_today_utc - timedelta(days=6)
        start_prev_7_days_utc = start_7_days_utc - timedelta(days=7)

        seven_days_from_now = now_utc + timedelta(days=7)

        revenue_today = db.session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc
            )
        ) or Decimal("0.00")
        revenue_yesterday = db.session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_of_yesterday_utc,
                Transaction.created_at < start_of_today_utc,
            )
        ) or Decimal("0.00")
        revenue_month = db.session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_of_month_utc,
            )
        ) or Decimal("0.00")
        revenue_week = db.session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_of_week_utc,
            )
        ) or Decimal("0.00")
        revenue_prev_week = db.session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_of_prev_week_utc,
                Transaction.created_at < start_of_week_utc,
            )
        ) or Decimal("0.00")

        transaksi_hari_ini = (
            db.session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.status == TransactionStatus.SUCCESS,
                    Transaction.created_at >= start_of_today_utc,
                )
            )
            or 0
        )
        transaksi_minggu_ini = (
            db.session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.status == TransactionStatus.SUCCESS,
                    Transaction.created_at >= start_of_week_utc,
                )
            )
            or 0
        )
        transaksi_minggu_lalu = (
            db.session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.status == TransactionStatus.SUCCESS,
                    Transaction.created_at >= start_of_prev_week_utc,
                    Transaction.created_at < start_of_week_utc,
                )
            )
            or 0
        )

        new_registrants = (
            db.session.scalar(select(func.count(User.id)).where(User.created_at >= start_of_today_utc)) or 0
        )
        active_users = (
            db.session.scalar(
                select(func.count(User.id)).where(
                    User.approval_status == ApprovalStatus.APPROVED, User.is_active.is_(True)
                )
            )
            or 0
        )
        expiring_soon_users = (
            db.session.scalar(
                select(func.count(User.id)).where(User.quota_expiry_date.between(now_utc, seven_days_from_now))
            )
            or 0
        )

        kuota_terjual_gb = db.session.scalar(
            select(func.sum(Package.data_quota_gb))
            .select_from(Transaction)
            .join(Package)
            .where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_of_month_utc,
                Package.data_quota_gb > 0,
            )
        ) or Decimal("0.0")
        kuota_terjual_7hari_gb = db.session.scalar(
            select(func.sum(Package.data_quota_gb))
            .select_from(Transaction)
            .join(Package)
            .where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_7_days_utc,
                Package.data_quota_gb > 0,
            )
        ) or Decimal("0.0")
        kuota_terjual_prev_7hari_gb = db.session.scalar(
            select(func.sum(Package.data_quota_gb))
            .select_from(Transaction)
            .join(Package)
            .where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_prev_7_days_utc,
                Transaction.created_at < start_7_days_utc,
                Package.data_quota_gb > 0,
            )
        ) or Decimal("0.0")

        kuota_terjual_mb = float(kuota_terjual_gb) * 1024
        kuota_terjual_7hari_mb = float(kuota_terjual_7hari_gb) * 1024
        kuota_terjual_prev_7hari_mb = float(kuota_terjual_prev_7hari_gb) * 1024

        latest_transactions_q = (
            select(Transaction)
            .options(
                selectinload(Transaction.user).load_only(User.full_name, User.phone_number),
                selectinload(Transaction.package).load_only(Package.name),
            )
            .where(Transaction.status == TransactionStatus.SUCCESS)
            .order_by(desc(Transaction.created_at))
            .limit(5)
        )
        latest_transactions = db.session.scalars(latest_transactions_q).all()
        transaksi_terakhir_data = [
            {
                "id": str(tx.id),
                "amount": float(tx.amount),
                "created_at": tx.created_at.isoformat(),
                "package": {"name": tx.package.name if tx.package else "N/A"},
                "user": {
                    "full_name": tx.user.full_name if tx.user else "Pengguna Dihapus",
                    "phone_number": tx.user.phone_number if tx.user else None,
                },
            }
            for tx in latest_transactions
        ]

        top_packages_q = (
            select(Package.name, func.count(Transaction.id).label("sales_count"))
            .select_from(Transaction)
            .join(Package)
            .where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc)
            .group_by(Package.name)
            .order_by(desc("sales_count"))
            .limit(5)
        )
        top_packages = db.session.execute(top_packages_q).all()
        paket_terlaris_data = [{"name": name, "count": count} for name, count in top_packages]

        pending_requests_count = (
            db.session.scalar(select(func.count(QuotaRequest.id)).where(QuotaRequest.status == RequestStatus.PENDING))
            or 0
        )

        daily_revenue_rows = db.session.execute(
            select(func.date(Transaction.created_at).label("day"), func.sum(Transaction.amount))
            .where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_30_days_utc)
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
        ).all()
        daily_revenue_map = {row[0]: float(row[1] or 0) for row in daily_revenue_rows}

        daily_quota_rows = db.session.execute(
            select(func.date(Transaction.created_at).label("day"), func.sum(Package.data_quota_gb))
            .select_from(Transaction)
            .join(Package)
            .where(
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_7_days_utc,
                Package.data_quota_gb > 0,
            )
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
        ).all()
        daily_quota_map = {row[0]: float(row[1] or 0) * 1024 for row in daily_quota_rows}

        pendapatan_per_hari = []
        for i in range(30):
            day = (start_30_days_utc + timedelta(days=i)).date()
            pendapatan_per_hari.append(daily_revenue_map.get(day, 0))

        kuota_per_hari = []
        for i in range(7):
            day = (start_7_days_utc + timedelta(days=i)).date()
            kuota_per_hari.append(daily_quota_map.get(day, 0))

        stats = {
            "pendapatanHariIni": float(revenue_today),
            "pendapatanBulanIni": float(revenue_month),
            "pendapatanKemarin": float(revenue_yesterday),
            "pendapatanMingguIni": float(revenue_week),
            "pendapatanMingguLalu": float(revenue_prev_week),
            "transaksiHariIni": transaksi_hari_ini,
            "transaksiMingguIni": transaksi_minggu_ini,
            "transaksiMingguLalu": transaksi_minggu_lalu,
            "pendaftarBaru": new_registrants,
            "penggunaAktif": active_users,
            "akanKadaluwarsa": expiring_soon_users,
            "kuotaTerjualMb": kuota_terjual_mb,
            "kuotaTerjual7HariMb": kuota_terjual_7hari_mb,
            "kuotaTerjualMingguLaluMb": kuota_terjual_prev_7hari_mb,
            "kuotaPerHari": kuota_per_hari,
            "pendapatanPerHari": pendapatan_per_hari,
            "transaksiTerakhir": transaksi_terakhir_data,
            "paketTerlaris": paket_terlaris_data,
            "permintaanTertunda": pending_requests_count,
        }
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error di endpoint dashboard/stats: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat statistik dasbor."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route("/backups", methods=["GET"])
@admin_required
def list_backups(current_admin: User):
    return list_backups_impl(get_backup_dir=_get_backup_dir)


@admin_bp.route("/backups", methods=["POST"])
@admin_required
def create_backup(current_admin: User):
    return create_backup_impl(get_backup_dir=_get_backup_dir, build_pg_dump_command=_build_pg_dump_command)


@admin_bp.route("/backups/<path:filename>", methods=["GET"])
@admin_required
def download_backup(current_admin: User, filename: str):
    return download_backup_impl(filename=filename, get_backup_dir=_get_backup_dir)


@admin_bp.route("/backups/upload", methods=["POST"])
@super_admin_required
def upload_backup(current_admin: User):
    return upload_backup_impl(get_backup_dir=_get_backup_dir)


@admin_bp.route("/backups/restore", methods=["POST"])
@super_admin_required
def restore_backup(current_admin: User):
    return restore_backup_impl(
        db=db,
        get_backup_dir=_get_backup_dir,
        sanitize_sql_dump_for_restore=_sanitize_sql_dump_for_restore,
        build_psql_restore_command=_build_psql_restore_command,
        build_pg_restore_command=_build_pg_restore_command,
        build_psql_statement_command=_build_psql_statement_command,
    )


@admin_bp.route("/whatsapp/test-send", methods=["POST"])
@admin_required
def send_whatsapp_test(current_admin: User):
    return send_whatsapp_test_impl(send_whatsapp_message=send_whatsapp_message)


@admin_bp.route("/telegram/test-send", methods=["POST"])
@admin_required
def send_telegram_test(current_admin: User):
    return send_telegram_test_impl(send_telegram_message=send_telegram_message)


@admin_bp.route("/whatsapp/broadcast", methods=["POST"])
@admin_required
def send_whatsapp_broadcast(current_admin: User):
    return send_whatsapp_broadcast_impl(db=db, send_whatsapp_message=send_whatsapp_message)


@admin_bp.route("/notification-recipients", methods=["GET"])
@super_admin_required
def get_notification_recipients(current_admin: User):
    """Mengambil daftar admin dan status langganan mereka untuk tipe notifikasi tertentu."""
    return get_notification_recipients_impl(db=db)


@admin_bp.route("/notification-recipients", methods=["POST"])
@super_admin_required
def update_notification_recipients(current_admin: User):
    """Memperbarui daftar penerima untuk tipe notifikasi tertentu dari payload."""
    return update_notification_recipients_impl(db=db)


@admin_bp.route("/transactions", methods=["GET"])
@admin_required
def get_transactions_list(current_admin: User):
    """Mengambil daftar transaksi dengan paginasi dan filter."""
    return get_transactions_list_impl(
        db=db,
        parse_local_date_range_to_utc=_parse_local_date_range_to_utc,
        get_phone_number_variations=get_phone_number_variations,
        User=User,
        Transaction=Transaction,
        selectinload=selectinload,
        or_=or_,
        desc=desc,
    )


@admin_bp.route("/transactions/<order_id>/detail", methods=["GET"])
@admin_required
def get_transaction_detail(current_admin: User, order_id: str):
    """Mengambil detail satu transaksi (termasuk payload notifikasi Midtrans jika tersedia)."""
    return get_transaction_detail_impl(
        db=db,
        order_id=order_id,
        Transaction=Transaction,
        TransactionEvent=TransactionEvent,
        select=select,
        selectinload=selectinload,
        json_module=json,
    )


@admin_bp.route("/transactions/export", methods=["GET"])
@admin_required
def export_transactions(current_admin: User):
    """Unduh laporan penjualan (SUCCESS saja) untuk periode tertentu.

    Query params:
    - format: pdf
    - start_date: YYYY-MM-DD (wajib)
    - end_date: YYYY-MM-DD (wajib)
    - user_id: UUID (opsional)
    """
    return export_transactions_impl(
        db=db,
        WEASYPRINT_AVAILABLE=WEASYPRINT_AVAILABLE,
        HTML=HTML,
        parse_local_date_range_to_utc=_parse_local_date_range_to_utc,
        get_local_tz=_get_local_tz,
        estimate_debt_rp_from_cheapest_package=estimate_debt_rp_from_cheapest_package,
        format_to_local_phone=format_to_local_phone,
        Package=Package,
        Transaction=Transaction,
        TransactionStatus=TransactionStatus,
        User=User,
        UserRole=UserRole,
        ApprovalStatus=ApprovalStatus,
        func=func,
        select=select,
        desc=desc,
    )


@admin_bp.route("/transactions/qris", methods=["POST"])
@admin_bp.route("/transactions/bill", methods=["POST"])
@admin_required
def create_bill(current_admin: User):
    """Admin membuat tagihan (Snap/Core API) untuk user tertentu dan mengirim via WhatsApp.

    Payload:
    - user_id: UUID
    - package_id: UUID
    - payment_method: qris|va|gopay|shopeepay (optional; default qris)
    - va_bank: bca|bni|bri|mandiri|permata|cimb (required when payment_method=va)

    Catatan:
    - Endpoint /transactions/qris dipertahankan untuk kompatibilitas; ia sekarang alias dari endpoint ini.
    """
    return create_bill_impl(
        db=db,
        current_admin=current_admin,
        settings_service=settings_service,
        User=User,
        Package=Package,
        Transaction=Transaction,
        TransactionStatus=TransactionStatus,
        AdminActionLog=AdminActionLog,
        AdminActionType=AdminActionType,
        TransactionEvent=TransactionEvent,
        TransactionEventSource=TransactionEventSource,
        format_to_local_phone=format_to_local_phone,
        get_midtrans_snap_client=get_midtrans_snap_client,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
        extract_qr_code_url=extract_qr_code_url,
        extract_va_number=extract_va_number,
        extract_action_url=extract_action_url,
        send_whatsapp_message=send_whatsapp_message,
    )


@admin_bp.route("/midtrans/selftest", methods=["POST"])
@admin_required
def midtrans_selftest(current_admin: User):
    """Self-test channel Midtrans untuk memastikan payment_type aktif (qris/gopay) via Core API.

    Catatan:
    - Ini akan memanggil endpoint charge Midtrans (bukan dry-run). Gunakan amount kecil.
    - Tidak menyimpan transaksi ke database.
    """
    return midtrans_selftest_impl(
        current_admin=current_admin,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        format_to_local_phone=format_to_local_phone,
        extract_qr_code_url=extract_qr_code_url,
    )


@admin_bp.route("/transactions/<order_id>/report.pdf", methods=["GET"])
@admin_required
def get_transaction_admin_report_pdf(current_admin: User, order_id: str):
    """PDF Admin report (berbeda dari invoice user) untuk audit transaksi + histori event."""
    return get_transaction_admin_report_pdf_impl(
        db=db,
        order_id=order_id,
        WEASYPRINT_AVAILABLE=WEASYPRINT_AVAILABLE,
        HTML=HTML,
        get_local_tz=_get_local_tz,
        format_to_local_phone=format_to_local_phone,
        Transaction=Transaction,
        TransactionEvent=TransactionEvent,
        select=select,
        selectinload=selectinload,
    )


# --- Endpoint /action-logs DIHAPUS DARI SINI ---
# Logika ini sekarang sepenuhnya ditangani oleh action_log_routes.py
