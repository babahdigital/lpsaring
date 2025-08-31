# backend/app/tasks.py
# SI FINAL: Mengimplementasikan notifikasi saat akun diblokir dan diaktifkan kembali.
# pyright: reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false

import logging
from datetime import date, datetime, timedelta, timezone as dt_tz

from flask import current_app
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import celery_app, db
from app.infrastructure.db.models import User, DailyUsageLog, ApprovalStatus, UserDevice
from app.services import settings_service, notification_service
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.infrastructure.gateways import mikrotik_client
from app.utils.formatters import format_to_local_phone, normalize_to_e164
from app.utils.mikrotik_helpers import determine_target_profile, get_server_for_user

logger = logging.getLogger(__name__)

# ---------------- WARM MAC CACHE TASK -----------------
@celery_app.task(name="tasks.warm_mac_cache", bind=True, max_retries=2, default_retry_delay=60)
def warm_mac_cache(self):
    """Prefetch MAC untuk subset IP aktif (UserDevice) untuk mengurangi latensi lookup pertama.

    Strategi:
    - Ambil batch user devices yang recently updated atau active.
    - Lakukan find_mac_by_ip_comprehensive secara paralel (opsional) dengan force_refresh=False agar cache terisi.
    - Hindari saturasi: batasi batch size via config.
    """
    if not current_app.config.get('WARM_MAC_ENABLED', True):
        return
    batch_size = int(current_app.config.get('WARM_MAC_BATCH_SIZE', 50))
    # Ambil IP distinct dari user devices (aktif saja)
    q = db.session.query(UserDevice.ip_address).filter(UserDevice.ip_address.isnot(None)).order_by(UserDevice.updated_at.desc()).limit(batch_size)
    ips = [r[0] for r in q if r[0]]
    if not ips:
        return
    from app.infrastructure.gateways import mikrotik_client as _mc
    start = datetime.now(dt_tz.utc)
    warmed = 0
    for ip in ips:
        try:
            ok, mac, _src = _mc.find_mac_by_ip_comprehensive(ip, force_refresh=False)
            if ok:
                warmed += 1
        except Exception:
            pass
    took_ms = (datetime.now(dt_tz.utc) - start).total_seconds() * 1000
    logger.info(f"[WarmMAC] Prefetched {warmed}/{len(ips)} IPs in {took_ms:.1f}ms")


def init_celery(app, celery):
    """Initialize Celery with Flask app context"""
    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery


@celery_app.task(name="send_whatsapp_invoice_task", bind=True)
def send_whatsapp_invoice_task(self, recipient_number: str, caption: str, pdf_url: str, filename: str):
    logger.info(f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number}")
    try:
        from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf
        send_whatsapp_with_pdf(recipient_number, caption, pdf_url, filename)
    except Exception as e:
        logger.error(f"Celery Task: Exception saat mengirim WhatsApp invoice: {e}", exc_info=True)


@celery_app.task(name="check_low_quota_task", bind=True)
def check_low_quota_task(self):
    now = datetime.now(dt_tz.utc)
    task_logger = current_app.logger 
    task_logger.info("[LowQuotaNotif] Memulai pengecekan kuota rendah...")
    
    thr_percent = int(settings_service.get_setting('LOW_QUOTA_THRESHOLD_PERCENT', 10))
    thr_mb = int(settings_service.get_setting('LOW_QUOTA_THRESHOLD_MB', 200))
    cooldown_h = int(settings_service.get_setting('LOW_QUOTA_NOTIF_COOLDOWN_HOURS', 24))
    
    candidates: list[User] = db.session.query(User).filter(
        User.is_active.is_(True),
        User.is_unlimited_user.is_(False),
        User.total_quota_purchased_mb > 0,
        (User.total_quota_purchased_mb - User.total_quota_used_mb) < db.func.least(User.total_quota_purchased_mb * thr_percent / 100, thr_mb)
    ).all()
    
    task_logger.info(f"[LowQuotaNotif] Menemukan {len(candidates)} kandidat.")
    sent_count = 0
    for user in candidates:
        if user.last_low_quota_notif_at and now - user.last_low_quota_notif_at < timedelta(hours=cooldown_h):
            continue
        
        remaining_mb = max(0, user.total_quota_purchased_mb - (user.total_quota_used_mb or 0))
        message = notification_service.get_notification_message(
            "user_low_quota_alert", 
            {"full_name": user.full_name, "remaining_mb": f"{remaining_mb:,.0f}"}
        )
        
        if send_whatsapp_message(user.phone_number, message):
            user.last_low_quota_notif_at = now
            sent_count += 1
    
    db.session.commit()
    task_logger.info(f"[LowQuotaNotif] Selesai. Sukses mengirim {sent_count} notifikasi.")


@celery_app.task(name='tasks.sync_single_user_status', bind=True, max_retries=3, default_retry_delay=60)
def sync_single_user_status(self, user_id: str):
    task_logger = logging.getLogger('tasks.sync_single_user_status')
    user = db.session.get(User, user_id)

    if not user:
        task_logger.warning(f"User ID {user_id} tidak ditemukan.")
        return

    mikrotik_username = format_to_local_phone(user.phone_number)
    if not mikrotik_username:
        task_logger.warning(f"User {user.full_name} ({user_id}) tidak punya nomor telepon valid.")
        return
        
    try:
        usage_from_host_mb = 0.0
        host_id_to_reset = None
        
        binding_found, binding_details, _ = mikrotik_client.get_ip_binding_details(mikrotik_username)
        if binding_found and binding_details and binding_details.get('mac-address'):
            mac_address = binding_details['mac-address']
            host_found, host_details, _ = mikrotik_client.get_host_details_by_mac(mac_address)
            
            if host_found and host_details:
                host_id_to_reset = host_details.get('.id')
                bytes_in_out_host = int(host_details.get('bytes-in', '0')) + int(host_details.get('bytes-out', '0'))
                
                if bytes_in_out_host > 0:
                    usage_from_host_mb = round(bytes_in_out_host / (1024 * 1024), 2)

        if usage_from_host_mb > 0.1:
            task_logger.info(f"Penggunaan baru terdeteksi untuk '{mikrotik_username}': {usage_from_host_mb:.2f} MB dari Host.")
            last_recorded_usage_mb = float(user.total_quota_used_mb or 0.0)
            new_cumulative_total_mb = last_recorded_usage_mb + usage_from_host_mb
            user.total_quota_used_mb = new_cumulative_total_mb
            
            today = date.today()
            daily_log = db.session.execute(
                select(DailyUsageLog).where(DailyUsageLog.user_id == user.id, DailyUsageLog.log_date == today)
            ).scalar_one_or_none()

            if daily_log:
                daily_log.usage_mb = float(daily_log.usage_mb or 0.0) + usage_from_host_mb
            else:
                daily_log = DailyUsageLog(user_id=user.id, log_date=today, usage_mb=usage_from_host_mb)
                db.session.add(daily_log)
            
            db.session.commit()
            task_logger.info(f"DB & Log Harian untuk '{mikrotik_username}' diperbarui dengan total {new_cumulative_total_mb:.2f} MB.")
            
            db.session.refresh(user)
            
            if host_id_to_reset:
                reset_success, reset_msg = mikrotik_client.reset_host_counters(host_id_to_reset)
                if reset_success:
                    task_logger.info(f"Counter untuk host ID {host_id_to_reset} berhasil direset.")
                else:
                    task_logger.warning(f"Gagal mereset counter host {host_id_to_reset}: {reset_msg}")
        
        task_logger.info(f"Memeriksa pembaruan profil untuk '{mikrotik_username}'...")
        user_found, mt_user, _ = mikrotik_client.get_hotspot_user_details(mikrotik_username)
        if user_found and mt_user:
            current_profile = mt_user.get('profile')
            target_profile = determine_target_profile(user)
            
            task_logger.info(f"  - Profil MikroTik saat ini: '{current_profile}'")
            task_logger.info(f"  - Profil target seharusnya: '{target_profile}'")

            if target_profile and current_profile != target_profile:
                task_logger.info(f"Perbedaan profil terdeteksi untuk '{mikrotik_username}'. Memulai proses perubahan.")
                
                # --- [PENAMBAHAN LOGIKA NOTIFIKASI] ---
                aktif_profile = current_app.config['MIKROTIK_PROFILE_AKTIF']
                fup_profile = current_app.config['MIKROTIK_PROFILE_FUP']
                habis_profile = current_app.config['MIKROTIK_PROFILE_HABIS']
                blokir_profile = current_app.config['MIKROTIK_PROFILE_BLOKIR']

                # Kirim notifikasi berdasarkan transisi status
                if target_profile == fup_profile:
                    task_logger.info(f"Memicu notifikasi FUP untuk '{mikrotik_username}'.")
                    message = notification_service.get_notification_message(
                        "user_fup_activated", 
                        {"full_name": user.full_name, "fup_threshold_percent": current_app.config.get('FUP_THRESHOLD_PERCENT', 85)}
                    )
                    send_whatsapp_message(user.phone_number, message)
                
                elif target_profile == habis_profile:
                    task_logger.info(f"Memicu notifikasi KUOTA HABIS untuk '{mikrotik_username}'.")
                    message = notification_service.get_notification_message("user_quota_finished", {"full_name": user.full_name})
                    send_whatsapp_message(user.phone_number, message)

                elif target_profile == blokir_profile:
                    task_logger.info(f"Memicu notifikasi AKUN DIBLOKIR untuk '{mikrotik_username}'.")
                    admin_phone = settings_service.get_setting('BUSINESS_CONTACT_PHONE', 'Admin')
                    message = notification_service.get_notification_message(
                        "user_account_blocked", 
                        {"full_name": user.full_name, "business_phone": admin_phone}
                    )
                    send_whatsapp_message(user.phone_number, message)

                # [BARU] Kirim notifikasi jika akun diaktifkan kembali dari status blokir
                elif target_profile == aktif_profile and current_profile == blokir_profile:
                    task_logger.info(f"Memicu notifikasi AKUN DIAKTIFKAN KEMBALI untuk '{mikrotik_username}'.")
                    message = notification_service.get_notification_message("user_account_reactivated", {"full_name": user.full_name})
                    send_whatsapp_message(user.phone_number, message)
                # --- [AKHIR PENAMBAHAN LOGIKA NOTIFIKASI] ---

                task_logger.info(f"Mengubah profil '{mikrotik_username}' dari '{current_profile}' ke '{target_profile}'...")
                success, msg = mikrotik_client.set_hotspot_user_profile(mikrotik_username, target_profile)
                if success:
                    task_logger.info(f"Sukses mengubah profil untuk '{mikrotik_username}': {msg}")
                    
                    # CRITICAL: Pastikan IP binding status konsisten dengan profil
                    try:
                        consistency_success, consistency_msg = mikrotik_client.ensure_ip_binding_status_matches_profile(mikrotik_username, target_profile)
                        if consistency_success:
                            task_logger.info(f"IP binding consistency check untuk '{mikrotik_username}': {consistency_msg}")
                        else:
                            task_logger.warning(f"IP binding consistency check GAGAL untuk '{mikrotik_username}': {consistency_msg}")
                    except Exception as e:
                        task_logger.error(f"Error saat consistency check IP binding untuk '{mikrotik_username}': {e}")
                else:
                    task_logger.error(f"Gagal mengubah profil untuk '{mikrotik_username}': {msg}")
            else:
                task_logger.info(f"Profil sudah sesuai. Tidak ada perubahan diperlukan untuk '{mikrotik_username}'.")
        else:
            task_logger.warning(f"User '{mikrotik_username}' tidak ditemukan di MikroTik saat akan sinkronisasi profil.")
        
    except Exception as exc:
        db.session.rollback()
        task_logger.error(f"Error tidak terduga saat sinkronisasi user {user_id}: {exc}", exc_info=True)
        self.retry(exc=exc)


@celery_app.task(name='tasks.dispatch_all_users_sync')
def dispatch_all_users_sync():
    is_test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
    
    if is_test_mode:
        test_phone_numbers_raw = current_app.config.get('SYNC_TEST_PHONE_NUMBERS', [])
        if not test_phone_numbers_raw:
            logger.info("[Dispatcher] Mode tes aktif tetapi SYNC_TEST_PHONE_NUMBERS kosong. Tidak ada tugas dikirim.")
            return
        
        test_phone_numbers_e164 = {normalize_to_e164(num) for num in test_phone_numbers_raw if num}
        
        user_ids_to_sync = db.session.scalars(
            db.select(User.id).where(
                User.phone_number.in_(test_phone_numbers_e164)
            )
        ).all()
        logger.info(f"[Dispatcher] Mode tes aktif. Menargetkan {len(user_ids_to_sync)} pengguna dari daftar tes.")
    else:
        user_ids_to_sync = db.session.scalars(
            db.select(User.id).where(
                User.is_active == True, 
                User.approval_status == ApprovalStatus.APPROVED
            )
        ).all()
        logger.info(f"[Dispatcher] Mode produksi. Mengirim {len(user_ids_to_sync)} tugas sinkronisasi massal.")

    for user_id in user_ids_to_sync:
        sync_single_user_status.delay(user_id=str(user_id))

@celery_app.task(name="tasks.record_daily_usage")
def record_daily_usage_task():
    task_logger = logging.getLogger('tasks.record_daily_usage')
    yesterday = date.today() - timedelta(days=1)
    task_logger.info(f"Memulai rekapitulasi penggunaan harian untuk tanggal: {yesterday}")
    try:
        active_users = db.session.execute(select(User).where(User.is_active == True, User.total_quota_used_mb > 0)).scalars().all()
        previous_usage_stmt = select(
            DailyUsageLog.user_id,
            func.sum(DailyUsageLog.usage_mb).label('total_usage_until_yesterday')
        ).group_by(DailyUsageLog.user_id)
        
        previous_usage_results = db.session.execute(previous_usage_stmt).all()
        previous_usage_map = {str(user_id): total for user_id, total in previous_usage_results}

        logs_to_update = []
        logs_to_add = []
        for user in active_users:
            current_total_usage = float(user.total_quota_used_mb or 0.0)
            usage_until_yesterday = float(previous_usage_map.get(str(user.id), 0.0))
            
            daily_usage = current_total_usage - usage_until_yesterday
            
            if daily_usage > 0.01:
                existing_log = db.session.execute(
                    select(DailyUsageLog).where(
                        DailyUsageLog.user_id == user.id, 
                        DailyUsageLog.log_date == yesterday
                    )
                ).scalar_one_or_none()

                if existing_log:
                    existing_log.usage_mb = daily_usage
                    logs_to_update.append(existing_log)
                else:
                    new_log = DailyUsageLog(
                        user_id=user.id,
                        log_date=yesterday,
                        usage_mb=daily_usage
                    )
                    logs_to_add.append(new_log)

        if logs_to_add:
            db.session.add_all(logs_to_add)
        
        db.session.commit()
        task_logger.info(f"Selesai. {len(logs_to_add)} log baru & {len(logs_to_update)} log diperbarui.")

    except SQLAlchemyError as e:
        db.session.rollback()
        task_logger.error(f"SQLAlchemy Error saat merekam penggunaan harian: {e}", exc_info=True)
    except Exception as e:
        db.session.rollback()
        task_logger.error(f"Error tidak terduga saat merekam penggunaan harian: {e}", exc_info=True)


# ===================== DEVICE MANAGEMENT TASKS =====================

@celery_app.task(name="tasks.sync_bypass_address_list", bind=True, max_retries=3, default_retry_delay=120)
def sync_bypass_address_list(self):
    """
    Task untuk mensinkronisasi address list bypass untuk semua pengguna aktif.
    Memastikan IP pengguna aktif terdaftar di address list bypass.
    
    [Arsitektur 2.0] Pengganti dari sync_device_ip_bindings.
    """
    from flask import current_app
    from app.infrastructure.gateways.mikrotik_client import sync_address_list_for_user
    from app.utils.formatters import format_to_local_phone
    import logging
    
    task_logger = logging.getLogger('tasks.sync_bypass_address_list')
    task_logger.info("Memulai sinkronisasi bypass address list (batched)...")
    
    success_count = error_count = 0
    
    try:
        # Ambil semua user dengan IP login terakhir
        users = db.session.execute(
            select(User).where(User.last_login_ip.isnot(None))
        ).scalars().all()
        
        for user in users:
            try:
                # Hanya proses jika user punya nomor dan IP
                if user.phone_number and user.last_login_ip:
                    mikrotik_username = format_to_local_phone(user.phone_number)
                    if not mikrotik_username:
                        continue
                        
                    # Tentukan profil berdasarkan status user
                    # Jika user tidak aktif atau diblokir, gunakan profil inactive
                    target_profile = user.mikrotik_profile_name or 'user'
                    if not user.is_active or user.is_blocked:
                        target_profile = current_app.config.get('MIKROTIK_PROFILE_INACTIVE', 'inactive')
                    
                    # Sync address list sesuai status
                    success, msg = sync_address_list_for_user(
                        username=mikrotik_username,
                        new_ip_address=user.last_login_ip,
                        target_profile_name=target_profile,
                        old_ip_address=None
                    )
                    
                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                        task_logger.warning(f"Gagal sync address list untuk user {user.id}: {msg}")
            except Exception as e:
                error_count += 1
                task_logger.error(f"Error updating address list for user {user.id}: {e}")
        
        task_logger.info(f"Address list bypass sync selesai. Success: {success_count}, Errors: {error_count}")
        
    except Exception as exc:
        task_logger.error(f"Error dalam sync_bypass_address_list: {exc}", exc_info=True)

# ===================== NEW: DEVICE / ADDRESS LIST AUDIT & CLEANUP =====================

@celery_app.task(name="tasks.audit_address_list_consistency")
def audit_address_list_consistency():
    """Bandingkan address list bypass dengan database user.last_login_ip.
    Mendeteksi: IP di list tanpa user, user aktif tanpa IP di list, duplikasi comment.
    Hasil dicatat di log (bisa dikembangkan simpan ke tabel audit)."""
    task_logger = logging.getLogger('tasks.audit_address_list_consistency')
    list_name = current_app.config['MIKROTIK_BYPASS_ADDRESS_LIST']
    try:
        with mikrotik_client.get_mikrotik_connection() as api:
            if not api:
                task_logger.error("API MikroTik tidak tersedia untuk audit.")
                return
            res = api.get_resource('/ip/firewall/address-list')
            entries = res.get(list=list_name)
            entry_map = {}  # comment -> ip
            duplicates = []
            for e in entries:
                c = e.get('comment')
                a = e.get('address')
                if not c or not a:
                    continue
                if c in entry_map and entry_map[c] != a:
                    duplicates.append((c, entry_map[c], a))
                entry_map.setdefault(c, a)

            # Ambil semua user aktif yang punya last_login_ip
            users = db.session.execute(
                select(User).where(User.is_active == True, User.last_login_ip.isnot(None))
            ).scalars().all()
            missing = []
            mismatch = []
            for user in users:
                if not user.phone_number or not user.last_login_ip:
                    continue
                comment = format_to_local_phone(user.phone_number)
                if not comment:
                    continue
                ip_in_list = entry_map.get(comment)
                if not ip_in_list:
                    missing.append((user.id, comment, user.last_login_ip))
                elif ip_in_list != user.last_login_ip:
                    mismatch.append((user.id, comment, ip_in_list, user.last_login_ip))

            task_logger.info(f"[AUDIT] Total entries: {len(entries)}; duplicates: {len(duplicates)}; missing: {len(missing)}; mismatch: {len(mismatch)}")
            if duplicates:
                task_logger.warning(f"[AUDIT] Duplicates: {duplicates[:20]}")
            if missing:
                task_logger.warning(f"[AUDIT] Missing: {missing[:20]}")
            if mismatch:
                task_logger.warning(f"[AUDIT] Mismatch: {mismatch[:20]}")
    except Exception as e:
        task_logger.error(f"Audit error: {e}")


@celery_app.task(name="tasks.cleanup_stale_static_leases")
def cleanup_stale_static_leases(days: int = 7):
    """Hapus static DHCP leases yang tidak tercatat di DB atau last_seen > X hari."""
    task_logger = logging.getLogger('tasks.cleanup_stale_static_leases')
    cutoff = datetime.now(dt_tz.utc) - timedelta(days=days)
    try:
        with mikrotik_client.get_mikrotik_connection() as api:
            if not api:
                task_logger.error("API MikroTik tidak tersedia untuk lease cleanup.")
                return
            leases_res = api.get_resource('/ip/dhcp-server/lease')
            leases = leases_res.get()
            mac_set = { (u.trusted_mac_address or '').upper() for u in db.session.execute(select(User)).scalars().all() if u.trusted_mac_address }
            removed = 0
            for lease in leases:
                mac = (lease.get('mac-address') or '').upper()
                dynamic = lease.get('dynamic') == 'true'
                last_seen_raw = lease.get('last-seen')  # format RouterOS, bisa diabaikan jika parsing rumit
                if dynamic:
                    continue  # hanya static
                if mac and mac not in mac_set:
                    # lease bukan milik user aktif
                    lid = lease.get('.id') or lease.get('id')
                    try:
                        if lid:
                            leases_res.remove(id=lid)
                            removed += 1
                    except Exception:
                        pass
            task_logger.info(f"[LEASE-CLEANUP] Removed {removed} stale static leases (not in DB).")
    except Exception as e:
        task_logger.error(f"Lease cleanup error: {e}")


@celery_app.task(name="tasks.repair_stale_address_list_entries")
def repair_stale_address_list_entries(limit: int = 50):
    """Perbaiki entri address list yang mismatch dibanding DB (ambil dari audit kering)."""
    task_logger = logging.getLogger('tasks.repair_stale_address_list_entries')
    list_name = current_app.config['MIKROTIK_BYPASS_ADDRESS_LIST']
    try:
        with mikrotik_client.get_mikrotik_connection() as api:
            if not api:
                task_logger.error("API MikroTik tidak tersedia untuk perbaikan.")
                return
            res = api.get_resource('/ip/firewall/address-list')
            entries = res.get(list=list_name)
            entry_map = { e.get('comment'): e for e in entries if e.get('comment') }
            users = db.session.execute(select(User).where(User.is_active == True, User.last_login_ip.isnot(None))).scalars().all()
            fixed = 0
            from app.utils.formatters import format_to_local_phone
            for u in users:
                if fixed >= limit:
                    break
                comment = format_to_local_phone(u.phone_number)
                if not comment:
                    continue
                target_ip = u.last_login_ip
                entry = entry_map.get(comment)
                if entry and entry.get('address') != target_ip:
                    # update ip dengan hapus dan tambah kembali
                    eid = entry.get('.id') or entry.get('id')
                    try:
                        if eid:
                            res.remove(id=eid)
                        res.add(address=target_ip, list=list_name, comment=comment)
                        fixed += 1
                    except Exception as _e:
                        task_logger.warning(f"[REPAIR] Gagal update {comment}: {_e}")
            task_logger.info(f"[REPAIR] Fixed {fixed} mismatched entries.")
    except Exception as e:
        task_logger.error(f"Repair error: {e}")

# Fungsi lama tetap ada untuk backward compatibility
@celery_app.task(name="tasks.sync_device_ip_bindings", bind=True, max_retries=3, default_retry_delay=120)
def sync_device_ip_bindings(self):
    """
    Task untuk mensinkronisasi IP binding untuk semua perangkat yang aktif.
    Memastikan IP binding di MikroTik sesuai dengan status user dan device.
    
    [DEPRECATED] Akan digantikan oleh sync_bypass_address_list di Arsitektur 2.0
    """
    task_logger = logging.getLogger('tasks.sync_device_ip_bindings')
    task_logger.info("Memulai sinkronisasi IP binding untuk semua perangkat aktif...")
    
    try:
        # Ambil semua user yang aktif dan punya last_login_ip/mac
        active_users_with_devices = db.session.execute(
            select(User).where(
                User.is_active == True,
                User.last_login_ip.isnot(None),
                User.last_login_mac.isnot(None)
            )
        ).scalars().all()
        
        binding_updated = 0
        binding_errors = 0
        
        for user in active_users_with_devices:
            try:
                mikrotik_username = format_to_local_phone(user.phone_number)
                if not mikrotik_username:
                    continue
                
                # Tentukan binding type berdasarkan user status
                if user.is_blocked:
                    binding_type = 'blocked'
                elif not user.is_unlimited_user and user.total_quota_purchased_mb > 0:
                    # Check if quota finished
                    purchased = float(user.total_quota_purchased_mb or 0)
                    used = float(user.total_quota_used_mb or 0)
                    if used >= purchased:
                        binding_type = 'quota-finished'
                    else:
                        binding_type = 'bypassed'
                else:
                    binding_type = 'bypassed'
                
                # Update IP binding
                success, msg = mikrotik_client.create_or_update_ip_binding(
                    mac_address=user.last_login_mac,
                    ip_address=user.last_login_ip,
                    comment=f"Auto sync: {mikrotik_username}",
                    server=user.mikrotik_server_name,
                    type=binding_type
                )
                
                if success:
                    binding_updated += 1
                    task_logger.debug(f"IP binding updated for {mikrotik_username}: {binding_type}")
                else:
                    binding_errors += 1
                    task_logger.warning(f"Failed to update IP binding for {mikrotik_username}: {msg}")
                    
            except Exception as e:
                binding_errors += 1
                task_logger.error(f"Error updating IP binding for user {user.id}: {e}")
        
        task_logger.info(f"IP binding sync selesai. Updated: {binding_updated}, Errors: {binding_errors}")
        
    except Exception as exc:
        task_logger.error(f"Error dalam sync_device_ip_bindings: {exc}", exc_info=True)
        self.retry(exc=exc)


@celery_app.task(name="tasks.cleanup_stale_devices", bind=True)
def cleanup_stale_devices(self):
    """
    Task untuk membersihkan device yang sudah lama tidak aktif.
    Menghapus UserDevice yang last_seen_at > 30 hari.
    """
    task_logger = logging.getLogger('tasks.cleanup_stale_devices')
    task_logger.info("Memulai pembersihan perangkat yang tidak aktif...")
    
    try:
        # Device dianggap stale jika tidak seen selama 30 hari
        stale_threshold = datetime.now(dt_tz.utc) - timedelta(days=30)
        
        stale_devices = db.session.execute(
            select(UserDevice).where(
                UserDevice.last_seen_at < stale_threshold
            )
        ).scalars().all()
        
        if not stale_devices:
            task_logger.info("Tidak ada perangkat stale yang perlu dibersihkan.")
            return
        
        device_count = len(stale_devices)
        
        # Hapus stale devices
        for device in stale_devices:
            task_logger.info(f"Menghapus device stale: {device.device_name} (MAC: {device.mac_address}, Last seen: {device.last_seen_at})")
            db.session.delete(device)
        
        db.session.commit()
        task_logger.info(f"Berhasil menghapus {device_count} perangkat yang tidak aktif.")
        
    except Exception as e:
        db.session.rollback()
        task_logger.error(f"Error dalam cleanup_stale_devices: {e}", exc_info=True)


@celery_app.task(name="tasks.validate_device_consistency", bind=True)
def validate_device_consistency(self):
    """
    Task untuk memvalidasi konsistensi antara database devices dan MikroTik IP bindings.
    Mendeteksi dan memperbaiki inkonsistensi.
    """
    task_logger = logging.getLogger('tasks.validate_device_consistency')
    task_logger.info("Memulai validasi konsistensi perangkat...")
    
    try:
        # Ambil semua user dengan trusted_mac_address tapi tidak ada di UserDevice
        users_with_orphaned_mac = db.session.execute(
            select(User).where(
                User.trusted_mac_address.isnot(None),
                ~User.devices.any(UserDevice.mac_address == User.trusted_mac_address)
            )
        ).scalars().all()
        
        orphaned_fixed = 0
        
        for user in users_with_orphaned_mac:
            # Buat UserDevice untuk trusted_mac_address yang orphaned
            if len(user.devices) < 5:  # Respect device limit
                new_device = UserDevice(
                    user_id=user.id,
                    mac_address=user.trusted_mac_address,
                    device_name="Auto-recovered Device",
                    last_seen_at=datetime.now(dt_tz.utc)
                )
                db.session.add(new_device)
                orphaned_fixed += 1
                task_logger.info(f"Auto-recovered orphaned MAC for user {user.phone_number}: {user.trusted_mac_address}")
        
        # Commit perubahan
        if orphaned_fixed > 0:
            db.session.commit()
            task_logger.info(f"Berhasil memperbaiki {orphaned_fixed} MAC address yang orphaned.")
        else:
            task_logger.info("Tidak ada inkonsistensi perangkat yang perlu diperbaiki.")
            
    except Exception as e:
        db.session.rollback()
        task_logger.error(f"Error dalam validate_device_consistency: {e}", exc_info=True)