# backend/app/infrastructure/http/admin/admin_routes.py
from flask import Blueprint, jsonify, request, current_app, send_file, abort, make_response, render_template
from sqlalchemy import func, or_, select, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone as dt_timezone, timedelta, time as dt_time
from http import HTTPStatus
from pydantic import ValidationError
from decimal import Decimal
import json
import midtransclient
import uuid
import csv
import io
import os
import pathlib
import subprocess
from sqlalchemy.engine import make_url

from app.extensions import db
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message, send_whatsapp_with_image_url
from app.infrastructure.db.models import (
    User, UserRole, Package, ApprovalStatus, Transaction,
    TransactionStatus, NotificationRecipient, NotificationType,
    QuotaRequest, RequestStatus, TransactionEvent, TransactionEventSource
)
from .decorators import admin_required, super_admin_required
from .schemas.notification_schemas import NotificationRecipientUpdateSchema
from app.utils.formatters import get_phone_number_variations, format_to_local_phone

from app.infrastructure.http.transactions_routes import (
    extract_qr_code_url,
    extract_va_number,
    get_midtrans_core_api_client,
    safe_parse_midtrans_datetime,
)

admin_bp = Blueprint('admin_api', __name__)

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

def _get_backup_dir() -> str:
    backup_dir = current_app.config.get('BACKUP_DIR', '/app/backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def _build_pg_dump_command(output_path: str) -> list[str]:
    db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
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
        "-h", host,
        "-p", str(port),
        "-U", url.username,
        "-F", "c",
        "-f", output_path,
        url.database,
    ]


def _build_pg_restore_command(input_path: str) -> list[str]:
    db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
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
        "-h", host,
        "-p", str(port),
        "-U", url.username,
        "-d", url.database,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        input_path,
    ]


def _build_psql_restore_command(input_path: str) -> list[str]:
    db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
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
        "-h", host,
        "-p", str(port),
        "-U", url.username,
        "-d", url.database,
        "-v", "ON_ERROR_STOP=1",
        "-f", input_path,
    ]


def _build_psql_statement_command(statement: str) -> list[str]:
    db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
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
        "-h", host,
        "-p", str(port),
        "-U", url.username,
        "-d", url.database,
        "-v", "ON_ERROR_STOP=1",
        "-c", statement,
    ]


def _sanitize_sql_dump_for_restore(file_path: pathlib.Path) -> tuple[pathlib.Path, int]:
    original_content = file_path.read_text(encoding='utf-8', errors='replace')
    filtered_lines = []
    removed_lines = 0
    for line in original_content.splitlines(keepends=True):
        if line.lstrip().startswith('pg_dump:'):
            removed_lines += 1
            continue
        filtered_lines.append(line)

    if removed_lines == 0:
        return file_path, 0

    sanitized_name = f"{file_path.stem}.sanitized_{uuid.uuid4().hex}{file_path.suffix}"
    sanitized_path = file_path.parent / sanitized_name
    sanitized_path.write_text(''.join(filtered_lines), encoding='utf-8')
    return sanitized_path, removed_lines

@admin_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats(current_admin: User):
    """Menyediakan statistik komprehensif untuk dasbor admin."""
    try:
        now_utc = datetime.now(dt_timezone.utc)
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday_utc = start_of_today_utc - timedelta(days=1)
        start_of_month_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_7_days_utc = start_of_today_utc - timedelta(days=6)
        start_prev_7_days_utc = start_7_days_utc - timedelta(days=7)
        start_30_days_utc = start_of_today_utc - timedelta(days=29)
        seven_days_from_now = now_utc + timedelta(days=7)

        revenue_today = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc)) or Decimal('0.00')
        revenue_yesterday = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_yesterday_utc, Transaction.created_at < start_of_today_utc)) or Decimal('0.00')
        revenue_month = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc)) or Decimal('0.00')
        revenue_week = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_7_days_utc)) or Decimal('0.00')
        revenue_prev_week = db.session.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_prev_7_days_utc, Transaction.created_at < start_7_days_utc)) or Decimal('0.00')

        transaksi_hari_ini = db.session.scalar(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_today_utc)) or 0
        transaksi_minggu_ini = db.session.scalar(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_7_days_utc)) or 0
        transaksi_minggu_lalu = db.session.scalar(select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_prev_7_days_utc, Transaction.created_at < start_7_days_utc)) or 0

        new_registrants = db.session.scalar(select(func.count(User.id)).where(User.approval_status == ApprovalStatus.PENDING_APPROVAL)) or 0
        active_users = db.session.scalar(select(func.count(User.id)).where(User.approval_status == ApprovalStatus.APPROVED, User.is_active.is_(True))) or 0
        expiring_soon_users = db.session.scalar(select(func.count(User.id)).where(User.quota_expiry_date.between(now_utc, seven_days_from_now))) or 0

        kuota_terjual_gb = db.session.scalar(select(func.sum(Package.data_quota_gb)).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc, Package.data_quota_gb > 0)) or Decimal('0.0')
        kuota_terjual_7hari_gb = db.session.scalar(select(func.sum(Package.data_quota_gb)).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_7_days_utc, Package.data_quota_gb > 0)) or Decimal('0.0')
        kuota_terjual_prev_7hari_gb = db.session.scalar(select(func.sum(Package.data_quota_gb)).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_prev_7_days_utc, Transaction.created_at < start_7_days_utc, Package.data_quota_gb > 0)) or Decimal('0.0')

        kuota_terjual_mb = float(kuota_terjual_gb) * 1024
        kuota_terjual_7hari_mb = float(kuota_terjual_7hari_gb) * 1024
        kuota_terjual_prev_7hari_mb = float(kuota_terjual_prev_7hari_gb) * 1024

        latest_transactions_q = select(Transaction).options(
            selectinload(Transaction.user).load_only(User.full_name, User.phone_number),
            selectinload(Transaction.package).load_only(Package.name)
        ).where(Transaction.status == TransactionStatus.SUCCESS).order_by(desc(Transaction.created_at)).limit(5)
        latest_transactions = db.session.scalars(latest_transactions_q).all()
        transaksi_terakhir_data = [{
            "id": str(tx.id),
            "amount": float(tx.amount),
            "created_at": tx.created_at.isoformat(),
            "package": {"name": tx.package.name if tx.package else "N/A"},
            "user": {
                "full_name": tx.user.full_name if tx.user else "Pengguna Dihapus",
                "phone_number": tx.user.phone_number if tx.user else None,
            }
        } for tx in latest_transactions]
        
        top_packages_q = select(Package.name, func.count(Transaction.id).label('sales_count')).select_from(Transaction).join(Package).where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_of_month_utc).group_by(Package.name).order_by(desc('sales_count')).limit(5)
        top_packages = db.session.execute(top_packages_q).all()
        paket_terlaris_data = [{"name": name, "count": count} for name, count in top_packages]
        
        pending_requests_count = db.session.scalar(select(func.count(QuotaRequest.id)).where(QuotaRequest.status == RequestStatus.PENDING)) or 0

        daily_revenue_rows = db.session.execute(
            select(func.date(Transaction.created_at).label('day'), func.sum(Transaction.amount))
            .where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_30_days_utc)
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
        ).all()
        daily_revenue_map = {row[0]: float(row[1] or 0) for row in daily_revenue_rows}

        daily_quota_rows = db.session.execute(
            select(func.date(Transaction.created_at).label('day'), func.sum(Package.data_quota_gb))
            .select_from(Transaction)
            .join(Package)
            .where(Transaction.status == TransactionStatus.SUCCESS, Transaction.created_at >= start_7_days_utc, Package.data_quota_gb > 0)
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
            "pendapatanHariIni": float(revenue_today), "pendapatanBulanIni": float(revenue_month),
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

@admin_bp.route('/backups', methods=['GET'])
@admin_required
def list_backups(current_admin: User):
    try:
        backup_dir = _get_backup_dir()
        items = []
        for pattern in ("*.dump", "*.sql"):
            for entry in pathlib.Path(backup_dir).glob(pattern):
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
                })
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return jsonify({"items": items}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar backup: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil daftar backup."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/backups', methods=['POST'])
@admin_required
def create_backup(current_admin: User):
    try:
        backup_dir = _get_backup_dir()
        timestamp = datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{timestamp}.dump"
        output_path = os.path.join(backup_dir, filename)

        cmd = _build_pg_dump_command(output_path)
        env = os.environ.copy()
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if not isinstance(db_uri, str) or not db_uri:
            raise RuntimeError("DATABASE_URL tidak disetel")
        db_url = make_url(db_uri)
        if db_url.password:
            env["PGPASSWORD"] = db_url.password

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            current_app.logger.error(f"pg_dump gagal: {result.stderr}")
            return jsonify({"message": "Backup gagal dijalankan."}), HTTPStatus.INTERNAL_SERVER_ERROR

        stat = pathlib.Path(output_path).stat()
        return jsonify({
            "name": filename,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
        }), HTTPStatus.OK
    except FileNotFoundError:
        return jsonify({"message": "pg_dump tidak tersedia di server."}), HTTPStatus.BAD_REQUEST
    except RuntimeError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error membuat backup: {e}", exc_info=True)
        return jsonify({"message": "Gagal membuat backup."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/backups/<path:filename>', methods=['GET'])
@admin_required
def download_backup(current_admin: User, filename: str):
    backup_dir = _get_backup_dir()
    safe_name = pathlib.Path(filename).name
    file_path = pathlib.Path(backup_dir) / safe_name
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"message": "File backup tidak ditemukan."}), HTTPStatus.NOT_FOUND
    return send_file(file_path, as_attachment=True)


@admin_bp.route('/backups/upload', methods=['POST'])
@super_admin_required
def upload_backup(current_admin: User):
    try:
        uploaded_file = request.files.get('file')
        if uploaded_file is None:
            return jsonify({"message": "File backup wajib diunggah."}), HTTPStatus.BAD_REQUEST

        original_name = pathlib.Path(uploaded_file.filename or '').name
        if not original_name:
            return jsonify({"message": "Nama file tidak valid."}), HTTPStatus.BAD_REQUEST

        extension = pathlib.Path(original_name).suffix.lower()
        if extension not in ('.dump', '.sql'):
            return jsonify({"message": "Format file tidak didukung. Gunakan .dump atau .sql"}), HTTPStatus.BAD_REQUEST

        backup_dir = pathlib.Path(_get_backup_dir())
        stem = pathlib.Path(original_name).stem
        timestamp = datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')
        save_name = f"upload_{timestamp}_{stem}{extension}"
        target_path = backup_dir / save_name
        uploaded_file.save(target_path)

        stat = target_path.stat()
        return jsonify({
            "message": "File backup berhasil diunggah.",
            "name": save_name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error upload backup: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengunggah file backup."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/backups/restore', methods=['POST'])
@super_admin_required
def restore_backup(current_admin: User):
    temporary_restore_path: pathlib.Path | None = None
    try:
        json_data = request.get_json(silent=True) or {}
        filename = str(json_data.get('filename') or '').strip()
        confirm = str(json_data.get('confirm') or '').strip().upper()
        restore_mode = str(json_data.get('restore_mode') or 'merge').strip().lower()

        if not filename:
            return jsonify({"message": "filename wajib diisi."}), HTTPStatus.BAD_REQUEST
        if confirm != 'RESTORE':
            return jsonify({"message": "Konfirmasi restore tidak valid."}), HTTPStatus.BAD_REQUEST
        if restore_mode not in ('merge', 'replace_users'):
            return jsonify({"message": "restore_mode tidak valid. Gunakan 'merge' atau 'replace_users'."}), HTTPStatus.BAD_REQUEST

        backup_dir = _get_backup_dir()
        safe_name = pathlib.Path(filename).name
        file_path = pathlib.Path(backup_dir) / safe_name
        extension = file_path.suffix.lower()
        if extension not in ('.dump', '.sql'):
            return jsonify({"message": "Format file backup tidak didukung."}), HTTPStatus.BAD_REQUEST
        if extension != '.sql' and restore_mode != 'merge':
            return jsonify({"message": "restore_mode selain 'merge' hanya didukung untuk file .sql"}), HTTPStatus.BAD_REQUEST
        if not file_path.exists() or not file_path.is_file():
            return jsonify({"message": "File backup tidak ditemukan."}), HTTPStatus.NOT_FOUND

        db.session.remove()
        db.engine.dispose()

        if extension == '.sql':
            sanitized_path, removed_lines = _sanitize_sql_dump_for_restore(file_path)
            if removed_lines > 0:
                current_app.logger.warning(
                    "Restore SQL: %s baris warning pg_dump dihapus otomatis dari %s",
                    removed_lines,
                    safe_name,
                )
            if sanitized_path != file_path:
                temporary_restore_path = sanitized_path
            cmd = _build_psql_restore_command(str(sanitized_path))
        else:
            cmd = _build_pg_restore_command(str(file_path))
        env = os.environ.copy()
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if not isinstance(db_uri, str) or not db_uri:
            raise RuntimeError("DATABASE_URL tidak disetel")
        db_url = make_url(db_uri)
        if db_url.password:
            env['PGPASSWORD'] = db_url.password

        if extension == '.sql' and restore_mode == 'replace_users':
            pre_cmd = _build_psql_statement_command('TRUNCATE TABLE public.users RESTART IDENTITY CASCADE;')
            pre_result = subprocess.run(pre_cmd, env=env, capture_output=True, text=True, check=False)
            if pre_result.returncode != 0:
                pre_stderr = (pre_result.stderr or '').strip()
                current_app.logger.error(f"Pre-clean users sebelum restore gagal: {pre_stderr}")
                return jsonify({
                    "message": "Pre-clean data users gagal dijalankan sebelum restore.",
                    "details": pre_stderr[:500],
                }), HTTPStatus.INTERNAL_SERVER_ERROR

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            stderr_text = (result.stderr or '').strip()
            only_transaction_timeout_warning = (
                extension == '.dump'
                and 'unrecognized configuration parameter "transaction_timeout"' in stderr_text
            )

            if only_transaction_timeout_warning:
                current_app.logger.warning(
                    "pg_restore selesai dengan warning kompatibilitas transaction_timeout: %s",
                    stderr_text,
                )
            else:
                current_app.logger.error(f"pg_restore gagal: {stderr_text}")
                return jsonify({
                    "message": "Restore gagal dijalankan.",
                    "details": stderr_text[:500],
                }), HTTPStatus.INTERNAL_SERVER_ERROR

        return jsonify({
            "message": "Restore database berhasil dijalankan.",
            "filename": safe_name,
            "restore_mode": restore_mode,
        }), HTTPStatus.OK
    except FileNotFoundError:
        return jsonify({"message": "pg_restore/psql tidak tersedia di server."}), HTTPStatus.BAD_REQUEST
    except RuntimeError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error restore backup: {e}", exc_info=True)
        return jsonify({"message": "Gagal menjalankan restore backup."}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        if temporary_restore_path is not None:
            try:
                if temporary_restore_path.exists():
                    temporary_restore_path.unlink()
            except Exception as cleanup_error:
                current_app.logger.warning(
                    "Gagal menghapus file sementara restore %s: %s",
                    str(temporary_restore_path),
                    cleanup_error,
                )


@admin_bp.route('/whatsapp/test-send', methods=['POST'])
@admin_required
def send_whatsapp_test(current_admin: User):
    try:
        json_data = request.get_json(silent=True) or {}
        phone_number = str(json_data.get('phone_number') or '').strip()
        message = str(json_data.get('message') or '').strip() or 'Tes WhatsApp dari panel admin hotspot.'

        if not phone_number:
            return jsonify({"message": "Nomor WhatsApp wajib diisi."}), HTTPStatus.BAD_REQUEST
        if len(message) > 1000:
            return jsonify({"message": "Pesan terlalu panjang (maks 1000 karakter)."}), HTTPStatus.BAD_REQUEST

        sent = send_whatsapp_message(phone_number, message)
        if not sent:
            return jsonify({
                "message": "Pengiriman WhatsApp gagal. Cek konfigurasi Fonnte/token/nomor tujuan.",
            }), HTTPStatus.BAD_REQUEST

        return jsonify({
            "message": "Pesan WhatsApp uji coba berhasil dikirim.",
            "target": phone_number,
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error test-send WhatsApp admin: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengirim WhatsApp uji coba."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/whatsapp/broadcast', methods=['POST'])
@admin_required
def send_whatsapp_broadcast(current_admin: User):
    try:
        json_data = request.get_json(silent=True) or {}
        target_role = str(json_data.get('target_role') or '').strip().upper()
        message = str(json_data.get('message') or '').strip()

        if target_role not in {UserRole.USER.value, UserRole.KOMANDAN.value}:
            return jsonify({"message": "Filter role tidak valid. Gunakan USER atau KOMANDAN."}), HTTPStatus.BAD_REQUEST
        if not message:
            return jsonify({"message": "Pesan wajib diisi."}), HTTPStatus.BAD_REQUEST
        if len(message) > 1000:
            return jsonify({"message": "Pesan terlalu panjang (maks 1000 karakter)."}), HTTPStatus.BAD_REQUEST

        recipients_query = select(User).where(
            User.role == UserRole[target_role],
            User.approval_status == ApprovalStatus.APPROVED,
            User.phone_number.isnot(None),
            User.phone_number != '',
        )
        recipients = db.session.scalars(recipients_query).all()

        if not recipients:
            return jsonify({
                "message": f"Tidak ada penerima untuk role {target_role}.",
                "target_role": target_role,
                "total_recipients": 0,
                "sent_count": 0,
                "failed_count": 0,
            }), HTTPStatus.OK

        sent_count = 0
        failed_numbers = []
        for user in recipients:
            phone_number = str(user.phone_number or '').strip()
            if not phone_number:
                failed_numbers.append(phone_number)
                continue
            sent = send_whatsapp_message(phone_number, message)
            if sent:
                sent_count += 1
            else:
                failed_numbers.append(phone_number)

        failed_count = len(recipients) - sent_count
        return jsonify({
            "message": "Pengiriman WhatsApp massal selesai diproses.",
            "target_role": target_role,
            "total_recipients": len(recipients),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "failed_numbers": failed_numbers[:20],
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error broadcast WhatsApp admin: {e}", exc_info=True)
        return jsonify({"message": "Gagal memproses pengiriman WhatsApp massal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/notification-recipients', methods=['GET'])
@super_admin_required
def get_notification_recipients(current_admin: User):
    """Mengambil daftar admin dan status langganan mereka untuk tipe notifikasi tertentu."""
    notification_type_str = (
        request.args.get('notification_type')
        or request.args.get('type')
        or 'NEW_USER_REGISTRATION'
    )
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
                recipient = NotificationRecipient()
                recipient.admin_user_id = admin_id
                recipient.notification_type = notification_type
                new_recipients.append(recipient)
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
        
        if start_date_str and end_date_str:
            try:
                start_utc, end_utc = _parse_local_date_range_to_utc(start_date_str, end_date_str)
                query = query.where(Transaction.created_at >= start_utc)
                query = query.where(Transaction.created_at < end_utc)
            except ValueError:
                return jsonify({"message": "Format tanggal tidak valid."}), HTTPStatus.BAD_REQUEST
        elif start_date_str or end_date_str:
            return jsonify({"message": "start_date dan end_date harus diisi keduanya."}), HTTPStatus.BAD_REQUEST

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
        transactions_data = [
            {
                "id": str(tx.id),
                "order_id": tx.midtrans_order_id,
                "amount": float(tx.amount),
                "status": tx.status.value,
                "created_at": tx.created_at.isoformat(),
                "midtrans_transaction_id": tx.midtrans_transaction_id,
                "payment_method": tx.payment_method,
                "payment_time": tx.payment_time.isoformat() if tx.payment_time else None,
                "expiry_time": tx.expiry_time.isoformat() if tx.expiry_time else None,
                "user": {
                    "full_name": tx.user.full_name if tx.user else "N/A",
                    "phone_number": tx.user.phone_number if tx.user else "N/A",
                },
                "package_name": tx.package.name if tx.package else "N/A",
            }
            for tx in pagination.items
        ]
        
        return jsonify({"items": transactions_data, "totalItems": pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar transaksi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/transactions/<order_id>/detail', methods=['GET'])
@admin_required
def get_transaction_detail(current_admin: User, order_id: str):
    """Mengambil detail satu transaksi (termasuk payload notifikasi Midtrans jika tersedia)."""
    try:
        order_id = (order_id or "").strip()
        if not order_id:
            return jsonify({"message": "order_id tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

        tx = db.session.scalar(
            select(Transaction)
            .where(Transaction.midtrans_order_id == order_id)
            .options(selectinload(Transaction.user), selectinload(Transaction.package))
        )

        if tx is None:
            return jsonify({"message": "Transaksi tidak ditemukan."}), HTTPStatus.NOT_FOUND

        payload: object | None = None
        if tx.midtrans_notification_payload:
            try:
                payload = json.loads(tx.midtrans_notification_payload)
            except Exception:
                payload = {"_raw": tx.midtrans_notification_payload}

        events_q = (
            select(TransactionEvent)
            .where(TransactionEvent.transaction_id == tx.id)
            .order_by(TransactionEvent.created_at.asc())
        )
        events = db.session.scalars(events_q).all()
        events_payload = []
        for ev in events:
            ev_payload: object | None = None
            if ev.payload:
                try:
                    ev_payload = json.loads(ev.payload)
                except Exception:
                    ev_payload = {"_raw": ev.payload}
            events_payload.append(
                {
                    "id": str(ev.id),
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                    "source": ev.source.value,
                    "event_type": ev.event_type,
                    "status": ev.status.value if ev.status else None,
                    "payload": ev_payload,
                }
            )

        return (
            jsonify(
                {
                    "id": str(tx.id),
                    "order_id": tx.midtrans_order_id,
                    "amount": float(tx.amount),
                    "status": tx.status.value,
                    "created_at": tx.created_at.isoformat(),
                    "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
                    "midtrans_transaction_id": tx.midtrans_transaction_id,
                    "payment_method": tx.payment_method,
                    "payment_time": tx.payment_time.isoformat() if tx.payment_time else None,
                    "expiry_time": tx.expiry_time.isoformat() if tx.expiry_time else None,
                    "va_number": tx.va_number,
                    "payment_code": tx.payment_code,
                    "biller_code": tx.biller_code,
                    "qr_code_url": tx.qr_code_url,
                    "user": {
                        "full_name": tx.user.full_name if tx.user else "N/A",
                        "phone_number": tx.user.phone_number if tx.user else "N/A",
                    },
                    "package_name": tx.package.name if tx.package else "N/A",
                    "midtrans_notification_payload": payload,
                    "events": events_payload,
                }
            ),
            HTTPStatus.OK,
        )
    except Exception as e:
        current_app.logger.error(f"Error mengambil detail transaksi {order_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/transactions/export', methods=['GET'])
@admin_required
def export_transactions(current_admin: User):
    """Unduh laporan penjualan (SUCCESS saja) untuk periode tertentu.

    Query params:
    - format: pdf|csv
    - start_date: YYYY-MM-DD (wajib)
    - end_date: YYYY-MM-DD (wajib)
    - user_id: UUID (opsional)
    """
    try:
        fmt = str(request.args.get('format', '') or '').strip().lower()
        start_date_str = str(request.args.get('start_date', '') or '').strip()
        end_date_str = str(request.args.get('end_date', '') or '').strip()
        user_id_filter = request.args.get('user_id')

        if fmt not in ('pdf', 'csv'):
            return jsonify({"message": "format tidak valid. Gunakan pdf atau csv."}), HTTPStatus.BAD_REQUEST
        if not start_date_str or not end_date_str:
            return jsonify({"message": "start_date dan end_date wajib diisi."}), HTTPStatus.BAD_REQUEST

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"message": "Format tanggal tidak valid. Gunakan YYYY-MM-DD."}), HTTPStatus.BAD_REQUEST

        if end_date < start_date:
            return jsonify({"message": "end_date tidak boleh lebih kecil dari start_date."}), HTTPStatus.BAD_REQUEST

        # Interpret requested dates in local timezone, then convert to UTC for DB filtering.
        start_dt, end_dt = _parse_local_date_range_to_utc(start_date_str, end_date_str)

        base_filters = [
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.created_at >= start_dt,
            Transaction.created_at < end_dt,
        ]

        user_uuid: uuid.UUID | None = None
        if user_id_filter:
            try:
                user_uuid = uuid.UUID(str(user_id_filter))
                base_filters.append(Transaction.user_id == user_uuid)
            except ValueError:
                return jsonify({"message": "Invalid user_id format."}), HTTPStatus.BAD_REQUEST

        # Ringkasan total
        totals_row = db.session.execute(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            ).where(*base_filters)
        ).one()

        total_success = int(totals_row[0] or 0)
        total_amount = int(totals_row[1] or 0)

        # Top paket (best selling)
        package_rows = db.session.execute(
            select(
                Package.name,
                func.count(Transaction.id).label('qty'),
                func.coalesce(func.sum(Transaction.amount), 0).label('revenue'),
            )
            .join(Package, Transaction.package_id == Package.id)
            .where(*base_filters)
            .group_by(Package.name)
            .order_by(desc('revenue'), desc('qty'), Package.name.asc())
        ).all()

        # Breakdown metode pembayaran
        method_rows = db.session.execute(
            select(
                Transaction.payment_method,
                func.count(Transaction.id).label('qty'),
                func.coalesce(func.sum(Transaction.amount), 0).label('revenue'),
            )
            .where(*base_filters)
            .group_by(Transaction.payment_method)
            .order_by(desc('revenue'), desc('qty'))
        ).all()

        if fmt == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow(["Laporan Penjualan (SUCCESS)"])
            writer.writerow(["Periode", start_date_str, "s/d", end_date_str])
            if user_uuid is not None:
                writer.writerow(["Filter user_id", str(user_uuid)])
            writer.writerow(["Total transaksi sukses", total_success])
            writer.writerow(["Total pendapatan (IDR)", total_amount])
            writer.writerow([])

            writer.writerow(["Paket Terlaris"])
            writer.writerow(["Rank", "Paket", "Qty", "Revenue (IDR)"])
            for idx, row in enumerate(package_rows, start=1):
                writer.writerow([idx, row[0], int(row[1] or 0), int(row[2] or 0)])

            writer.writerow([])
            writer.writerow(["Metode Pembayaran"])
            writer.writerow(["Metode", "Qty", "Revenue (IDR)"])
            for row in method_rows:
                method = row[0] or "(unknown)"
                writer.writerow([method, int(row[1] or 0), int(row[2] or 0)])

            csv_bytes = output.getvalue().encode('utf-8-sig')
            resp = make_response(csv_bytes)
            resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
            resp.headers['Content-Disposition'] = f'attachment; filename="laporan-transaksi-{start_date_str}-to-{end_date_str}.csv"'
            return resp

        # pdf
        if not WEASYPRINT_AVAILABLE or HTML is None:
            return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        context = {
            "start_date": start_date_str,
            "end_date": end_date_str,
            "generated_at": datetime.now(app_tz),
            "total_success": total_success,
            "total_amount": total_amount,
            "packages": [
                {"rank": idx, "name": r[0], "qty": int(r[1] or 0), "revenue": int(r[2] or 0)}
                for idx, r in enumerate(package_rows, start=1)
            ],
            "methods": [
                {"method": (r[0] or "(unknown)"), "qty": int(r[1] or 0), "revenue": int(r[2] or 0)}
                for r in method_rows
            ],
            "business_name": current_app.config.get('BUSINESS_NAME', 'LPSaring'),
        }

        public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
        html_string = render_template('admin_sales_report.html', **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        resp = make_response(pdf_bytes)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename="laporan-transaksi-{start_date_str}-to-{end_date_str}.pdf"'
        return resp
    except Exception as e:
        current_app.logger.error(f"Error export transaksi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/transactions/qris', methods=['POST'])
@admin_required
def create_qris_bill(current_admin: User):
    """Admin membuat tagihan QRIS untuk user tertentu dan mengirim via WhatsApp."""
    session = db.session
    json_data = request.get_json(silent=True) or {}

    user_id_raw = json_data.get('user_id')
    package_id_raw = json_data.get('package_id')
    if not user_id_raw or not package_id_raw:
        return jsonify({"message": "user_id dan package_id wajib diisi."}), HTTPStatus.BAD_REQUEST

    try:
        user_id = uuid.UUID(str(user_id_raw))
        package_id = uuid.UUID(str(package_id_raw))
    except ValueError:
        return jsonify({"message": "Format user_id/package_id tidak valid."}), HTTPStatus.BAD_REQUEST

    try:
        user = session.get(User, user_id)
        if user is None:
            return jsonify({"message": "User tidak ditemukan."}), HTTPStatus.NOT_FOUND

        package = session.get(Package, package_id)
        if package is None or not getattr(package, 'is_active', True):
            return jsonify({"message": "Paket tidak valid atau tidak aktif."}), HTTPStatus.BAD_REQUEST

        amount = int(getattr(package, 'price', 0) or 0)
        if amount <= 0:
            return jsonify({"message": "Harga paket tidak valid."}), HTTPStatus.BAD_REQUEST

        order_id = f"HS-{uuid.uuid4().hex[:12].upper()}"
        now_utc = datetime.now(dt_timezone.utc)
        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        tx = Transaction()
        tx.id = uuid.uuid4()
        tx.user_id = user.id
        tx.package_id = package.id
        tx.midtrans_order_id = order_id
        tx.amount = amount
        tx.status = TransactionStatus.PENDING
        tx.expiry_time = expiry_time
        # Default: QRIS native (Other QRIS). Bisa auto-fallback ke GoPay Dynamic QRIS jika channel belum aktif.
        tx.payment_method = 'qris'
        session.add(tx)

        core = get_midtrans_core_api_client()

        base_payload: dict[str, object] = {
            "transaction_details": {"order_id": order_id, "gross_amount": amount},
            "item_details": [{
                "id": str(package.id),
                "price": amount,
                "quantity": 1,
                "name": str(getattr(package, 'name', 'Paket'))[:100],
            }],
            "customer_details": {
                "first_name": str(getattr(user, 'full_name', None) or 'Pengguna')[:50],
                "phone": format_to_local_phone(getattr(user, 'phone_number', '') or ''),
            },
        }

        def _parse_midtrans_api_response_from_message(message: str) -> dict[str, object] | None:
            try:
                marker = 'API response: `'
                if marker in message:
                    json_part = message.split(marker, 1)[1]
                    json_part = json_part.split('`', 1)[0]
                    parsed = json.loads(json_part)
                    return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
            return None

        charge_resp: object
        attempted_payment_type = 'qris'
        fallback_used = False
        try:
            # Attempt 1: Other QRIS (native QRIS) via payment_type=qris
            attempted_payment_type = 'qris'
            charge_payload = {**base_payload, "payment_type": "qris"}
            charge_resp = core.charge(charge_payload)
        except midtransclient.error_midtrans.MidtransAPIError as e_charge:
            raw_message = getattr(e_charge, 'message', '') or ''
            parsed = _parse_midtrans_api_response_from_message(raw_message) or {}
            status_message = str(parsed.get('status_message') or '').strip()
            # Jika channel QRIS native belum aktif, fallback ke GoPay Dynamic QRIS (masih scan QRIS).
            if 'Payment channel is not activated' in status_message:
                current_app.logger.warning(
                    "Midtrans QRIS channel not active; fallback to GoPay Dynamic QRIS. order_id=%s",
                    order_id,
                )
                fallback_used = True
                tx.payment_method = 'gopay'
                attempted_payment_type = 'gopay'
                charge_payload = {
                    **base_payload,
                    "payment_type": "gopay",
                    # Minimal config; Midtrans akan mengembalikan actions generate-qr-code.
                    "gopay": {"enable_callback": False},
                }
                charge_resp = core.charge(charge_payload)
            else:
                raise

        try:
            tx.midtrans_notification_payload = json.dumps(charge_resp, ensure_ascii=False)
        except Exception:
            tx.midtrans_notification_payload = None

        if isinstance(charge_resp, dict):
            charge_resp_dict: dict[str, object] = charge_resp
            transaction_id = charge_resp_dict.get('transaction_id')
            if isinstance(transaction_id, str):
                tx.midtrans_transaction_id = transaction_id
            expiry_time_raw = charge_resp_dict.get('expiry_time')
            expiry_time_str = expiry_time_raw if isinstance(expiry_time_raw, str) else None
            if parsed := safe_parse_midtrans_datetime(expiry_time_str):
                tx.expiry_time = parsed
            tx.va_number = extract_va_number(charge_resp_dict) or tx.va_number
            tx.qr_code_url = extract_qr_code_url(charge_resp_dict) or tx.qr_code_url

            midtrans_status = str(charge_resp_dict.get('transaction_status') or '').strip().lower()
            if midtrans_status == 'pending':
                tx.status = TransactionStatus.PENDING
            elif midtrans_status in ('settlement', 'capture'):
                tx.status = TransactionStatus.SUCCESS

        ev = TransactionEvent()
        ev.transaction_id = tx.id
        ev.source = TransactionEventSource.APP
        ev.event_type = 'ADMIN_QRIS_BILL_CREATED'
        ev.status = tx.status
        expiry_time = tx.expiry_time
        ev.payload = json.dumps(
            {
                "order_id": order_id,
                "user_id": str(user.id),
                "package_id": str(package.id),
                "amount": amount,
                "expiry_time": expiry_time.isoformat() if expiry_time is not None else None,
                "qr_code_url": tx.qr_code_url,
                "payment_method": tx.payment_method,
            },
            ensure_ascii=False,
        )
        session.add(ev)
        session.commit()

        phone_number = getattr(user, 'phone_number', '') or ''
        caption = (
            f"📌 *Tagihan Pembelian Paket*\n\n"
            f"Nama: *{getattr(user, 'full_name', '') or 'Pengguna'}*\n"
            f"Paket: *{getattr(package, 'name', '') or 'Paket'}*\n"
            f"Jumlah: *Rp {amount:,}*\n"
            f"Invoice: *{order_id}*\n\n"
            f"Silakan scan QRIS atau buka link QR." 
        )

        sent = False
        if tx.qr_code_url:
            sent = send_whatsapp_with_image_url(phone_number, caption, tx.qr_code_url, filename=f"qris-{order_id}.png")
        if not sent:
            send_whatsapp_message(phone_number, f"{caption}\n\nQR: {tx.qr_code_url or '-'}")

        return jsonify({
            "message": "Tagihan QRIS berhasil dibuat.",
            "order_id": order_id,
            "status": tx.status.value,
            "qr_code_url": tx.qr_code_url,
            "payment_method": tx.payment_method,
        }), HTTPStatus.OK

    except midtransclient.error_midtrans.MidtransAPIError as e:
        session.rollback()
        raw_message = getattr(e, 'message', '') or ''
        current_app.logger.error(f"Midtrans error saat create QRIS bill: {raw_message}")

        midtrans_status_code: str | None = None
        midtrans_status_message: str | None = None
        midtrans_error_id: str | None = None

        # Coba parse potongan `API response: `...`` dari message Midtrans.
        try:
            marker = 'API response: `'
            if marker in raw_message:
                json_part = raw_message.split(marker, 1)[1]
                json_part = json_part.split('`', 1)[0]
                parsed = json.loads(json_part)
                if isinstance(parsed, dict):
                    if isinstance(parsed.get('status_code'), str):
                        midtrans_status_code = parsed.get('status_code')
                    if isinstance(parsed.get('status_message'), str):
                        midtrans_status_message = parsed.get('status_message')
                    if isinstance(parsed.get('id'), str):
                        midtrans_error_id = parsed.get('id')
        except Exception:
            # Jika parsing gagal, tetap lanjutkan dengan message mentah.
            pass

        user_message = 'Gagal membuat tagihan QRIS di Midtrans.'
        if midtrans_status_message:
            user_message = f"Gagal membuat tagihan QRIS di Midtrans: {midtrans_status_message}"
            if 'Payment channel is not activated' in midtrans_status_message:
                # Beri konteks channel yang sedang dicoba + apakah fallback sudah dilakukan.
                tried = None
                try:
                    tried = attempted_payment_type  # type: ignore[name-defined]
                except Exception:
                    tried = None
                try:
                    used_fallback = bool(fallback_used)  # type: ignore[name-defined]
                except Exception:
                    used_fallback = False

                if tried == 'gopay':
                    user_message += ' (Channel GoPay/GoPay Dynamic QRIS belum aktif di Midtrans Production untuk Core API.)'
                else:
                    user_message += ' (Channel Other QRIS belum aktif di Midtrans Production.)'

                if used_fallback:
                    user_message += ' Sudah dicoba fallback ke GoPay Dynamic QRIS, namun masih ditolak.'

        return jsonify({
            "message": user_message,
            "midtrans_status_code": midtrans_status_code,
            "midtrans_status_message": midtrans_status_message,
            "midtrans_error_id": midtrans_error_id,
            "attempted_payment_type": (attempted_payment_type if 'attempted_payment_type' in locals() else None),
            "fallback_used": (fallback_used if 'fallback_used' in locals() else None),
        }), HTTPStatus.BAD_REQUEST
    except Exception as e:
        session.rollback()
        current_app.logger.error(f"Error create QRIS bill: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/midtrans/selftest', methods=['POST'])
@admin_required
def midtrans_selftest(current_admin: User):
    """Self-test channel Midtrans untuk memastikan payment_type aktif (qris/gopay) via Core API.

    Catatan:
    - Ini akan memanggil endpoint charge Midtrans (bukan dry-run). Gunakan amount kecil.
    - Tidak menyimpan transaksi ke database.
    """
    json_data = request.get_json(silent=True) or {}

    payment_types_raw = json_data.get('payment_types')
    if isinstance(payment_types_raw, list) and payment_types_raw:
        payment_types = [str(x).strip().lower() for x in payment_types_raw if str(x).strip()]
    else:
        payment_types = ['qris', 'gopay']

    try:
        amount = int(json_data.get('amount') or 1000)
    except Exception:
        amount = 1000
    amount = max(1000, min(amount, 50000))

    def _parse_midtrans_api_response_from_message(message: str) -> dict[str, object] | None:
        try:
            marker = 'API response: `'
            if marker in message:
                json_part = message.split(marker, 1)[1]
                json_part = json_part.split('`', 1)[0]
                parsed = json.loads(json_part)
                return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
        return None

    core = get_midtrans_core_api_client()
    results: list[dict[str, object]] = []
    for payment_type in payment_types:
        order_id = f"MT-TEST-{payment_type.upper()}-{uuid.uuid4().hex[:10].upper()}"
        payload: dict[str, object] = {
            "payment_type": payment_type,
            "transaction_details": {"order_id": order_id, "gross_amount": amount},
            "item_details": [{
                "id": f"selftest-{payment_type}",
                "price": amount,
                "quantity": 1,
                "name": f"SelfTest {payment_type}"[:100],
            }],
            "customer_details": {
                "first_name": (str(getattr(current_admin, 'full_name', '') or 'Admin')[:50]),
                "phone": format_to_local_phone(str(getattr(current_admin, 'phone_number', '') or '')),
            },
        }
        if payment_type == 'gopay':
            payload["gopay"] = {"enable_callback": False}

        try:
            resp = core.charge(payload)
            if isinstance(resp, dict):
                results.append({
                    "payment_type": payment_type,
                    "order_id": order_id,
                    "ok": True,
                    "status_code": resp.get('status_code'),
                    "status_message": resp.get('status_message'),
                    "transaction_status": resp.get('transaction_status'),
                    "transaction_id": resp.get('transaction_id'),
                    "qr_code_url": extract_qr_code_url(resp),
                    "raw": resp,
                })
            else:
                results.append({
                    "payment_type": payment_type,
                    "order_id": order_id,
                    "ok": True,
                    "raw": resp,
                })
        except midtransclient.error_midtrans.MidtransAPIError as e:
            raw_message = getattr(e, 'message', '') or ''
            parsed = _parse_midtrans_api_response_from_message(raw_message) or {}
            results.append({
                "payment_type": payment_type,
                "order_id": order_id,
                "ok": False,
                "error": raw_message,
                "midtrans_status_code": parsed.get('status_code'),
                "midtrans_status_message": parsed.get('status_message'),
                "midtrans_error_id": parsed.get('id'),
            })

    return jsonify({
        "is_production": bool(current_app.config.get('MIDTRANS_IS_PRODUCTION', False)),
        "amount": amount,
        "results": results,
    }), HTTPStatus.OK


@admin_bp.route('/transactions/<order_id>/report.pdf', methods=['GET'])
@admin_required
def get_transaction_admin_report_pdf(current_admin: User, order_id: str):
    """PDF Admin report (berbeda dari invoice user) untuk audit transaksi + histori event."""
    if not WEASYPRINT_AVAILABLE or HTML is None:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    order_id = (order_id or "").strip()
    if not order_id:
        abort(HTTPStatus.BAD_REQUEST, "order_id tidak boleh kosong.")

    tx = db.session.scalar(
        select(Transaction)
        .where(Transaction.midtrans_order_id == order_id)
        .options(selectinload(Transaction.user), selectinload(Transaction.package))
    )
    if tx is None:
        abort(HTTPStatus.NOT_FOUND, "Transaksi tidak ditemukan.")

    payload: object | None = None
    if tx.midtrans_notification_payload:
        try:
            payload = json.loads(tx.midtrans_notification_payload)
        except Exception:
            payload = {"_raw": tx.midtrans_notification_payload}

    events_q = (
        select(TransactionEvent)
        .where(TransactionEvent.transaction_id == tx.id)
        .order_by(TransactionEvent.created_at.asc())
    )
    events = db.session.scalars(events_q).all()
    events_payload = []
    for ev in events:
        ev_payload: object | None = None
        if ev.payload:
            try:
                ev_payload = json.loads(ev.payload)
            except Exception:
                ev_payload = {"_raw": ev.payload}
        events_payload.append(
            {
                "created_at": ev.created_at,
                "source": ev.source.value,
                "event_type": ev.event_type,
                "status": ev.status.value if ev.status else None,
                "payload": ev_payload,
            }
        )

    app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
    context = {
        "transaction": tx,
        "user": tx.user,
        "package": tx.package,
        "status": tx.status.value,
        "report_date_local": datetime.now(app_tz),
        "business_name": current_app.config.get('BUSINESS_NAME', 'LPSaring'),
        "business_address": current_app.config.get('BUSINESS_ADDRESS', ''),
        "business_phone": current_app.config.get('BUSINESS_PHONE', ''),
        "business_email": current_app.config.get('BUSINESS_EMAIL', ''),
        "midtrans_payload": payload,
        "events": events_payload,
    }

    public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
    html_string = render_template('admin_transaction_report.html', **context)
    pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
    if not pdf_bytes:
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="admin-report-{order_id}.pdf"'
    return response

# --- Endpoint /action-logs DIHAPUS DARI SINI ---
# Logika ini sekarang sepenuhnya ditangani oleh action_log_routes.py