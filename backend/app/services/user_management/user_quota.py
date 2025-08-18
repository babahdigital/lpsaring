# backend/app/services/user_management/user_quota.py
# VERSI OPTIMAL: Disesuaikan dengan arsitektur RouterOsApiPool.

from typing import Tuple
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType
from app.utils.formatters import format_to_local_phone
from app.services import settings_service

# --- [OPTIMALISASI] ---
from .helpers import _log_admin_action, _generate_password
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user

def inject_user_quota(user: User, admin_actor: User, mb_to_add: int, days_to_add: int) -> Tuple[bool, str]:
    """
    [PEROMBAKAN TOTAL] Logika injeksi kuota dan masa aktif yang baru.
    """
    if not admin_actor.is_super_admin_role:
        if user.role != UserRole.KOMANDAN:
            return False, "Admin hanya dapat melakukan injeksi untuk pengguna dengan peran Komandan."
            
    if mb_to_add < 0 or days_to_add < 0:
        return False, "Jumlah MB atau Hari tidak boleh negatif."
    if mb_to_add == 0 and days_to_add == 0:
        return False, "Tidak ada yang ditambahkan."

    now = datetime.now(dt_timezone.utc)
    
    if user.is_unlimited_user:
        if mb_to_add > 0:
            return False, "Tidak dapat menambah kuota (GB) untuk pengguna unlimited. Hanya bisa menambah masa aktif."
        if days_to_add <= 0:
            return False, "Anda hanya bisa menambah masa aktif untuk pengguna unlimited."

        current_expiry = user.quota_expiry_date
        user.quota_expiry_date = (current_expiry if current_expiry and current_expiry > now else now) + timedelta(days=days_to_add)
        
        timeout_seconds = int((user.quota_expiry_date - now).total_seconds()) if user.quota_expiry_date else 0
        limit_bytes_total = 0
        comment = f"Extend unlimited {days_to_add}d by {admin_actor.full_name}"
        action_details = {"added_days_for_unlimited": days_to_add}

    else:
        user.total_quota_purchased_mb = (user.total_quota_purchased_mb or 0) + mb_to_add
        current_expiry = user.quota_expiry_date
        if days_to_add > 0:
            user.quota_expiry_date = (current_expiry if current_expiry and current_expiry > now else now) + timedelta(days=days_to_add)

        remaining_quota_mb = user.total_quota_purchased_mb - (user.total_quota_used_mb or 0)
        limit_bytes_total = int(remaining_quota_mb * 1024 * 1024)
        timeout_seconds = int((user.quota_expiry_date - now).total_seconds()) if user.quota_expiry_date else 0
        comment = f"Inject {mb_to_add}MB/{days_to_add}d by {admin_actor.full_name}"
        action_details = {"added_mb": mb_to_add, "added_days": days_to_add}

    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    # --- [OPTIMALISASI] --- Pemanggilan langsung
    mikrotik_success, mikrotik_msg = activate_or_update_hotspot_user(
        user_mikrotik_username=format_to_local_phone(user.phone_number),
        hotspot_password=user.mikrotik_password,
        mikrotik_profile_name=user.mikrotik_profile_name,
        comment=comment,
        limit_bytes_total=max(0, limit_bytes_total), 
        session_timeout_seconds=max(0, timeout_seconds),
        server=user.mikrotik_server_name,
        force_update_profile=False
    )

    if not mikrotik_success:
        db.session.rollback()
        current_app.logger.error(f"Gagal sinkronisasi injeksi kuota untuk {user.id}: {mikrotik_msg}")
        return False, f"Gagal sinkronisasi dengan Mikrotik: {mikrotik_msg}"
    
    user.mikrotik_user_exists = True

    _log_admin_action(admin_actor, user, AdminActionType.INJECT_QUOTA, {**action_details, "mikrotik_sync_success": mikrotik_success})
    
    return True, f"Berhasil memperbarui kuota/masa aktif untuk {user.full_name}."

def set_user_unlimited(user: User, admin_actor: User, make_unlimited: bool) -> Tuple[bool, str]:
    if user.is_unlimited_user == make_unlimited: 
        return True, f"Pengguna sudah dalam status yang diminta."

    if not user.mikrotik_password: 
        user.mikrotik_password = _generate_password()

    user.is_unlimited_user = make_unlimited
    
    if make_unlimited:
        action_type = AdminActionType.SET_UNLIMITED_STATUS
        user.mikrotik_profile_name = settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited')
        limit_bytes_total = 0 
        session_timeout_seconds = 0
        status_text = "dijadikan"
    else:
        action_type = AdminActionType.REVOKE_UNLIMITED_STATUS
        user.mikrotik_profile_name = 'komandan' if user.role == UserRole.KOMANDAN else 'user'
        limit_bytes_total = 1 
        session_timeout_seconds = 0
        status_text = "dikembalikan dari"

    # --- [OPTIMALISASI] --- Pemanggilan langsung
    mikrotik_success, mikrotik_msg = activate_or_update_hotspot_user(
        user_mikrotik_username=format_to_local_phone(user.phone_number), 
        hotspot_password=user.mikrotik_password,
        mikrotik_profile_name=user.mikrotik_profile_name,
        limit_bytes_total=limit_bytes_total, 
        session_timeout_seconds=session_timeout_seconds,
        server=user.mikrotik_server_name,
        force_update_profile=True, 
        comment=f"Set unlimited to {make_unlimited} by {admin_actor.full_name}"
    )
    
    if not mikrotik_success:
        return False, f"Gagal sinkronisasi Mikrotik: {mikrotik_msg}"

    user.mikrotik_user_exists = True
    if not admin_actor.is_super_admin_role:
        _log_admin_action(admin_actor, user, action_type, {"status": make_unlimited, "profile": user.mikrotik_profile_name})
    
    return True, f"Status unlimited untuk {user.full_name} berhasil {status_text} unlimited."