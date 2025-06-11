# backend/app/commands/sync_usage_command.py
# Versi 4.0: Perbaikan menyeluruh dengan mekanisme retry dan toleransi perbedaan
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime, timezone as dt_timezone
import time
import logging

from app.extensions import db
from app.infrastructure.db.models import User, DailyUsageLog, UserRole
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_hotspot_user_details,
    set_hotspot_user_limit,
    set_hotspot_user_profile,
    format_to_local_phone
)
from app.services import settings_service

# Setup logger khusus untuk perintah ini
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Toleransi perbedaan usage dalam MB sebelum update DB
USAGE_UPDATE_THRESHOLD_MB = 0.1
# Toleransi perbedaan limit dalam bytes (1KB)
LIMIT_UPDATE_THRESHOLD_BYTES = 1024
# Jumlah maksimal percobaan untuk operasi sinkronisasi per user
MAX_RETRIES = 3
# Jeda antar percobaan (dalam detik)
RETRY_DELAY = 0.5

def _sync_user_with_retry(api, user, today, counters):
    """Menangani sinkronisasi satu user dengan mekanisme retry"""
    username_08 = format_to_local_phone(user.phone_number)
    if not username_08:
        logger.warning(f"Skip user {user.id}: Format nomor salah '{user.phone_number}'")
        return False
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _process_single_user(api, user, username_08, today, counters)
        except Exception as e:
            logger.error(f"Error proses user {username_08} (attempt {attempt}/{MAX_RETRIES}): {str(e)}")
            time.sleep(RETRY_DELAY * attempt)
    
    logger.error(f"Gagal sinkron user {username_08} setelah {MAX_RETRIES} percobaan")
    return False

def _process_single_user(api, user, username_08, today, counters):
    """Memproses sinkronisasi untuk satu user"""
    # 1. Ambil data penggunaan dari Mikrotik
    success, mt_user, msg = get_hotspot_user_details(api, username_08)
    if not success:
        logger.error(f"Gagal ambil data {username_08}: {msg}")
        return False
    
    if mt_user is None:
        logger.warning(f"User {username_08} ada di DB tapi tidak di Mikrotik")
        return False

    # 2. Hitung pemakaian saat ini
    current_usage_bytes = 0
    try:
        bytes_in = int(mt_user.get('bytes-in', 0) or 0
        bytes_out = int(mt_user.get('bytes-out', 0) or 0
        current_usage_bytes = bytes_in + bytes_out
    except (TypeError, ValueError) as e:
        logger.error(f"Error parsing usage for {username_08}: {e}")
        return False
    
    current_usage_mb = round(current_usage_bytes / (1024 * 1024), 2)
    old_usage_mb_in_db = user.total_quota_used_mb or 0.0
    
    # 3. Update log harian jika ada pemakaian baru
    delta_usage_mb = max(0, current_usage_mb - old_usage_mb_in_db)
    if delta_usage_mb > 0:
        try:
            log_stmt = select(DailyUsageLog).where(
                DailyUsageLog.user_id == user.id,
                DailyUsageLog.log_date == today
            )
            daily_log = db.session.scalars(log_stmt).first()

            if daily_log:
                daily_log.usage_mb = (daily_log.usage_mb or 0) + delta_usage_mb
                counters['log_updated'] += 1
            else:
                new_log = DailyUsageLog(
                    user_id=user.id,
                    log_date=today,
                    usage_mb=delta_usage_mb
                )
                db.session.add(new_log)
                counters['log_created'] += 1
        except Exception as log_err:
            logger.error(f"Error logging untuk {user.id}: {log_err}")

    # 4. Update total pemakaian di DB jika ada perbedaan signifikan
    usage_diff = abs(old_usage_mb_in_db - current_usage_mb)
    if usage_diff > USAGE_UPDATE_THRESHOLD_MB or current_usage_mb < old_usage_mb_in_db:
        user.total_quota_used_mb = current_usage_mb
        counters['db_updates'] += 1
        logger.info(f"Update usage {username_08}: {old_usage_mb_in_db:.2f}MB -> {current_usage_mb:.2f}MB")

    # 5. Sinkronisasi limit kuota ke Mikrotik
    db_quota_bytes = int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
    mt_limit_bytes = int(mt_user.get('limit-bytes-total', 0) or 0
    
    # Periksa perbedaan yang signifikan
    if abs(db_quota_bytes - mt_limit_bytes) > LIMIT_UPDATE_THRESHOLD_BYTES:
        logger.info(f"Limit sync {username_08}: DB={db_quota_bytes} MT={mt_limit_bytes}")
        limit_ok, limit_msg = set_hotspot_user_limit(api, username_08, db_quota_bytes)
        if limit_ok:
            counters['limit_updates'] += 1
        else:
            logger.error(f"Gagal update limit {username_08}: {limit_msg}")

    # 6. Sinkronisasi profil
    is_expired = user.quota_expiry_date and user.quota_expiry_date < datetime.now(dt_timezone.utc)
    correct_profile = settings_service.get_setting(
        'MIKROTIK_EXPIRED_PROFILE', 'expired' if is_expired else 'default'
    )
    mt_profile = mt_user.get('profile', '')
    
    if correct_profile != mt_profile:
        logger.info(f"Profile sync {username_08}: {mt_profile} -> {correct_profile}")
        profile_ok, profile_msg = set_hotspot_user_profile(api, username_08, correct_profile)
        if profile_ok:
            counters['profile_updates'] += 1
        else:
            logger.error(f"Gagal update profile {username_08}: {profile_msg}")
    
    return True

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    """Sinkronisasi komprehensif dengan mekanisme retry dan toleransi perbedaan"""
    logger.info("Memulai sinkronisasi pengguna dengan Mikrotik...")
    start_time = time.time()

    # Ambil pengaturan profil
    try:
        DEFAULT_PROFILE = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        EXPIRED_PROFILE = settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired')
        if not DEFAULT_PROFILE or not EXPIRED_PROFILE:
            logger.error("Sinkronisasi dibatalkan: Profil belum diatur")
            return
    except Exception as e:
        logger.error(f"Gagal ambil pengaturan: {e}", exc_info=True)
        return

    # Ambil semua pengguna aktif
    try:
        stmt = select(User).filter(
            User.is_active == True,
            User.role == UserRole.USER,
            User.approval_status == 'APPROVED'
        )
        users_to_sync = db.session.scalars(stmt).all()
    except SQLAlchemyError as e:
        logger.error(f"Error DB ambil user: {e}", exc_info=True)
        return

    if not users_to_sync:
        logger.info("Tidak ada pengguna aktif")
        return

    logger.info(f"Ditemukan {len(users_to_sync)} pengguna untuk sinkronisasi")

    # Inisialisasi counter
    counters = {
        'processed': 0,
        'failed': 0,
        'db_updates': 0,
        'limit_updates': 0,
        'profile_updates': 0,
        'log_created': 0,
        'log_updated': 0
    }
    today = date.today()

    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal dapat koneksi Mikrotik")
            return
        
        # Dapatkan identitas Mikrotik untuk logging
        try:
            identity = api.get_resource('/system/identity').get()
            logger.info(f"Terhubung ke Mikrotik: {identity[0].get('name', 'N/A')}")
        except Exception as e:
            logger.warning(f"Gagal dapat identitas: {e}")

        # Proses setiap user
        for user in users_to_sync:
            success = _sync_user_with_retry(api, user, today, counters)
            if success:
                counters['processed'] += 1
            else:
                counters['failed'] += 1

    # Commit perubahan ke DB
    try:
        if db.session.dirty or db.session.new:
            logger.info(f"Commit {len(db.session.dirty) + len(db.session.new)} perubahan ke DB...")
            db.session.commit()
            logger.info("Commit berhasil")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Gagal commit DB: {e}", exc_info=True)

    # Log hasil akhir
    duration = time.time() - start_time
    logger.info(
        f"Sinkronisasi selesai. Waktu: {duration:.2f} detik\n"
        f"Total diproses: {counters['processed']}\n"
        f"Gagal: {counters['failed']}\n"
        f"Update DB: {counters['db_updates']}\n"
        f"Update Limit: {counters['limit_updates']}\n"
        f"Update Profil: {counters['profile_updates']}\n"
        f"Log baru: {counters['log_created']}\n"
        f"Log update: {counters['log_updated']}"
    )