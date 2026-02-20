# backend/app/services/user_management/user_role.py

from typing import Tuple, Optional
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app

from app.infrastructure.db.models import User, UserRole, AdminActionType, UserQuotaDebt
from app.utils.formatters import format_to_local_phone
from app.extensions import db
from app.services import settings_service
from .helpers import (
    _log_admin_action, _generate_password, _send_whatsapp_notification,
    _handle_mikrotik_operation
)
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user


def _resolve_default_server() -> str:
    return (
        settings_service.get_setting('MIKROTIK_DEFAULT_SERVER', None)
        or settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'srv-user')
    )


def _resolve_komandan_server() -> str:
    return settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'srv-komandan')


def _resolve_komandan_profile() -> str:
    return settings_service.get_setting('MIKROTIK_KOMANDAN_PROFILE', 'komandan')


def _resolve_active_profile() -> str:
    return (
        settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', None)
        or settings_service.get_setting('MIKROTIK_USER_PROFILE', 'user')
        or settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
    )


def _resolve_unlimited_profile() -> str:
    return settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited')

def change_user_role(user: User, new_role: UserRole, admin: User, blok: Optional[str] = None, kamar: Optional[str] = None) -> Tuple[bool, str]:
    """Mengubah peran pengguna dengan validasi hak akses dan sinkronisasi Mikrotik yang lebih baik."""
    old_role = user.role
    if old_role == new_role: 
        return False, "Tidak ada perubahan peran."
    
    # [PERBAIKAN] Menggunakan variabel 'admin' yang benar, bukan 'admin_actor'
    if not admin.is_super_admin_role:
        if new_role == UserRole.ADMIN:
            return False, "Hanya Super Admin yang dapat mengangkat Admin."
        if old_role == UserRole.USER and new_role != UserRole.USER:
            return False, "Admin tidak dapat mengubah peran dari USER. Hubungi Super Admin."
        if old_role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            return False, "Admin tidak dapat menurunkan peran dari ADMIN lain."

    action_type = None
    mikrotik_username = format_to_local_phone(user.phone_number)
    default_server = _resolve_default_server()
    active_profile = _resolve_active_profile()
    unlimited_profile = _resolve_unlimited_profile()
    
    original_role_profile = user.mikrotik_profile_name
    original_role_server = user.mikrotik_server_name

    # Logika untuk upgrade ke Admin
    if new_role == UserRole.ADMIN and old_role != UserRole.ADMIN:
        action_type = AdminActionType.UPGRADE_TO_ADMIN
        if user.blok or user.kamar:
            user.previous_blok, user.previous_kamar = user.blok, user.kamar
            user.blok, user.kamar = None, None
        
        user.role = new_role
        user.is_unlimited_user = True
        user.quota_expiry_date = None
        user.mikrotik_server_name = default_server
        user.mikrotik_profile_name = unlimited_profile
        
        new_portal_password = _generate_password()
        user.password_hash = generate_password_hash(new_portal_password)
        _send_whatsapp_notification(user.phone_number, "user_upgrade_to_admin_with_password", {"password": new_portal_password})
        
        user.mikrotik_password = new_portal_password

    # Logika untuk downgrade dari Admin
    elif old_role == UserRole.ADMIN and new_role != UserRole.ADMIN:
        action_type = AdminActionType.DOWNGRADE_FROM_ADMIN
        user.password_hash = None
        user.role = new_role
        user.is_unlimited_user = False
        
        user.blok = user.previous_blok or (blok if blok else None)
        user.kamar = user.previous_kamar or (kamar if kamar else None)
        
        if new_role == UserRole.USER and (not user.blok or not user.kamar):
             return False, "Blok dan Kamar wajib diisi saat downgrade ke peran USER."

        user.mikrotik_server_name = default_server
        user.mikrotik_profile_name = active_profile
        
        try:
            initial_quota_mb_str = settings_service.get_setting('USER_INITIAL_QUOTA_MB', '1024')
            user.total_quota_purchased_mb = int(initial_quota_mb_str)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Nilai USER_INITIAL_QUOTA_MB tidak valid ('{initial_quota_mb_str}'). Menggunakan default 1024.")
            user.total_quota_purchased_mb = 1024

        user.total_quota_used_mb = 0
        user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=30)
        user.mikrotik_password = _generate_password()

    # Logika perubahan antara User dan Komandan
    elif (old_role, new_role) in [(UserRole.USER, UserRole.KOMANDAN), (UserRole.KOMANDAN, UserRole.USER)]:
        user.role = new_role
        if new_role == UserRole.KOMANDAN:
            action_type = AdminActionType.CHANGE_USER_ROLE
            if user.blok or user.kamar:
                user.previous_blok, user.previous_kamar = user.blok, user.kamar
                user.blok, user.kamar = None, None
            user.mikrotik_server_name = _resolve_komandan_server()
            user.mikrotik_profile_name = _resolve_komandan_profile() or active_profile

            # Debt tidak berlaku untuk KOMANDAN: bersihkan debt manual + ledger.
            try:
                user.manual_debt_mb = 0
                user.manual_debt_updated_at = datetime.now(dt_timezone.utc)
                db.session.execute(
                    db.delete(UserQuotaDebt).where(UserQuotaDebt.user_id == user.id)
                )
            except Exception:
                pass

            try:
                initial_quota_mb_str = settings_service.get_setting('KOMANDAN_INITIAL_QUOTA_MB', '5120')
                initial_quota_mb = int(initial_quota_mb_str)
            except (ValueError, TypeError):
                current_app.logger.warning(f"Nilai KOMANDAN_INITIAL_QUOTA_MB tidak valid ('{initial_quota_mb_str}'). Menggunakan default 5120.")
                initial_quota_mb = 5120
                
            try:
                duration_days_str = settings_service.get_setting('KOMANDAN_INITIAL_DURATION_DAYS', '30')
                initial_duration_days = int(duration_days_str)
            except (ValueError, TypeError):
                current_app.logger.warning(f"Nilai KOMANDAN_INITIAL_DURATION_DAYS tidak valid ('{duration_days_str}'). Menggunakan default 30.")
                initial_duration_days = 30
            
            user.total_quota_purchased_mb = (user.total_quota_purchased_mb or 0) + initial_quota_mb
            
            now = datetime.now(dt_timezone.utc)
            current_expiry = user.quota_expiry_date
            user.quota_expiry_date = (current_expiry if current_expiry and current_expiry > now else now) + timedelta(days=initial_duration_days)

            _send_whatsapp_notification(user.phone_number, "user_upgrade_to_komandan", {"full_name": user.full_name})
        else: # KOMANDAN -> USER
            action_type = AdminActionType.CHANGE_USER_ROLE
            if not blok or not kamar:
                return False, "Blok dan Kamar wajib diisi saat mengubah peran menjadi USER."
            user.blok, user.kamar = blok, kamar
            user.mikrotik_server_name = default_server
            user.mikrotik_profile_name = active_profile
            # Pastikan debt manual tetap nol saat turun dari KOMANDAN.
            try:
                user.manual_debt_mb = int(user.manual_debt_mb or 0)
            except Exception:
                user.manual_debt_mb = 0
            _send_whatsapp_notification(user.phone_number, "user_downgrade_from_komandan", {"full_name": user.full_name})
    else:
        return False, f"Perubahan peran dari {old_role.value} ke {new_role.value} tidak didukung."

    # SINKRONISASI MIKROTIK
    if mikrotik_username:
        limit_bytes = 0
        if not user.is_unlimited_user and user.total_quota_purchased_mb is not None:
            remaining_mb = (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)
            limit_bytes = max(0, int(remaining_mb * 1024 * 1024))
            if limit_bytes <= 0:
                limit_bytes = 1

        timeout_seconds = 0
        if user.quota_expiry_date and user.quota_expiry_date > datetime.now(dt_timezone.utc):
             if not user.is_unlimited_user or user.role == UserRole.KOMANDAN:
                timeout_seconds = max(0, int((user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()))

        mikrotik_op_success, mikrotik_op_message = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=mikrotik_username,
            mikrotik_profile_name=user.mikrotik_profile_name,
            hotspot_password=user.mikrotik_password or _generate_password(),
            server=user.mikrotik_server_name,
            force_update_profile=True,
            limit_bytes_total=limit_bytes,
            session_timeout_seconds=timeout_seconds,
            comment=f"Role changed from {old_role.value} to {new_role.value} by {admin.full_name}"
        )
        if not mikrotik_op_success:
            user.role = old_role
            user.mikrotik_profile_name = original_role_profile
            user.mikrotik_server_name = original_role_server
            return False, f"Gagal sinkronisasi Mikrotik saat perubahan peran: {mikrotik_op_message}"
        
        user.mikrotik_user_exists = True

    # [PERBAIKAN] Menggunakan variabel 'admin' yang benar, bukan 'admin_actor'
    # Logika ini juga diubah agar mencatat semua perubahan peran, tidak hanya oleh non-super-admin.
    _log_admin_action(admin, user, action_type, {"from": old_role.value, "to": new_role.value})
    
    return True, f"Peran pengguna {user.full_name} berhasil diubah menjadi {new_role.value}."