# backend/app/services/user_management/user_approval.py
# PERBAIKAN: Mengimpor dari .helpers bukan .common

from typing import Tuple
from datetime import datetime, timezone as dt_timezone, timedelta

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus, AdminActionType
from app.utils.formatters import format_to_local_phone
from app.services import settings_service

# --- [PERBAIKAN PENTING DI SINI] ---
# Mengubah impor dari .common yang tidak ada, menjadi .helpers yang sudah kita buat.
from .helpers import (
    _log_admin_action,
    _generate_password,
    _send_whatsapp_notification,
    _handle_mikrotik_operation,
    _get_active_bonus_registration_promo,
)
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user


def approve_user_account(user_to_approve: User, admin_actor: User) -> Tuple[bool, str]:
    """
    Logika inti untuk menyetujui pengguna baru.
    """
    if user_to_approve.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return False, "Pengguna ini tidak dalam status menunggu persetujuan."

    if user_to_approve.role == UserRole.USER:
        if user_to_approve.is_tamping:
            if not user_to_approve.tamping_type:
                return False, "Pengguna tamping harus memilih jenis tamping."
        else:
            if not user_to_approve.blok or not user_to_approve.kamar:
                return False, "Pengguna USER harus memiliki Blok dan Kamar."

    mikrotik_username = format_to_local_phone(user_to_approve.phone_number)
    if not mikrotik_username:
        return False, "Format nomor telepon tidak valid."

    new_mikrotik_password = _generate_password()
    initial_quota_mb = 0
    initial_duration_days = 30
    mikrotik_profile = ""
    mikrotik_server = user_to_approve.mikrotik_server_name
    log_details = {}
    inactive_profile = settings_service.get_setting("MIKROTIK_INACTIVE_PROFILE", None) or settings_service.get_setting(
        "MIKROTIK_DEFAULT_PROFILE", "default"
    )

    if user_to_approve.role == UserRole.KOMANDAN:
        initial_quota_mb = settings_service.get_setting_as_int("KOMANDAN_INITIAL_QUOTA_MB", 0)
        initial_duration_days = settings_service.get_setting_as_int("KOMANDAN_INITIAL_DURATION_DAYS", 30)
        mikrotik_profile = settings_service.get_setting("MIKROTIK_KOMANDAN_PROFILE", "komandan")
        if not mikrotik_server:
            mikrotik_server = "srv-komandan"
        log_details = {
            "role_approved": "KOMANDAN",
            "initial_quota_mb": initial_quota_mb,
            "initial_days": initial_duration_days,
        }

    else:  # Untuk USER
        active_bonus_promo = _get_active_bonus_registration_promo()
        if active_bonus_promo and active_bonus_promo.bonus_value_mb and active_bonus_promo.bonus_value_mb > 0:
            initial_quota_mb = active_bonus_promo.bonus_value_mb
            if active_bonus_promo.bonus_duration_days is not None and active_bonus_promo.bonus_duration_days > 0:
                initial_duration_days = active_bonus_promo.bonus_duration_days
        else:
            initial_quota_mb = settings_service.get_setting_as_int("USER_INITIAL_QUOTA_MB", 0)

        mikrotik_profile = settings_service.get_setting("MIKROTIK_USER_PROFILE", "user")
        if not mikrotik_server:
            mikrotik_server = "srv-user"
        log_details = {"role_approved": "USER", "bonus_mb": initial_quota_mb, "bonus_days": initial_duration_days}

    if initial_quota_mb <= 0:
        mikrotik_profile = inactive_profile

    user_to_approve.total_quota_purchased_mb = initial_quota_mb
    user_to_approve.quota_expiry_date = (
        datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days) if initial_quota_mb > 0 else None
    )
    user_to_approve.mikrotik_profile_name = mikrotik_profile

    mikrotik_limit_bytes_total = int(initial_quota_mb) * 1024 * 1024 if initial_quota_mb > 0 else 1

    mikrotik_success, mikrotik_message = _handle_mikrotik_operation(
        activate_or_update_hotspot_user,
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
    user_to_approve.is_active = True
    user_to_approve.approved_at = datetime.now(dt_timezone.utc)
    user_to_approve.approved_by_id = admin_actor.id
    user_to_approve.mikrotik_password = new_mikrotik_password
    user_to_approve.mikrotik_user_exists = True
    user_to_approve.is_unlimited_user = False
    user_to_approve.total_quota_used_mb = 0

    _log_admin_action(admin_actor, user_to_approve, AdminActionType.APPROVE_USER, log_details)

    context = {
        "full_name": user_to_approve.full_name,
        "hotspot_username": mikrotik_username,
        "hotspot_password": new_mikrotik_password,
    }
    _send_whatsapp_notification(user_to_approve.phone_number, "user_approve_success", context)

    return True, f"Pengguna {user_to_approve.full_name} berhasil disetujui."


def reject_user_account(user_to_reject: User, admin_actor: User) -> Tuple[bool, str]:
    """Menolak pendaftaran, lalu menghapus data dari DB dan mengirim notifikasi."""
    if user_to_reject.approval_status != ApprovalStatus.PENDING_APPROVAL:
        return False, "Pengguna ini tidak dalam status menunggu persetujuan."

    user_name_log, user_phone_log = user_to_reject.full_name, user_to_reject.phone_number

    _send_whatsapp_notification(user_phone_log, "user_reject_notification", {"full_name": user_name_log})
    _log_admin_action(admin_actor, user_to_reject, AdminActionType.REJECT_USER, {"reason": "Admin rejection"})
    db.session.delete(user_to_reject)

    return True, f"Pendaftaran pengguna {user_name_log} ditolak dan data telah dihapus."
