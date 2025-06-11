# backend/app/commands/sync_usage_command.py
# Versi 3.1: Final - Sinkronisasi komprehensif DITAMBAH logging pemakaian harian.
# - PULL: Mengambil data pemakaian (usage) dari MikroTik ke DB.
# - PUSH: Mendorong/memaksa sinkronisasi limit kuota dan status profil dari DB ke MikroTik.
# - LOG: Mencatat penambahan pemakaian harian ke tabel DailyUsageLog.

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime, timezone as dt_timezone

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

# Toleransi perbedaan usage dalam MB sebelum update DB (untuk mengurangi write)
USAGE_UPDATE_THRESHOLD_MB = 0.1

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    """
    Menyinkronkan status pengguna antara database dan MikroTik secara komprehensif,
    termasuk mencatat pemakaian harian.
    """
    current_app.logger.info("Memulai sinkronisasi status pengguna dengan MikroTik...")

    # Ambil kunci konfigurasi dari DB settings
    try:
        DEFAULT_PROFILE = settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        EXPIRED_PROFILE = settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired')
        if not DEFAULT_PROFILE or not EXPIRED_PROFILE:
            current_app.logger.error("Sinkronisasi dibatalkan: Nama profil default atau expired belum diatur di Application Settings.")
            return
    except Exception as e:
        current_app.logger.error(f"Gagal mengambil pengaturan profil dari DB: {e}", exc_info=True)
        return

    # Ambil semua pengguna reguler yang aktif dari DB
    try:
        stmt = select(User).filter(User.is_active == True, User.role == UserRole.USER)
        users_to_sync = db.session.scalars(stmt).all()
    except SQLAlchemyError as e:
        current_app.logger.error(f"Sinkronisasi dibatalkan: Error DB saat mengambil pengguna: {e}", exc_info=True)
        return

    if not users_to_sync:
        current_app.logger.info("Tidak ada pengguna aktif yang perlu disinkronkan.")
        return

    current_app.logger.info(f"Ditemukan {len(users_to_sync)} pengguna aktif untuk disinkronkan.")

    # Inisialisasi counter
    processed_count, failed_count, db_updates, limit_updates, profile_updates, log_created, log_updated = 0, 0, 0, 0, 0, 0, 0
    today = date.today()

    with get_mikrotik_connection() as api:
        if not api:
            current_app.logger.error("Sinkronisasi dibatalkan: Gagal mendapatkan koneksi API MikroTik.")
            return
        
        identity = api.get_resource('/system/identity').get()
        current_app.logger.info(f"Terhubung ke MikroTik '{identity[0].get('name', 'N/A')}' untuk tugas sinkronisasi.")

        for user in users_to_sync:
            username_08 = format_to_local_phone(user.phone_number)
            if not username_08:
                current_app.logger.warning(f"Melewati user ID {user.id}: tidak dapat memformat nomor telepon '{user.phone_number}'.")
                failed_count += 1
                continue

            try:
                # 1. Ambil detail lengkap user dari MikroTik
                success, mt_user, msg = get_hotspot_user_details(api, username_08)
                if not success:
                    current_app.logger.error(f"Gagal mengambil detail untuk '{username_08}': {msg}. Melewati user ini.")
                    failed_count += 1
                    continue
                
                if mt_user is None:
                    current_app.logger.warning(f"Discrepancy: User '{username_08}' (DB ID: {user.id}) ada di DB tapi tidak di MikroTik. Melewati user ini.")
                    failed_count += 1
                    continue

                # 2. Sinkronisasi PENGGUNAAN (PULL dari MikroTik ke DB) dan LOGGING HARIAN
                current_usage_bytes = int(mt_user.get('bytes-in', 0) or 0) + int(mt_user.get('bytes-out', 0) or 0)
                current_usage_mb = round(current_usage_bytes / (1024 * 1024), 2)
                old_usage_mb_in_db = user.total_quota_used_mb or 0.0
                
                # Hitung delta pemakaian sejak sinkronisasi terakhir
                delta_usage_mb = max(0, current_usage_mb - old_usage_mb_in_db)

                if delta_usage_mb > 0:
                    try:
                        log_stmt = select(DailyUsageLog).where(DailyUsageLog.user_id == user.id, DailyUsageLog.log_date == today)
                        daily_log = db.session.scalars(log_stmt).first()

                        if daily_log:
                            daily_log.usage_mb = (daily_log.usage_mb or 0) + delta_usage_mb
                            log_updated += 1
                        else:
                            new_log = DailyUsageLog(user_id=user.id, log_date=today, usage_mb=delta_usage_mb)
                            db.session.add(new_log)
                            log_created += 1
                    except Exception as log_err:
                        current_app.logger.error(f"Error saat logging pemakaian harian untuk user {user.id}: {log_err}", exc_info=True)

                if abs(old_usage_mb_in_db - current_usage_mb) > USAGE_UPDATE_THRESHOLD_MB:
                    user.total_quota_used_mb = current_usage_mb
                    db_updates += 1
                    current_app.logger.info(f"Usage Sync for '{username_08}': DB updated from {old_usage_mb_in_db:.2f}MB to {current_usage_mb:.2f}MB.")

                # 3. Sinkronisasi BATAS KUOTA (PUSH dari DB ke MikroTik, jika beda)
                db_quota_bytes = int(user.total_quota_purchased_mb or 0) * 1024 * 1024
                mt_limit_bytes = int(mt_user.get('limit-bytes-total', 0) or 0)
                
                if db_quota_bytes != mt_limit_bytes:
                    current_app.logger.info(f"Limit Sync for '{username_08}': DB wants {db_quota_bytes} bytes, MikroTik has {mt_limit_bytes}. Updating MikroTik.")
                    limit_ok, limit_msg = set_hotspot_user_limit(api, username_08, db_quota_bytes)
                    if limit_ok:
                        limit_updates += 1
                    else:
                        current_app.logger.error(f"Gagal update limit untuk '{username_08}': {limit_msg}")

                # 4. Sinkronisasi PROFIL (PUSH dari DB ke MikroTik, jika beda)
                is_expired_in_db = user.quota_expiry_date is not None and user.quota_expiry_date < datetime.now(dt_timezone.utc)
                correct_profile = EXPIRED_PROFILE if is_expired_in_db else DEFAULT_PROFILE
                mt_profile = mt_user.get('profile')

                if correct_profile != mt_profile:
                    current_app.logger.info(f"Profile Sync for '{username_08}': DB state implies '{correct_profile}', MikroTik has '{mt_profile}'. Updating MikroTik.")
                    profile_ok, profile_msg = set_hotspot_user_profile(api, username_08, correct_profile)
                    if profile_ok:
                        profile_updates += 1
                    else:
                        current_app.logger.error(f"Gagal update profil untuk '{username_08}': {profile_msg}")
                
                processed_count += 1

            except Exception as e:
                current_app.logger.error(f"Error tidak terduga saat memproses user '{username_08}' (DB ID: {user.id}): {e}", exc_info=True)
                failed_count += 1
    
    # Commit semua perubahan ke DB sekaligus di akhir
    if db.session.dirty or db.session.new:
        current_app.logger.info(f"Menyimpan {len(db.session.dirty) + len(db.session.new)} pembaruan ke database...")
        try:
            db.session.commit()
            current_app.logger.info("Semua pembaruan berhasil disimpan.")
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error DB saat menyimpan pembaruan: {e}", exc_info=True)

    current_app.logger.info(
        f"Sinkronisasi Selesai. "
        f"Total Diproses: {processed_count}, Gagal/Dilewati: {failed_count}, "
        f"Update Usage DB: {db_updates}, Update Limit MT: {limit_updates}, Update Profil MT: {profile_updates}, "
        f"Log Harian Dibuat: {log_created}, Log Harian Diperbarui: {log_updated}"
    )