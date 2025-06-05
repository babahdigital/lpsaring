# backend/app/commands/sync_usage_command.py
# Versi 2.9: Modifikasi untuk mencatat penggunaan harian ke DailyUsageLog

# Tampilkan bantuan Flask CLI di container backend
# docker-compose exec backend flask --help

# Jalankan sinkronisasi penggunaan manual di container backend
# docker-compose exec backend flask sync-usage

# Penting:
# Setelah tes manual 'flask sync-usage' berhasil dan diverifikasi,
# jadwalkan perintah tersebut agar otomatis berjalan (misal pakai cron di host).
# Jangan jadwalkan di dalam container.

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import or_, select, func as sqlfunc # Import func as sqlfunc
from sqlalchemy.exc import SQLAlchemyError
from datetime import date # Import date

from app.extensions import db
# Import User dan DailyUsageLog
from app.infrastructure.db.models import User, DailyUsageLog
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_hotspot_user_usage,
    set_hotspot_user_limit,
    format_to_local_phone
)

# Toleransi perbedaan usage dalam MB sebelum update DB (untuk mengurangi write)
USAGE_UPDATE_THRESHOLD_MB = 0.1

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    """
    Synchronize user quota usage from MikroTik to the application database
    and log daily usage increments.
    """
    current_app.logger.info("Starting user quota usage synchronization and daily logging...")

    # Dapatkan koneksi pool MikroTik
    mikrotik_conn_pool = get_mikrotik_connection()
    if not mikrotik_conn_pool:
        current_app.logger.error("Synchronization aborted: Failed to get MikroTik connection pool.")
        return

    # Ambil semua user yang relevan dari DB
    try:
        stmt = select(User).filter(
            User.is_active == True,
            or_(User.total_quota_purchased_mb > 0, User.total_quota_used_mb > 0)
        )
        users_to_sync = db.session.scalars(stmt).all()
    except SQLAlchemyError as e:
         current_app.logger.error(f"Synchronization aborted: DB error fetching users to sync: {e}", exc_info=True)
         return
    except Exception as e:
         current_app.logger.error(f"Synchronization aborted: Unexpected error fetching users: {e}", exc_info=True)
         return

    if not users_to_sync:
        current_app.logger.info("No active users found requiring usage synchronization.")
        return

    current_app.logger.info(f"Found {len(users_to_sync)} active users to potentially sync.")

    # Inisialisasi counter
    synced_count = 0
    failed_sync_count = 0
    db_update_count = 0
    limit_update_count = 0
    log_created_count = 0
    log_updated_count = 0
    users_to_commit = []
    logs_to_commit = [] # List untuk menyimpan log yang akan di-commit

    # Dapatkan koneksi API dari pool dan tes koneksi
    api = None
    try:
        api = mikrotik_conn_pool.get_api()
        identity = api.get_resource('/system/identity').get()
        current_app.logger.info(f"Successfully connected to MikroTik '{identity[0].get('name', 'N/A')}' for sync job.")
    except Exception as conn_err:
        current_app.logger.error(f"Synchronization aborted: Failed to get/verify API connection from pool: {conn_err}", exc_info=True)
        return

    # Dapatkan tanggal hari ini sekali saja
    today = date.today()

    # Loop melalui setiap user
    for user in users_to_sync:
        # Ambil username format 08... untuk interaksi MikroTik
        username_08 = format_to_local_phone(user.phone_number)

        if not username_08:
            current_app.logger.warning(f"Skipping user ID {user.id}: Could not format phone number '{user.phone_number}' to 08 format.")
            failed_sync_count += 1
            continue

        try:
            # 1. Ambil data usage dari MikroTik menggunakan username 08...
            success, usage_data, error_msg = get_hotspot_user_usage(mikrotik_conn_pool, username_08)

            if not success:
                current_app.logger.warning(f"Failed to get usage for user '{username_08}': {error_msg}")
                failed_sync_count += 1
                continue

            if usage_data is None:
                current_app.logger.info(f"User '{username_08}' not found in MikroTik during sync. Skipping.")
                continue

            # 2. Hitung usage dalam MB
            bytes_in = usage_data.get('bytes-in', 0)
            bytes_out = usage_data.get('bytes-out', 0)
            current_usage_bytes = bytes_in + bytes_out
            current_usage_mb = round(current_usage_bytes / (1024 * 1024), 2)

            # --- BARU: Log Penggunaan Harian ---
            # Simpan nilai usage lama SEBELUM diupdate
            old_usage_mb = user.total_quota_used_mb or 0
            # Hitung delta (penambahan) penggunaan sejak sync terakhir
            delta_usage_mb = max(0, current_usage_mb - old_usage_mb) # Pastikan delta tidak negatif

            if delta_usage_mb > 0: # Hanya log jika ada penambahan penggunaan
                try:
                    # Coba cari log untuk user ini pada hari ini
                    # Gunakan select().where() untuk query yang lebih eksplisit
                    log_stmt = select(DailyUsageLog).where(
                        DailyUsageLog.user_id == user.id,
                        DailyUsageLog.log_date == today
                    )
                    daily_log = db.session.scalars(log_stmt).first()

                    if daily_log:
                        # Jika log sudah ada, tambahkan delta
                        daily_log.usage_mb = (daily_log.usage_mb or 0) + delta_usage_mb
                        if daily_log not in logs_to_commit:
                            logs_to_commit.append(daily_log)
                        log_updated_count += 1
                        current_app.logger.debug(f"Updating daily log for user {user.id} on {today}: added {delta_usage_mb:.2f} MB")
                    else:
                        # Jika log belum ada, buat baru
                        new_log = DailyUsageLog(
                            user_id=user.id,
                            log_date=today,
                            usage_mb=delta_usage_mb
                        )
                        db.session.add(new_log) # Tambahkan ke sesi
                        if new_log not in logs_to_commit:
                             logs_to_commit.append(new_log) # Tandai untuk commit
                        log_created_count += 1
                        current_app.logger.debug(f"Creating new daily log for user {user.id} on {today}: {delta_usage_mb:.2f} MB")

                except SQLAlchemyError as log_db_err:
                    current_app.logger.error(f"DB error while finding/creating daily log for user {user.id} on {today}: {log_db_err}", exc_info=True)
                    # Pertimbangkan: Lanjutkan sync user lain atau rollback? Untuk sementara, log error dan lanjut.
                except Exception as log_err:
                     current_app.logger.error(f"Unexpected error during daily logging for user {user.id} on {today}: {log_err}", exc_info=True)
            # --- AKHIR BARU ---

            # 3. Bandingkan dengan data di DB dan update jika perlu (setelah logging delta)
            # Gunakan old_usage_mb yang sudah disimpan sebelumnya
            if abs(old_usage_mb - current_usage_mb) > USAGE_UPDATE_THRESHOLD_MB:
                current_app.logger.info(f"Updating total usage for user '{username_08}' (DB ID: {user.id}): DB {old_usage_mb:.2f}MB -> MikroTik {current_usage_mb:.2f}MB")
                user.total_quota_used_mb = current_usage_mb
                if user not in users_to_commit:
                    users_to_commit.append(user) # Tandai user untuk commit
                db_update_count += 1

                # 4. (Opsional tapi direkomendasikan) Update limit di MikroTik
                purchased_mb = user.total_quota_purchased_mb or 0
                remaining_mb = max(0, purchased_mb - current_usage_mb)
                limit_bytes_total = int(remaining_mb * 1024 * 1024)

                # Gunakan username 08... untuk set limit
                limit_success, limit_msg = set_hotspot_user_limit(mikrotik_conn_pool, username_08, limit_bytes_total)
                if limit_success:
                    limit_update_count += 1
                else:
                    current_app.logger.warning(f"Failed to update MikroTik limit for '{username_08}' during sync: {limit_msg}")

            synced_count += 1

        except Exception as inner_e:
            current_app.logger.error(f"Error processing user '{username_08}' (DB ID: {user.id}) during sync: {inner_e}", exc_info=True)
            failed_sync_count += 1
            # Rollback perubahan spesifik user ini jika terjadi error di tengah?
            # Untuk saat ini, kita commit semua yang berhasil di akhir.

    # --- Commit Perubahan ke Database ---
    # Commit semua user dan log yang berhasil diproses
    items_to_commit = users_to_commit + logs_to_commit
    if items_to_commit:
        current_app.logger.info(f"Attempting to commit updates for {len(users_to_commit)} users and {len(logs_to_commit)} logs...")
        try:
            # Tidak perlu add() lagi karena objek sudah dalam sesi atau ditambahkan sebelumnya
            db.session.commit()
            current_app.logger.info(f"Successfully committed updates for {len(items_to_commit)} items.")
        except SQLAlchemyError as db_commit_err:
            db.session.rollback()
            current_app.logger.error(f"Database error during final commit of updates: {db_commit_err}", exc_info=True)
        except Exception as final_commit_err:
             db.session.rollback()
             current_app.logger.error(f"Unexpected error during final commit: {final_commit_err}", exc_info=True)
    else:
         current_app.logger.info("No updates needed to be committed to the database.")

    # --- Selesai ---
    current_app.logger.info(
        f"Synchronization finished. "
        f"Users processed: {synced_count}, "
        f"DB Total Updates: {db_update_count}, "
        f"Limit Updates: {limit_update_count}, "
        f"Logs Created: {log_created_count}, "
        f"Logs Updated: {log_updated_count}, "
        f"Failed/Skipped: {failed_sync_count}"
    )