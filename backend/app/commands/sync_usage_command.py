# backend/app/commands/sync_usage_command.py
import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime, timezone as dt_timezone
import time
import logging

from app.extensions import db
from app.infrastructure.db.models import User, DailyUsageLog, UserRole, Transaction, Package, PackageProfile, TransactionStatus
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_hotspot_user_details,
    set_hotspot_user_limit,
    set_hotspot_user_profile,
    format_to_local_phone
)
from app.services import settings_service

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

USAGE_UPDATE_THRESHOLD_MB = 0.1
LIMIT_UPDATE_THRESHOLD_BYTES = 1024 # 1 KB, untuk mendeteksi perubahan kecil sekalipun
MAX_RETRIES = 3
RETRY_DELAY = 0.5

def _sync_user_with_retry(api, user, today, counters):
    """Menangani sinkronisasi satu user dengan mekanisme retry yang terisolasi."""
    username_08 = format_to_local_phone(user.phone_number)
    if not username_08:
        logger.warning(f"Skip user {user.id}: Format nomor salah '{user.phone_number}'")
        return False
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Panggil fungsi pemrosesan utama
            return _process_single_user(api, user, username_08, today, counters)
        except Exception as e:
            logger.error(f"Error proses user {username_08} (attempt {attempt}/{MAX_RETRIES}): {str(e)}", exc_info=True)
            time.sleep(RETRY_DELAY * attempt)
    
    logger.error(f"Gagal total sinkronisasi user {username_08} setelah {MAX_RETRIES} percobaan.")
    return False

def _process_single_user(api, user, username_08, today, counters):
    """
    Memproses sinkronisasi untuk satu user.
    Alur:
    1. Baca pemakaian dari MikroTik, update ke DB.
    2. Baca konfigurasi dari DB, paksakan/update ke MikroTik (self-healing).
    """
    success, mt_user, msg = get_hotspot_user_details(api, username_08)
    if not success or mt_user is None:
        logger.warning(f"Gagal ambil data atau user tidak ditemukan di Mikrotik untuk '{username_08}'. Pesan: {msg}. Melewati user ini.")
        return False

    # --- BAGIAN 1: Sinkronisasi Pemakaian (Arah: MikroTik -> Database) ---
    current_usage_bytes_mt = int(mt_user.get('bytes-in', '0') or '0') + int(mt_user.get('bytes-out', '0') or '0')
    current_usage_mb_mt = round(current_usage_bytes_mt / (1024 * 1024), 2)
    old_usage_mb_in_db = float(user.total_quota_used_mb or 0.0)
    
    # Update DB hanya jika ada perbedaan pemakaian yang signifikan
    if abs(old_usage_mb_in_db - current_usage_mb_mt) > USAGE_UPDATE_THRESHOLD_MB:
        delta_for_log = current_usage_mb_mt - old_usage_mb_in_db
        user.total_quota_used_mb = current_usage_mb_mt
        counters['db_usage_updates'] += 1
        
        # Catat pemakaian harian
        if delta_for_log > 0:
            daily_log = db.session.scalars(select(DailyUsageLog).where(DailyUsageLog.user_id == user.id, DailyUsageLog.log_date == today)).first()
            if daily_log:
                daily_log.usage_mb = (daily_log.usage_mb or 0) + delta_for_log
                counters['log_updated'] += 1
            else:
                db.session.add(DailyUsageLog(user_id=user.id, log_date=today, usage_mb=delta_for_log))
                counters['log_created'] += 1

    # --- BAGIAN 2: Sinkronisasi Konfigurasi / Self-Healing (Arah: Database -> MikroTik) ---
    
    # 2a. Tentukan limit kuota yang BENAR berdasarkan data di Database
    correct_limit_bytes_from_db = 0 if user.is_unlimited_user else int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
    mt_limit_bytes = int(mt_user.get('limit-bytes-total', '0') or '0')

    # Bandingkan dan perbaiki jika perlu
    if abs(correct_limit_bytes_from_db - mt_limit_bytes) > LIMIT_UPDATE_THRESHOLD_BYTES:
        logger.warning(
            f"Koreksi limit untuk '{username_08}': "
            f"Limit di DB seharusnya {correct_limit_bytes_from_db} B, tapi di MT {mt_limit_bytes} B. "
            f"Memperbaiki MT..."
        )
        limit_ok, limit_msg = set_hotspot_user_limit(api, username_08, correct_limit_bytes_from_db)
        if limit_ok:
            counters['limit_corrections'] += 1
        else:
            logger.error(f"Gagal memperbaiki limit untuk '{username_08}': {limit_msg}")

    # 2b. Tentukan profil yang BENAR berdasarkan data di Database
    now = datetime.now(dt_timezone.utc)
    is_expired = user.quota_expiry_date and user.quota_expiry_date < now
    expired_profile_name = settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired')
    
    correct_profile_from_db = expired_profile_name
    
    if not is_expired:
        # Jika tidak expired, cari profil dari transaksi terakhir yang sukses
        successful_txs = [tx for tx in user.transactions if tx.status == TransactionStatus.SUCCESS and tx.package and tx.payment_time]
        if successful_txs:
            last_success_tx = sorted(successful_txs, key=lambda x: x.payment_time, reverse=True)[0]
            if last_success_tx.package.profile:
                correct_profile_from_db = last_success_tx.package.profile.profile_name
            else: # Fallback jika paket tidak punya profil
                correct_profile_from_db = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        else: # Fallback jika tidak ada transaksi sukses
            correct_profile_from_db = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')

    mt_profile = mt_user.get('profile', '')
    
    # Bandingkan dan perbaiki jika perlu
    if correct_profile_from_db != mt_profile:
        logger.warning(
            f"Koreksi profil untuk '{username_08}': "
            f"Profil di DB seharusnya '{correct_profile_from_db}', tapi di MT '{mt_profile}'. "
            f"Memperbaiki MT..."
        )
        profile_ok, profile_msg = set_hotspot_user_profile(api, username_08, correct_profile_from_db)
        if profile_ok:
            counters['profile_corrections'] += 1
        else:
             logger.error(f"Gagal memperbaiki profil untuk '{username_08}': {profile_msg}")

    return True

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    """Sinkronisasi data pemakaian dari Mikrotik dan melakukan self-healing konfigurasi."""
    logger.info("Memulai sinkronisasi pengguna dengan Mikrotik...")
    start_time = time.time()
    
    try:
        # Eager load relasi yang dibutuhkan untuk mengurangi query N+1
        users_to_sync = db.session.scalars(select(User).where(
            User.is_active == True,
            User.role == UserRole.USER,
            User.approval_status == 'APPROVED'
        ).options(
            selectinload(User.transactions)
            .selectinload(Transaction.package)
            .selectinload(Package.profile)
        )).all()
    except SQLAlchemyError as e:
        logger.error(f"Error DB saat mengambil daftar pengguna: {e}", exc_info=True)
        return

    if not users_to_sync:
        logger.info("Tidak ada pengguna aktif untuk disinkronisasi.")
        return

    logger.info(f"Ditemukan {len(users_to_sync)} pengguna untuk diproses.")
    counters = { 
        'processed': 0, 'failed': 0, 
        'db_usage_updates': 0, 'limit_corrections': 0, 'profile_corrections': 0,
        'log_created': 0, 'log_updated': 0 
    }
    today = date.today()

    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal mendapatkan koneksi ke Mikrotik. Proses sinkronisasi dibatalkan.")
            return
        
        for user in users_to_sync:
            if _sync_user_with_retry(api, user, today, counters):
                counters['processed'] += 1
            else:
                counters['failed'] += 1

    try:
        # Commit semua perubahan yang terkumpul dari loop
        if db.session.dirty or db.session.new:
            logger.info("Menyimpan semua perubahan (pemakaian dan log harian) ke database...")
            db.session.commit()
            logger.info("Penyimpanan ke database berhasil.")
        else:
            logger.info("Tidak ada perubahan data pemakaian yang perlu disimpan ke database.")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Gagal menyimpan perubahan ke database setelah loop selesai: {e}", exc_info=True)

    duration = time.time() - start_time
    logger.info(
        f"Sinkronisasi selesai dalam {duration:.2f} detik.\n"
        f"================= HASIL SINKRONISASI =================\n"
        f"  - Pengguna Sukses Diproses: {counters['processed']}\n"
        f"  - Pengguna Gagal Diproses : {counters['failed']}\n"
        f"  --------------------------------------------------\n"
        f"  - Update Pemakaian di DB  : {counters['db_usage_updates']}\n"
        f"  - Koreksi Limit di MT     : {counters['limit_corrections']}\n"
        f"  - Koreksi Profil di MT    : {counters['profile_corrections']}\n"
        f"  - Log Harian Baru         : {counters['log_created']}\n"
        f"  - Log Harian Diperbarui   : {counters['log_updated']}\n"
        f"======================================================"
    )