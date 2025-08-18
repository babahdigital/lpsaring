# backend/app/commands/cleanup_inactive_command.py
# pyright: reportAttributeAccessIssue=false
import click
from flask.cli import with_appcontext
from sqlalchemy import select
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, delete_hotspot_user

logger = logging.getLogger(__name__)

# --- Konfigurasi ---
# Pengguna dianggap tidak aktif jika tanggal kadaluarsanya sudah lewat dari X bulan
INACTIVITY_MONTHS_THRESHOLD = 6 

@click.command('cleanup-inactive')
@with_appcontext
def cleanup_inactive_command():
    """
    Script untuk menghapus pengguna yang sudah lama tidak aktif.
    Idealnya dijalankan oleh cron job setiap beberapa bulan atau setahun sekali.
    """
    logger.info("Memulai proses pembersihan pengguna tidak aktif...")

    # Tentukan tanggal batas (cutoff date)
    cutoff_date = datetime.now() - relativedelta(months=INACTIVITY_MONTHS_THRESHOLD)
    logger.info(f"Ambang batas waktu non-aktif: sebelum {cutoff_date.strftime('%Y-%m-%d')}")

    # Cari pengguna yang quota_expiry_date nya sudah lewat dari tanggal batas
    users_to_delete = db.session.scalars(select(User).where(User.quota_expiry_date < cutoff_date)).all()

    if not users_to_delete:
        logger.info("Tidak ada pengguna tidak aktif yang perlu dihapus.")
        return
        
    logger.info(f"Ditemukan {len(users_to_delete)} pengguna tidak aktif untuk dihapus.")
    
    success_count = 0
    fail_count = 0
    
    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal mendapatkan koneksi MikroTik. Proses dibatalkan.")
            return
            
        for user in users_to_delete:
            logger.warning(f"Menghapus pengguna: {user.full_name} (kadaluarsa pada {user.quota_expiry_date})...")
            
            # 1. Hapus dari MikroTik
            mikrotik_success, msg = delete_hotspot_user(api, user.phone_number)
            if not mikrotik_success:
                logger.error(f"  -> Gagal menghapus {user.full_name} dari MikroTik: {msg}")
                fail_count += 1
                continue # Lanjut ke user berikutnya jika gagal di MT

            # 2. Hapus dari Database
            try:
                db.session.delete(user)
                logger.info(f"  -> Berhasil menghapus {user.full_name} dari database.")
                success_count += 1
            except Exception as e:
                logger.error(f"  -> Gagal menghapus {user.full_name} dari database: {e}")
                fail_count += 1

    try:
        logger.info("Menyimpan perubahan (penghapusan) ke database...")
        db.session.commit()
        logger.info("Penyimpanan berhasil.")
    except Exception as e:
        logger.error(f"Gagal menyimpan penghapusan ke database: {e}")
        db.session.rollback()

    logger.info(f"Proses pembersihan selesai. Berhasil dihapus: {success_count}, Gagal: {fail_count}.")