# backend/app/services/user_management/user_approval.py
# VERSI FINAL: Menggunakan helper terpusat untuk server & profil (termasuk mode testing).

from typing import Tuple
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus, AdminActionType
from app.utils.formatters import format_to_local_phone
from app.services import settings_service

from .helpers import (
    _log_admin_action, _generate_password, _send_whatsapp_notification,
    _get_active_bonus_registration_promo
)
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    move_user_to_inactive_list,
    get_host_details_by_username,
    get_host_details_by_mac,
)
# [PERBAIKAN] Pastikan kedua helper di-import dengan benar
from app.utils.mikrotik_helpers import get_server_for_user, get_profile_for_user

def approve_user_account(user_to_approve: User, admin_actor: User) -> Tuple[bool, str]:
    if user_to_approve.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return False, "Pengguna ini tidak dalam status menunggu persetujuan."
    
    if user_to_approve.role == UserRole.USER and (not user_to_approve.blok or not user_to_approve.kamar):
        return False, "Pengguna USER harus memiliki Blok dan Kamar."

    mikrotik_username = format_to_local_phone(user_to_approve.phone_number)
    if not mikrotik_username:
        return False, "Format nomor telepon tidak valid."

    new_mikrotik_password = _generate_password()
    initial_quota_mb = 0
    initial_duration_days = 30
    log_details = {}
    
    # --- [PERBAIKAN UTAMA] Gunakan helper untuk menentukan server (profil dihitung setelah status diupdate) ---
    mikrotik_server = get_server_for_user(user_to_approve)
    
    # Logika penentuan kuota dan durasi tetap sama, namun bisa disesuaikan untuk testing
    is_test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
    if is_test_mode:
        # Untuk mode testing, periksa apakah user ini termasuk dalam daftar testing
        test_phone_numbers = current_app.config.get('SYNC_TEST_PHONE_NUMBERS', [])
        if isinstance(test_phone_numbers, str):
            test_phone_numbers = [test_phone_numbers]
        
        if user_to_approve.phone_number in test_phone_numbers:
            initial_quota_mb = 100 # Contoh kuota 100MB untuk testing
            initial_duration_days = 1 # Contoh durasi 1 hari untuk testing
            log_details = {"mode": "TESTING", "initial_quota_mb": initial_quota_mb, "initial_days": initial_duration_days}
            current_app.logger.info(f"[TEST MODE] Setting test quotas for {user_to_approve.phone_number}")
    elif user_to_approve.role == UserRole.KOMANDAN:
        initial_quota_mb = settings_service.get_setting_as_int('KOMANDAN_INITIAL_QUOTA_MB', 0)
        initial_duration_days = settings_service.get_setting_as_int('KOMANDAN_INITIAL_DURATION_DAYS', 30)
        log_details = {"role_approved": "KOMANDAN", "initial_quota_mb": initial_quota_mb, "initial_days": initial_duration_days}
    else: # Untuk USER di mode produksi
        active_bonus_promo = _get_active_bonus_registration_promo()
        if active_bonus_promo and active_bonus_promo.bonus_value_mb and active_bonus_promo.bonus_value_mb > 0:
            initial_quota_mb = active_bonus_promo.bonus_value_mb
            if active_bonus_promo.bonus_duration_days is not None and active_bonus_promo.bonus_duration_days > 0:
                initial_duration_days = active_bonus_promo.bonus_duration_days
        else:
            initial_quota_mb = settings_service.get_setting_as_int('USER_INITIAL_QUOTA_MB', 0)
        log_details = {"role_approved": "USER", "bonus_mb": initial_quota_mb, "bonus_days": initial_duration_days}

    # Tulis status awal ke user, tergantung ada bonus/kuota awal atau tidak
    user_gets_initial_quota = initial_quota_mb > 0
    user_to_approve.is_active = user_gets_initial_quota
    user_to_approve.total_quota_purchased_mb = initial_quota_mb
    user_to_approve.total_quota_used_mb = 0
    user_to_approve.quota_expiry_date = (
        datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)
        if user_gets_initial_quota else None
    )
    user_to_approve.is_unlimited_user = False
    user_to_approve.mikrotik_server_name = mikrotik_server

    # Hitung profil SETELAH field kunci di atas diupdate, agar helper membaca status terkini
    mikrotik_profile = get_profile_for_user(user_to_approve)
    user_to_approve.mikrotik_profile_name = mikrotik_profile

    current_app.logger.info(
        f"[APPROVE USER] User active: {user_to_approve.is_active}, Determined server: {mikrotik_server}, profile: {mikrotik_profile}"
    )

    mikrotik_limit_bytes_total = int(initial_quota_mb) * 1024 * 1024 if user_gets_initial_quota else 1

    # Panggil Mikrotik dengan server dan profil yang sudah ditentukan helper
    mikrotik_success, mikrotik_message = activate_or_update_hotspot_user(
        user_mikrotik_username=mikrotik_username,
        mikrotik_profile_name=mikrotik_profile,
        hotspot_password=new_mikrotik_password,
        comment=f"Approved by {admin_actor.full_name}",
        limit_bytes_total=mikrotik_limit_bytes_total,
        server=mikrotik_server,
    )

    if not mikrotik_success:
        return False, f"Gagal aktivasi di Mikrotik: {mikrotik_message}"

    user_to_approve.approval_status = ApprovalStatus.APPROVED
    user_to_approve.approved_at = datetime.now(dt_timezone.utc)
    user_to_approve.approved_by_id = admin_actor.id
    user_to_approve.mikrotik_password = new_mikrotik_password
    user_to_approve.mikrotik_user_exists = True

    # Jika user disetujui tetapi tidak aktif (tanpa kuota awal), pastikan IP masuk ke inactive_client list
    if not user_gets_initial_quota:
        try:
            target_ip = user_to_approve.last_login_ip
            username_comment = mikrotik_username

            # Fallback 1: cari host by username di MikroTik
            if not target_ip:
                ok, host, _ = get_host_details_by_username(mikrotik_username)
                if ok and host and host.get('address'):
                    target_ip = host.get('address')

            # Fallback 2: jika ada MAC terakhir, coba host by MAC
            last_mac = getattr(user_to_approve, 'last_login_mac', None)
            if not target_ip and isinstance(last_mac, str) and last_mac:
                ok, host, _ = get_host_details_by_mac(last_mac)
                if ok and host and host.get('address'):
                    target_ip = host.get('address')

            if target_ip:
                move_user_to_inactive_list(target_ip, username_comment)
            else:
                current_app.logger.warning(
                    f"[APPROVE USER] Tidak ditemukan IP untuk user {mikrotik_username} (belum pernah login/host tidak ada); lewati inactive list untuk sekarang"
                )
        except Exception as e:
            current_app.logger.warning(f"[APPROVE USER] Gagal memindahkan user ke inactive list: {e}")
    
    _log_admin_action(admin_actor, user_to_approve, AdminActionType.APPROVE_USER, log_details)
    
    context = {
        'full_name': user_to_approve.full_name,
        'link_user_app': settings_service.get_setting("APP_LINK_USER", current_app.config.get('APP_LINK_USER'))
    }
    # Kirim notifikasi sesuai status kuota awal
    if user_gets_initial_quota:
        _send_whatsapp_notification(user_to_approve.phone_number, "user_approve_success", context)
        admin_msg = f"Pengguna {user_to_approve.full_name} berhasil disetujui dan diaktifkan."
    else:
        _send_whatsapp_notification(user_to_approve.phone_number, "user_inactive_approved", context)
        admin_msg = (
            f"Pengguna {user_to_approve.full_name} berhasil disetujui (status tidak aktif, perlu beli kuota)."
        )

    return True, admin_msg


def reject_user_account(user_to_reject: User, admin_actor: User) -> Tuple[bool, str]:
    if user_to_reject.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return False, "Pengguna ini tidak dalam status menunggu persetujuan."

    user_name_log, user_phone_log = user_to_reject.full_name, user_to_reject.phone_number
    
    _send_whatsapp_notification(user_phone_log, "user_reject_notification", {"full_name": user_name_log})
    _log_admin_action(admin_actor, user_to_reject, AdminActionType.REJECT_USER, {"reason": "Admin rejection"})
    db.session.delete(user_to_reject)
    
    return True, f"Pendaftaran pengguna {user_name_log} ditolak dan data telah dihapus."