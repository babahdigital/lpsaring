# backend/app/commands/monthly_reset_command.py
import click
from flask.cli import with_appcontext
from sqlalchemy import select
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import logging

from app.extensions import db
from app.infrastructure.db.models import User, UserRole
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, set_hotspot_user_profile, format_to_local_phone
from app.services import settings_service

logger = logging.getLogger(__name__)

# --- Konfigurasi ---
# Kuota default yang diberikan setiap bulan (dalam MB).
# Anda bisa membuat ini lebih dinamis sesuai paket user jika perlu.
DEFAULT_MONTHLY_QUOTA_MB = 5000

def _reset_user(api, user_to_reset, default_profile_name):
    """Logika untuk mereset satu pengguna."""
    username_08 = format_to_local_phone(user_to_reset.phone_number)
    if not username_08:
        logger.warning(f"Melewatkan reset untuk User ID {user_to_reset.id} karena nomor telepon tidak valid.")
        return False
        
    logger.info(f"Mereset pengguna: {user_to_reset.full_name} ({username_08})...")

    # 1. Reset data di database aplikasi
    user_to_reset.total_quota_used_mb = 0
    user_to_reset.total_quota_purchased_mb = DEFAULT_MONTHLY_QUOTA_MB
    # Atur tanggal kadaluarsa ke akhir bulan berikutnya
    user_to_reset.quota_expiry_date = (datetime.now() + relativedelta(months=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0) + relativedelta(months=1) - relativedelta(days=1)
    
    # 2. Reset data di MikroTik
    try:
        # Panggil perintah untuk mereset counter bytes
        user_resource = api.get_resource('/ip/hotspot/user')
        user_resource.call('reset-counters', {'numbers': username_08})
        logger.info(f"  -> Counter di MikroTik untuk {username_08} berhasil di-reset.")

        # Pastikan profilnya adalah 'default'
        set_hotspot_user_profile(api, username_08, default_profile_name)
        logger.info(f"  -> Profil untuk {username_08} dipastikan '{default_profile_name}'.")

    except Exception as e:
        logger.error(f"  -> Gagal mereset data di MikroTik untuk {username_08}: {e}")
        return False
        
    return True

@click.command('monthly-reset')
@with_appcontext
def monthly_reset_command():
    """
    Script untuk mereset kuota bulanan semua pengguna aktif.
    Idealnya dijalankan oleh cron job pada tanggal 1 setiap bulan.
    """
    logger.info("Memulai proses reset kuota bulanan...")
    
    default_profile = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
    if not default_profile:
        logger.error("Nama profil default tidak ditemukan di pengaturan. Proses dibatalkan.")
        return

    # Ambil semua pengguna USER yang aktif
    users_to_reset = db.session.scalars(select(User).where(User.role == UserRole.USER, User.is_active == True)).all()

    if not users_to_reset:
        logger.info("Tidak ada pengguna aktif untuk di-reset.")
        return

    logger.info(f"Ditemukan {len(users_to_reset)} pengguna untuk di-reset.")
    
    success_count = 0
    fail_count = 0

    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal mendapatkan koneksi MikroTik. Proses dibatalkan.")
            return

        for user in users_to_reset:
            if _reset_user(api, user, default_profile):
                success_count += 1
            else:
                fail_count += 1
    
    try:
        logger.info("Menyimpan semua perubahan reset ke database...")
        db.session.commit()
        logger.info("Penyimpanan berhasil.")
    except Exception as e:
        logger.error(f"Gagal menyimpan perubahan ke database: {e}")
        db.session.rollback()

    logger.info(f"Proses reset bulanan selesai. Berhasil: {success_count}, Gagal: {fail_count}.")