# backend/app/commands/sync_usage_command.py
# VERSI SEMPURNA & OPTIMAL: Menghindari pemanggilan helper yang tidak perlu di dalam loop.

import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime, timezone as dt_timezone
import time
import logging

from app.extensions import db
from app.infrastructure.db.models import User, DailyUsageLog, UserRole, Transaction, Package
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, get_hotspot_user_details, set_hotspot_user_profile
from app.utils.formatters import format_to_local_phone
from app.services import settings_service

# Helper _handle_mikrotik_operation tidak lagi dibutuhkan di file ini
# from app.services.user_management.helpers import _handle_mikrotik_operation

logger = logging.getLogger(__name__)

def _process_single_user(api, user, today, counters):
    username_08 = format_to_local_phone(user.phone_number)
    if not username_08:
        logger.warning(f"Skip user {user.id}: Format nomor salah '{user.phone_number}'")
        return False

    success, mt_user, msg = get_hotspot_user_details(api, username_08)
    if not success or not mt_user:
        logger.warning(f"Gagal ambil data atau user tidak ditemukan di Mikrotik untuk '{username_08}': {msg}.")
        return False

    current_usage_bytes_mt = int(mt_user.get('bytes-in', '0')) + int(mt_user.get('bytes-out', '0'))
    current_usage_mb_mt = round(current_usage_bytes_mt / (1024 * 1024), 2)
    old_usage_mb_in_db = float(user.total_quota_used_mb or 0.0)
    
    if abs(old_usage_mb_in_db - current_usage_mb_mt) > 0.1:
        delta_for_log = current_usage_mb_mt - old_usage_mb_in_db
        user.total_quota_used_mb = current_usage_mb_mt
        counters['db_usage_updates'] += 1
        
        if delta_for_log > 0:
            daily_log = db.session.scalar(select(DailyUsageLog).where(DailyUsageLog.user_id == user.id, DailyUsageLog.log_date == today))
            if daily_log:
                daily_log.usage_mb = (daily_log.usage_mb or 0) + delta_for_log
            else:
                db.session.add(DailyUsageLog(user_id=user.id, log_date=today, usage_mb=delta_for_log))

    now_utc = datetime.now(dt_timezone.utc)
    is_expired = user.quota_expiry_date and user.quota_expiry_date < now_utc
    
    expired_profile = settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired')
    if is_expired and mt_user.get('profile') != expired_profile:
        logger.info(f"User '{username_08}' expired. Moving to expired profile '{expired_profile}'.")
        
        # --- [OPTIMASI] ---
        # Panggil fungsi Mikrotik secara langsung karena kita sudah punya koneksi 'api'.
        # Ini lebih efisien daripada memanggil helper yang akan membuat koneksi baru.
        try:
            success, message = set_hotspot_user_profile(
                api_connection=api,
                username_or_id=username_08,
                new_profile_name=expired_profile
            )
            if success:
                counters['profile_corrections'] += 1
                logger.info(f"Berhasil memindahkan user '{username_08}' ke profil expired.")
            else:
                logger.error(f"Gagal memindahkan user '{username_08}' ke profil expired: {message}")
        except Exception as e:
            logger.error(f"Error saat memindahkan user '{username_08}' ke profil expired: {e}", exc_info=True)
            
    return True

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    logger.info("Memulai sinkronisasi pengguna dengan Mikrotik...")
    start_time = time.time()
    
    try:
        users_to_sync = db.session.scalars(select(User).where(
            User.is_active == True,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
            User.approval_status == 'APPROVED'
        ).options(selectinload(User.transactions).selectinload(Transaction.package))).all()
    except SQLAlchemyError as e:
        logger.error(f"Error DB saat mengambil daftar pengguna: {e}")
        return

    if not users_to_sync:
        logger.info("Tidak ada pengguna aktif untuk disinkronkan.")
        return

    counters = {'processed': 0, 'failed': 0, 'db_usage_updates': 0, 'profile_corrections': 0}
    today = date.today()

    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal mendapatkan koneksi ke Mikrotik. Proses dibatalkan.")
            return
        
        for user in users_to_sync:
            try:
                if _process_single_user(api, user, today, counters):
                    counters['processed'] += 1
                else:
                    counters['failed'] += 1
            except Exception as e:
                logger.error(f"Error tak terduga saat proses user {user.id}: {e}", exc_info=True)
                counters['failed'] += 1

    try:
        if db.session.dirty or db.session.new:
            db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Gagal menyimpan perubahan ke database: {e}")

    duration = time.time() - start_time
    logger.info(f"Sinkronisasi selesai dalam {duration:.2f} detik. Hasil: {counters}")