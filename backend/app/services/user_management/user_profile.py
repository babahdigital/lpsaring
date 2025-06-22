# backend/app/services/user_management/user_profile.py

from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sqlalchemy import select, or_

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType, ApprovalStatus, PromoEvent, PromoEventStatus
from app.utils.formatters import format_to_local_phone, normalize_to_e164
from app.services import settings_service

# Impor service lain dari paket yang sama
from . import user_role as role_service
from . import user_quota as quota_service
from .helpers import (
    _log_admin_action, _generate_password, _send_whatsapp_notification,
    _handle_mikrotik_operation
)
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user, set_hotspot_user_profile

def _get_active_registration_bonus() -> Optional[PromoEvent]:
    """
    Helper function untuk mencari promo bonus registrasi yang aktif.
    """
    now = datetime.now(dt_timezone.utc)
    query = select(PromoEvent).where(
        PromoEvent.status == PromoEventStatus.ACTIVE,
        PromoEvent.event_type == 'BONUS_REGISTRATION',
        PromoEvent.start_date <= now,
        or_(
            PromoEvent.end_date == None,
            PromoEvent.end_date >= now
        )
    ).order_by(PromoEvent.created_at.desc()).limit(1)
    
    return db.session.execute(query).scalar_one_or_none()

def create_user_by_admin(admin_actor: User, data: Dict[str, Any]) -> Tuple[bool, str, Optional[User]]:
    """Membuat pengguna baru dengan validasi peran dan data yang komprehensif."""
    try:
        new_role = UserRole(data['role'])
        if not admin_actor.is_super_admin_role and new_role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return False, "Hanya Super Admin yang dapat membuat pengguna dengan peran Admin atau Super Admin.", None
        
        phone_number = normalize_to_e164(data['phone_number'])
        if not phone_number:
            return False, "Format nomor telepon tidak valid.", None
        
        if db.session.scalar(select(User).filter_by(phone_number=phone_number)):
            return False, f"Nomor telepon {data['phone_number']} sudah terdaftar.", None
        
        if new_role == UserRole.USER and (not data.get('blok') or not data.get('kamar')):
            return False, "Blok dan Kamar wajib diisi untuk peran USER.", None

        new_user = User(
            full_name=data['full_name'],
            phone_number=phone_number,
            role=new_role,
            blok=data.get('blok') if new_role == UserRole.USER else None,
            kamar=f"Kamar_{data['kamar']}" if new_role == UserRole.USER and data.get('kamar') else None,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=datetime.now(dt_timezone.utc),
            approved_by_id=admin_actor.id,
            is_active=True,
            mikrotik_password=_generate_password()
        )

        if new_role == UserRole.SUPER_ADMIN:
            new_user.mikrotik_server_name = 'srv-support'
            new_user.mikrotik_profile_name = 'support'
            new_user.is_unlimited_user = True
            new_user.quota_expiry_date = None
        
        elif new_role == UserRole.ADMIN:
            new_user.mikrotik_server_name = 'srv-komandan'
            new_user.mikrotik_profile_name = 'unlimited'
            new_user.is_unlimited_user = True
            initial_duration_days = int(settings_service.get_setting('ADMIN_INITIAL_DURATION_DAYS', '365'))
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.KOMANDAN:
            new_user.mikrotik_server_name = 'srv-komandan'
            new_user.mikrotik_profile_name = 'komandan'
            new_user.is_unlimited_user = False 
            initial_quota_mb = int(settings_service.get_setting('KOMANDAN_INITIAL_QUOTA_MB', '5120'))
            initial_duration_days = int(settings_service.get_setting('KOMANDAN_INITIAL_DURATION_DAYS', '30'))
            new_user.total_quota_purchased_mb = initial_quota_mb
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.USER:
            new_user.mikrotik_server_name = 'srv-user'
            new_user.mikrotik_profile_name = 'user'
            new_user.is_unlimited_user = False
            
            active_bonus = _get_active_registration_bonus()
            if active_bonus and active_bonus.bonus_value_mb and active_bonus.bonus_duration_days:
                current_app.logger.info(f"Menerapkan bonus registrasi '{active_bonus.name}' untuk user baru {new_user.full_name}")
                new_user.total_quota_purchased_mb = active_bonus.bonus_value_mb
                new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=active_bonus.bonus_duration_days)
            else:
                new_user.total_quota_purchased_mb = 0
                new_user.quota_expiry_date = None
        
        if new_user.is_admin_role:
             portal_password = _generate_password(10)
             new_user.password_hash = generate_password_hash(portal_password)

        db.session.add(new_user)
        _log_admin_action(admin_actor, new_user, AdminActionType.CREATE_USER, {"role": new_role.value})

        db.session.commit()
        db.session.refresh(new_user)
        
        _sync_user_to_mikrotik(new_user, f"Created by {admin_actor.full_name}")
        db.session.commit()

        if new_user.is_admin_role:
            context = { "password": portal_password, "link_admin_app": settings_service.get_setting("LINK_ADMIN_APP", "http://localhost/admin") }
            _send_whatsapp_notification(phone_number, "admin_creation_success", context)
        else:
            context = {"full_name": new_user.full_name, "username": format_to_local_phone(new_user.phone_number), "password": new_user.mikrotik_password}
            _send_whatsapp_notification(phone_number, "user_approve_with_password", context)

        return True, "Pengguna baru berhasil dibuat dan disetujui.", new_user

    except (ValueError, TypeError) as e:
        db.session.rollback()
        current_app.logger.error(f"Error membuat user baru: {e}", exc_info=True)
        return False, f"Data tidak valid: {e}", None
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Kesalahan tak terduga saat membuat user: {e}", exc_info=True)
        return False, "Terjadi kesalahan internal saat memproses permintaan.", None
      
def reset_user_hotspot_password(user_to_reset: User, admin_actor: User) -> Tuple[bool, str]:
    if not user_to_reset.mikrotik_user_exists:
        return False, "Pengguna belum memiliki akun hotspot aktif untuk direset."

    new_mikrotik_password = _generate_password()
    mikrotik_username = format_to_local_phone(user_to_reset.phone_number)
    
    mikrotik_success, mikrotik_message = _handle_mikrotik_operation(
        activate_or_update_hotspot_user, 
        user_mikrotik_username=mikrotik_username,
        hotspot_password=new_mikrotik_password,
        mikrotik_profile_name=user_to_reset.mikrotik_profile_name,
        server=user_to_reset.mikrotik_server_name,
        comment=f"Password reset by {admin_actor.full_name}"
    )

    if not mikrotik_success: 
        return False, f"Password GAGAL direset di Mikrotik. Error: {mikrotik_message}"

    user_to_reset.mikrotik_password = new_mikrotik_password
    _log_admin_action(admin_actor, user_to_reset, AdminActionType.RESET_HOTSPOT_PASSWORD, {"synced": True})
    context = {"full_name": user_to_reset.full_name, "username": mikrotik_username, "password": new_mikrotik_password}
    _send_whatsapp_notification(user_to_reset.phone_number, "user_hotspot_password_reset_by_admin", context)
    return True, "Password hotspot berhasil direset dan notifikasi telah dikirim."

def generate_user_admin_password(user_to_update: User, admin_actor: User) -> Tuple[bool, str]:
    """Menghasilkan password portal baru berupa 6 digit angka."""
    if not user_to_update.is_admin_role:
        return False, "Fungsi ini hanya untuk menghasilkan password portal Admin."
    if user_to_update.id != admin_actor.id and not admin_actor.is_super_admin_role:
        return False, "Akses ditolak. Anda hanya bisa mereset password sendiri."

    new_portal_password = _generate_password(length=6, numeric_only=True)
    
    user_to_update.password_hash = generate_password_hash(new_portal_password)
    _log_admin_action(admin_actor, user_to_update, AdminActionType.GENERATE_ADMIN_PASSWORD, {})
    
    context = {"password": new_portal_password, "link_admin_app_change_password": settings_service.get_setting("LINK_ADMIN_CHANGE_PASSWORD", "http://localhost/akun")}
    _send_whatsapp_notification(user_to_update.phone_number, "admin_password_generated", context)
    
    return True, "Password portal baru berhasil dihasilkan dan dikirim via WhatsApp."

def update_user_by_admin_comprehensive(target_user: User, admin_actor: User, data: Dict[str, Any]) -> Tuple[bool, str, Optional[User]]:
    """Memperbarui profil pengguna dengan mendelegasikan logika kompleks ke service lain."""
    
    if not admin_actor.is_super_admin_role and target_user.is_admin_role:
        return False, "Akses ditolak: Admin tidak dapat mengubah data admin lain.", None
        
    changes = {}

    if 'full_name' in data and data['full_name'] != target_user.full_name:
        target_user.full_name = data['full_name']
        changes['full_name'] = data['full_name']
    
    if target_user.role == UserRole.USER:
        if 'blok' in data and data.get('blok') != target_user.blok: target_user.blok = data.get('blok')
        if 'kamar' in data and data.get('kamar') != target_user.kamar: target_user.kamar = f"Kamar_{data['kamar']}"

    if 'is_active' in data and data['is_active'] != target_user.is_active:
        success, msg = _handle_user_activation(target_user, data['is_active'], admin_actor)
        if not success: return False, msg, None
        changes['is_active'] = data['is_active']

    if not target_user.is_active:
        _log_admin_action(admin_actor, target_user, AdminActionType.UPDATE_USER_PROFILE, changes)
        return True, "Data pengguna berhasil diperbarui, akun dinonaktifkan.", target_user

    if 'role' in data and UserRole(data['role']) != target_user.role:
        new_role = UserRole(data['role'])
        success, msg = role_service.change_user_role(target_user, new_role, admin_actor, data.get('blok'), data.get('kamar'))
        if not success: return False, msg, None
        changes['role'] = new_role.value

    if 'is_unlimited_user' in data and data['is_unlimited_user'] != target_user.is_unlimited_user:
        success, msg = quota_service.set_user_unlimited(target_user, admin_actor, data['is_unlimited_user'])
        if not success: return False, msg, None
        changes['is_unlimited_user'] = data['is_unlimited_user']

    add_gb, add_days = float(data.get('add_gb') or 0.0), int(data.get('add_days') or 0)
    if add_gb > 0 or add_days > 0:
        if target_user.is_unlimited_user: return False, "Tidak dapat menambah kuota pada pengguna unlimited.", None
        success, msg = quota_service.inject_user_quota(target_user, admin_actor, int(add_gb * 1024), add_days)
        if not success: return False, msg, None
        changes['injected_quota'] = {'gb': add_gb, 'days': add_days}

    if admin_actor.is_super_admin_role:
        needs_manual_sync = False
        server_override = data.get('mikrotik_server_name')
        if server_override is not None and server_override != target_user.mikrotik_server_name:
            target_user.mikrotik_server_name = server_override
            changes['mikrotik_server_name'] = server_override
            needs_manual_sync = True
            
        profile_override = data.get('mikrotik_profile_name')
        if profile_override is not None and profile_override != target_user.mikrotik_profile_name:
            target_user.mikrotik_profile_name = profile_override
            changes['mikrotik_profile_name'] = profile_override
            needs_manual_sync = True
        
        if needs_manual_sync:
             success, msg = _sync_user_to_mikrotik(target_user, f"SA Override: {admin_actor.full_name}")
             if not success:
                 return False, f"Gagal override Mikrotik: {msg}", None
             changes['mikrotik_synced'] = True

    if changes:
        _log_admin_action(admin_actor, target_user, AdminActionType.UPDATE_USER_PROFILE, changes)
    
    return True, "Data pengguna berhasil diperbarui.", target_user

def _handle_user_activation(user: User, should_be_active: bool, admin: User) -> Tuple[bool, str]:
    user.is_active = should_be_active
    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    if should_be_active:
        if not user.mikrotik_profile_name or not user.mikrotik_server_name:
            return False, "Profil atau Server Mikrotik belum diatur."
        return _sync_user_to_mikrotik(user, f"Re-activated by {admin.full_name}")
    else:
        current_app.logger.info(f"Deactivating user {user.full_name}. Setting profile to 'inactive' and limit-bytes-total to 1.")
        success, msg = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=format_to_local_phone(user.phone_number),
            hotspot_password=user.mikrotik_password,
            mikrotik_profile_name='inactive',
            limit_bytes_total=1,
            session_timeout='1s',
            comment=f"Deactivated by {admin.full_name}",
            server=user.mikrotik_server_name,
            force_update_profile=True
        )
        if success:
            user.mikrotik_user_exists = True
        return success, msg

def _sync_user_to_mikrotik(user: User, comment: str) -> Tuple[bool, str]:
    limit_bytes, timeout = 0, '0s'
    now = datetime.now(dt_timezone.utc)
    if not user.is_unlimited_user:
        remaining_mb = (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)
        limit_bytes = max(1, int(remaining_mb * 1024 * 1024))
    
    if user.quota_expiry_date and user.quota_expiry_date > now:
        remaining_seconds = int((user.quota_expiry_date - now).total_seconds())
        days, rem = divmod(remaining_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        timeout_parts = []
        if days > 0: timeout_parts.append(f"{days}d")
        if hours > 0: timeout_parts.append(f"{hours}h")
        if mins > 0: timeout_parts.append(f"{mins}m")
        if secs > 0: timeout_parts.append(f"{secs}s")
        timeout = "".join(timeout_parts) if timeout_parts else '1s'
    else:
        timeout = '1s'
        if not user.is_unlimited_user:
            limit_bytes = 1

    success, msg = _handle_mikrotik_operation(
        activate_or_update_hotspot_user, 
        user_mikrotik_username=format_to_local_phone(user.phone_number), 
        hotspot_password=user.mikrotik_password, 
        mikrotik_profile_name=user.mikrotik_profile_name, 
        server=user.mikrotik_server_name, 
        limit_bytes_total=limit_bytes, 
        session_timeout=timeout, 
        force_update_profile=True, 
        comment=comment
    )
    if success: user.mikrotik_user_exists = True
    return success, msg