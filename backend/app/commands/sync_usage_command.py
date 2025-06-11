# backend/app/commands/sync_usage_command.py
# Versi 2.9: Modifikasi untuk mencatat penggunaan harian ke DailyUsageLog
# MODIFIKASI: Disesuaikan untuk fungsi "force sync" kuota ke MikroTik untuk debugging.

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
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.exc import SQLAlchemyError
from datetime import date

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
# Untuk tujuan force sync ini, threshold ini mungkin diabaikan atau disesuaikan.
USAGE_UPDATE_THRESHOLD_MB = 0.1

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    """
    Synchronize user quota usage from MikroTik to the application database
    and log daily usage increments.
    MODIFIKASI SEMENTARA: Juga mencoba force sync limit-bytes-total dari DB ke MikroTik.
    """
    current_app.logger.info("Starting user quota usage synchronization and daily logging...")
    current_app.logger.info("MODE: SEMENTARA - Attempting to force sync total_quota_purchased_mb to MikroTik limits.")


    # Ambil semua user yang relevan dari DB
    try:
        # Ambil user yang aktif DAN memiliki total_quota_purchased_mb > 0
        stmt = select(User).filter(
            User.is_active == True,
            User.total_quota_purchased_mb > 0 # Hanya sinkronkan yang punya kuota
        )
        users_to_sync = db.session.scalars(stmt).all()
    except SQLAlchemyError as e:
         current_app.logger.error(f"Synchronization aborted: DB error fetching users to sync: {e}", exc_info=True)
         return
    except Exception as e:
         current_app.logger.error(f"Synchronization aborted: Unexpected error fetching users: {e}", exc_info=True)
         return

    if not users_to_sync:
        current_app.logger.info("No active users with purchased quota found requiring synchronization.")
        return

    current_app.logger.info(f"Found {len(users_to_sync)} active users with purchased quota to potentially sync.")

    # Inisialisasi counter
    synced_count = 0
    failed_sync_count = 0
    db_update_count = 0
    limit_update_count = 0
    log_created_count = 0
    log_updated_count = 0
    users_to_commit = []
    logs_to_commit = [] # List untuk menyimpan log yang akan di-commit

    mikrotik_api_connection = None
    try:
        with get_mikrotik_connection() as api:
            if not api:
                current_app.logger.error("Synchronization aborted: Failed to get MikroTik API connection from pool.")
                return
            mikrotik_api_connection = api
            identity = mikrotik_api_connection.get_resource('/system/identity').get()
            current_app.logger.info(f"Successfully connected to MikroTik '{identity[0].get('name', 'N/A')}' for sync job.")
    except Exception as conn_err:
        current_app.logger.error(f"Synchronization aborted: Failed to get/verify API connection from pool: {conn_err}", exc_info=True)
        return

    if mikrotik_api_connection is None:
        current_app.logger.error("Synchronization aborted: MikroTik API connection not established.")
        return

    today = date.today()

    for user in users_to_sync:
        username_08 = format_to_local_phone(user.phone_number)

        if not username_08:
            current_app.logger.warning(f"Skipping user ID {user.id}: Could not format phone number '{user.phone_number}' to 08 format.")
            failed_sync_count += 1
            continue

        try:
            # 1. Ambil data usage dari MikroTik (tetap relevan untuk logging DailyUsageLog)
            success_usage, usage_data, error_msg_usage = get_hotspot_user_usage(mikrotik_api_connection, username_08)

            current_usage_mb = 0.0
            if success_usage and usage_data is not None:
                bytes_in = usage_data.get('bytes-in', 0)
                bytes_out = usage_data.get('bytes-out', 0)
                current_usage_bytes = bytes_in + bytes_out
                current_usage_mb = round(current_usage_bytes / (1024 * 1024), 2)
            elif not success_usage:
                current_app.logger.warning(f"Failed to get usage for user '{username_08}': {error_msg_usage}")
            else:
                current_app.logger.info(f"User '{username_08}' not found in MikroTik during usage retrieval. Setting usage to 0.")

            # --- BARU: Log Penggunaan Harian (delta berdasarkan usage dari Mikrotik) ---
            old_usage_mb_in_db = user.total_quota_used_mb or 0
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
                        if daily_log not in logs_to_commit:
                            logs_to_commit.append(daily_log)
                        log_updated_count += 1
                        current_app.logger.debug(f"Updating daily log for user {user.id} on {today}: added {delta_usage_mb:.2f} MB")
                    else:
                        new_log = DailyUsageLog(
                            user_id=user.id,
                            log_date=today,
                            usage_mb=delta_usage_mb
                        )
                        db.session.add(new_log)
                        if new_log not in logs_to_commit:
                             logs_to_commit.append(new_log)
                        log_created_count += 1
                        current_app.logger.debug(f"Creating new daily log for user {user.id} on {today}: {delta_usage_mb:.2f} MB")

                except SQLAlchemyError as log_db_err:
                    current_app.logger.error(f"DB error while finding/creating daily log for user {user.id} on {today}: {log_db_err}", exc_info=True)
                except Exception as log_err:
                     current_app.logger.error(f"Unexpected error during daily logging for user {user.id} on {today}: {log_err}", exc_info=True)
            # --- AKHIR BARU ---

            # 2. Update total_quota_used_mb di DB jika ada perubahan signifikan
            if abs(old_usage_mb_in_db - current_usage_mb) > USAGE_UPDATE_THRESHOLD_MB:
                current_app.logger.info(f"Updating total usage for user '{username_08}' (DB ID: {user.id}): DB {old_usage_mb_in_db:.2f}MB -> MikroTik {current_usage_mb:.2f}MB")
                user.total_quota_used_mb = current_usage_mb
                if user not in users_to_commit:
                    users_to_commit.append(user)
                db_update_count += 1
            else:
                current_app.logger.debug(f"User '{username_08}' (DB ID: {user.id}): Usage within threshold. No DB update needed.")


            # --- MODIFIKASI PENTING: Force sync limit-bytes-total ---
            # Ambil total_quota_purchased_mb langsung dari DB user
            # Ini adalah kuota yang "seharusnya" dimiliki user berdasarkan pembelian/bonus.
            purchased_mb = user.total_quota_purchased_mb or 0
            limit_bytes_total_to_send = int(purchased_mb * 1024 * 1024)

            # Pastikan nilai tidak negatif
            if limit_bytes_total_to_send < 0:
                limit_bytes_total_to_send = 0
                current_app.logger.warning(f"Negative purchased quota for user {user.id} ({user.full_name}), reset to 0 for Mikrotik limit.")

            # Selalu coba set limit di MikroTik jika user punya kuota terdaftar > 0
            if purchased_mb > 0:
                current_app.logger.info(f"FORCE SYNC: Setting MikroTik limit for '{username_08}' to {purchased_mb:.2f}MB ({limit_bytes_total_to_send} bytes).")
                limit_success, limit_msg = set_hotspot_user_limit(mikrotik_api_connection, username_08, limit_bytes_total_to_send)
                if limit_success:
                    limit_update_count += 1
                else:
                    current_app.logger.error(f"FAILED FORCE SYNC: Failed to set MikroTik limit for '{username_08}': {limit_msg}")
            else:
                current_app.logger.info(f"Skipping MikroTik limit force sync for '{username_08}' as purchased quota is 0.")
            # --- AKHIR MODIFIKASI PENTING ---

            synced_count += 1

        except Exception as inner_e:
            current_app.logger.error(f"Error processing user '{username_08}' (DB ID: {user.id}) during sync: {inner_e}", exc_info=True)
            failed_sync_count += 1

    # --- Commit Perubahan ke Database ---
    items_to_commit = users_to_commit + logs_to_commit
    if items_to_commit:
        current_app.logger.info(f"Attempting to commit updates for {len(users_to_commit)} users and {len(logs_to_commit)} logs...")
        try:
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
        f"DB Total Usage Updates: {db_update_count}, "
        f"MikroTik Limit Set Operations: {limit_update_count}, "
        f"Daily Logs Created: {log_created_count}, "
        f"Daily Logs Updated: {log_updated_count}, "
        f"Failed/Skipped Users: {failed_sync_count}"
    )