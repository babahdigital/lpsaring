# backend/app/services/user_management/user_profile.py
# VERSI FINAL: Memperbaiki logika pengembalian pesan agar lebih informatif saat blokir/aktivasi.

from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sqlalchemy import select, or_

from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, AdminActionType, ApprovalStatus, PromoEvent, 
    PromoEventStatus, UserBlok, UserKamar
)
from app.utils.formatters import format_to_local_phone, normalize_to_e164
from app.services import settings_service

from . import user_role as role_service
from . import user_quota as quota_service
from .helpers import _log_admin_action, _generate_password, _send_whatsapp_notification
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user

def _get_active_registration_bonus() -> Optional[PromoEvent]:
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

        blok_enum = None
        kamar_enum = None
        if new_role == UserRole.USER:
            try:
                blok_enum = UserBlok(data.get('blok'))
                kamar_value_str = f"Kamar_{data.get('kamar')}"
                kamar_enum = UserKamar(kamar_value_str)
            except ValueError:
                return False, f"Nilai untuk Blok atau Kamar tidak valid. Pastikan sesuai dengan pilihan yang ada.", None

        new_user = User()
        new_user.full_name = data['full_name']
        new_user.phone_number = phone_number
        new_user.role = new_role
        new_user.blok = blok_enum
        new_user.kamar = kamar_enum
        new_user.approval_status = ApprovalStatus.APPROVED
        new_user.approved_at = datetime.now(dt_timezone.utc)
        new_user.approved_by_id = admin_actor.id
        
        # Check if is_active is provided in request and set accordingly
        is_active = data.get('is_active', True)
        new_user.is_active = is_active
        
        # If user is inactive, also set blocked flag
        if not is_active:
            new_user.is_blocked = True
        
        new_user.mikrotik_password = _generate_password()

        # Import helper functions for server and profile determination
        from app.utils.mikrotik_helpers import get_server_for_user, get_profile_for_user
        
        # Check if profile is explicitly set in the request
        custom_profile = data.get('profile')
        is_inactive = not new_user.is_active
        
        # Intentionally NOT using get_server_for_user here as we'll defer the final
        # server determination to _sync_user_to_mikrotik which uses get_server_for_user
        # This ensures test mode is always properly enforced at sync time

        if is_inactive:
            # If user is inactive, set to inactive profile regardless of role
            new_user.mikrotik_profile_name = 'inactive'
            new_user.is_unlimited_user = False
            initial_duration_days = int(settings_service.get_setting('USER_INITIAL_DURATION_DAYS', '30') or '30')
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)
        elif custom_profile:
            # If profile is explicitly provided, use it
            new_user.mikrotik_profile_name = custom_profile
            new_user.is_unlimited_user = custom_profile in ['unlimited', 'support']
            initial_duration_days = int(settings_service.get_setting('USER_INITIAL_DURATION_DAYS', '30') or '30')
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)
        elif new_role == UserRole.SUPER_ADMIN:
            new_user.mikrotik_profile_name = 'support'
            new_user.is_unlimited_user = True
            new_user.quota_expiry_date = None
        
        elif new_role == UserRole.ADMIN:
            new_user.mikrotik_profile_name = 'unlimited'
            new_user.is_unlimited_user = True
            initial_duration_days = int(settings_service.get_setting('ADMIN_INITIAL_DURATION_DAYS', '365') or '365')
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.KOMANDAN:
            new_user.mikrotik_profile_name = 'komandan'
            new_user.is_unlimited_user = False 
            initial_quota_mb = int(settings_service.get_setting('KOMANDAN_INITIAL_QUOTA_MB', '5120') or '5120')
            initial_duration_days = int(settings_service.get_setting('KOMANDAN_INITIAL_DURATION_DAYS', '30') or '30')
            new_user.total_quota_purchased_mb = initial_quota_mb
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.USER:
            new_user.mikrotik_profile_name = 'profile-aktif'  # Updated to use profile-aktif
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
        
        db.session.flush() 
        
        sync_success, sync_message = _sync_user_to_mikrotik(new_user, f"Created by {admin_actor.full_name}")
        if not sync_success:
            return False, f"Gagal sinkronisasi ke Mikrotik: {sync_message}", None

        if new_user.is_admin_role:
            context = { 
                "password": portal_password, 
                "link_admin_app": settings_service.get_setting("APP_LINK_ADMIN", current_app.config.get('APP_LINK_ADMIN')),
                "link_admin_app_change_password": settings_service.get_setting("APP_LINK_ADMIN_CHANGE_PASSWORD", current_app.config.get('APP_LINK_ADMIN_CHANGE_PASSWORD')),
                "full_name": new_user.full_name
            }
            _send_whatsapp_notification(phone_number, "admin_creation_success", context)
        else:
            context = {
                "full_name": new_user.full_name,
                "link_user_app": settings_service.get_setting("APP_LINK_USER", current_app.config.get('APP_LINK_USER'))
            }
            
            # Jika user dibuat dalam keadaan tidak aktif
            if not new_user.is_active:
                _send_whatsapp_notification(phone_number, "user_inactive_approved", context)
            else:
                _send_whatsapp_notification(phone_number, "user_approve_success", context)

        return True, "Pengguna baru berhasil dibuat dan disetujui.", new_user

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Error data validasi saat membuat user baru: {e}", exc_info=True)
        return False, f"Data tidak valid: {e}", None
    except Exception as e:
        current_app.logger.error(f"Kesalahan tak terduga saat membuat user: {e}", exc_info=True)
        return False, "Terjadi kesalahan internal saat memproses permintaan.", None

def reset_user_hotspot_password(user_to_reset: User, admin_actor: User) -> Tuple[bool, str]:
    if not user_to_reset.mikrotik_user_exists:
        return False, "Pengguna belum memiliki akun hotspot aktif untuk direset."

    target_server = user_to_reset.mikrotik_server_name
    if not target_server:
        current_app.logger.error(f"Upaya reset password untuk user {user_to_reset.id} gagal: `mikrotik_server_name` tidak diatur di database.")
        return False, "Reset password gagal: Data server Mikrotik untuk pengguna ini tidak ditemukan. Hubungi Super Admin."

    new_mikrotik_password = _generate_password()
    mikrotik_username = format_to_local_phone(user_to_reset.phone_number)
    
    mikrotik_success, mikrotik_message = activate_or_update_hotspot_user( 
        user_mikrotik_username=format_to_local_phone(user_to_reset.phone_number) or "",
        hotspot_password=new_mikrotik_password,
        mikrotik_profile_name=user_to_reset.mikrotik_profile_name or "user",
        server=target_server,
        comment=f"Password reset by {admin_actor.full_name}"
    )

    if not mikrotik_success: 
        return False, f"Password GAGAL direset di Mikrotik. Error: {mikrotik_message}"

    user_to_reset.mikrotik_password = new_mikrotik_password
    _log_admin_action(admin_actor, user_to_reset, AdminActionType.RESET_HOTSPOT_PASSWORD, {"synced": True})
    
    context = {
        "full_name": user_to_reset.full_name, 
        "hotspot_username": mikrotik_username, 
        "hotspot_password": new_mikrotik_password
    }
    _send_whatsapp_notification(user_to_reset.phone_number, "user_hotspot_password_reset_by_admin", context)
    return True, "Password hotspot berhasil direset dan notifikasi telah dikirim."

def generate_user_admin_password(user_to_update: User, admin_actor: User) -> Tuple[bool, str]:
    if not user_to_update.is_admin_role:
        return False, "Fungsi ini hanya untuk menghasilkan password portal Admin."
    if user_to_update.id != admin_actor.id and not admin_actor.is_super_admin_role:
        return False, "Akses ditolak. Anda hanya bisa mereset password sendiri."

    new_portal_password = _generate_password(length=6, numeric_only=True)
    
    user_to_update.password_hash = generate_password_hash(new_portal_password)
    _log_admin_action(admin_actor, user_to_update, AdminActionType.GENERATE_ADMIN_PASSWORD, {})
    
    context = {
        "password": new_portal_password, 
        "link_admin_app_change_password": settings_service.get_setting("APP_LINK_ADMIN_CHANGE_PASSWORD", current_app.config.get('APP_LINK_ADMIN_CHANGE_PASSWORD')),
        "link_user_app": settings_service.get_setting("APP_LINK_USER", current_app.config.get('APP_LINK_USER'))
    }
    _send_whatsapp_notification(user_to_update.phone_number, "admin_password_generated", context)
    
    return True, "Password portal baru berhasil dihasilkan dan dikirim via WhatsApp."

def update_user_by_admin_comprehensive(target_user: User, admin_actor: User, data: Dict[str, Any]) -> Tuple[bool, str, Optional[User]]:
    if not admin_actor.is_super_admin_role and target_user.is_admin_role:
        return False, "Akses ditolak: Admin tidak dapat mengubah data admin lain.", None
        
    changes = {}
    # --- [PERBAIKAN] Variabel baru untuk menampung pesan spesifik ---
    activation_message = None

    if 'full_name' in data and data['full_name'] != target_user.full_name:
        target_user.full_name = data['full_name']
        changes['full_name'] = data['full_name']
    
    if target_user.role == UserRole.USER:
        if 'blok' in data and data.get('blok') != target_user.blok: 
            target_user.blok = UserBlok(data.get('blok')) if data.get('blok') else None
        if 'kamar' in data and data.get('kamar') != target_user.kamar: 
            kamar_value = f"Kamar_{data['kamar']}"
            target_user.kamar = UserKamar(kamar_value) if kamar_value else None

    # --- [PERBAIKAN] Logika penanganan status aktif diubah ---
    if 'is_active' in data and data['is_active'] != target_user.is_active:
        success, msg = _handle_user_activation(target_user, data['is_active'], admin_actor)
        if not success: return False, msg, None
        changes['is_active'] = data['is_active']
        # --- Pesan spesifik dari helper disimpan ---
        activation_message = msg

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
    
    # --- [PERBAIKAN] Pesan akhir dipilih secara cerdas ---
    final_message = activation_message if activation_message else "Data pengguna berhasil diperbarui."
    return True, final_message, target_user

def _handle_user_activation(user: User, should_be_active: bool, admin: User) -> Tuple[bool, str]:
    user.is_active = should_be_active
    
    if should_be_active:
        user.is_blocked = False
        current_app.logger.info(f"Activating user {user.full_name}. Unblocking and triggering sync.")
        success, msg = _sync_user_to_mikrotik(user, f"Re-activated by {admin.full_name}")
        
        # Update IP binding to enabled for reactivated user
        if user.last_login_ip and user.last_login_mac:
            from app.infrastructure.gateways.mikrotik_client import create_or_update_ip_binding
            mikrotik_username = format_to_local_phone(user.phone_number)
            
            try:
                # Determine binding type based on user status
                binding_type = 'bypassed'  # Default for active users
                comment = f"Admin reactivate: {mikrotik_username}"
                
                create_or_update_ip_binding(
                    mac_address=user.last_login_mac,
                    ip_address=user.last_login_ip,
                    comment=comment,
                    server=user.mikrotik_server_name,
                    type=binding_type
                )
                current_app.logger.info(f"[ADMIN-REACTIVATE] IP binding enabled for {mikrotik_username} (IP: {user.last_login_ip}, MAC: {user.last_login_mac})")
            except Exception as e:
                current_app.logger.warning(f"Failed to update IP binding for reactivated user {mikrotik_username}: {e}")
        
        if success:
            _log_admin_action(admin, user, AdminActionType.ACTIVATE_USER, {})
            try:
                context = {"full_name": user.full_name}
                _send_whatsapp_notification(user.phone_number, "user_account_reactivated", context)
                current_app.logger.info(f"Notifikasi re-aktivasi berhasil dikirim ke {user.full_name}.")
            except Exception as e:
                current_app.logger.error(f"Gagal mengirim notifikasi re-aktivasi ke {user.full_name}: {e}", exc_info=True)
        return success, msg
    else:
        user.is_blocked = True
        current_app.logger.info(f"Deactivating user {user.full_name}. Setting is_active=False and is_blocked=True.")
        
        # Disable IP binding for blocked user to force re-login
        if user.last_login_ip and user.last_login_mac:
            from app.infrastructure.gateways.mikrotik_client import create_or_update_ip_binding
            mikrotik_username = format_to_local_phone(user.phone_number)
            
            try:
                # For blocked users, create disabled binding to force re-login
                binding_type = 'blocked'
                comment = f"Admin block: {mikrotik_username}"
                
                create_or_update_ip_binding(
                    mac_address=user.last_login_mac,
                    ip_address=user.last_login_ip,
                    comment=comment,
                    server=user.mikrotik_server_name,
                    type=binding_type
                )
                current_app.logger.info(f"[ADMIN-BLOCK] IP binding disabled for {mikrotik_username} (IP: {user.last_login_ip}, MAC: {user.last_login_mac})")
            except Exception as e:
                current_app.logger.warning(f"Failed to disable IP binding for blocked user {mikrotik_username}: {e}")
        
        try:
            context = {
                "full_name": user.full_name,
                "business_phone": settings_service.get_setting('BUSINESS_PHONE_NUMBER_FORMATTED', 'Admin')
            }
            _send_whatsapp_notification(user.phone_number, "user_account_blocked", context)
            current_app.logger.info(f"Notifikasi pemblokiran berhasil dikirim ke {user.full_name}.")
        except Exception as e:
            current_app.logger.error(f"Gagal mengirim notifikasi pemblokiran ke {user.full_name}: {e}", exc_info=True)
        
        _log_admin_action(admin, user, AdminActionType.DEACTIVATE_USER, {})
        return True, f"User {user.full_name} telah dinonaktifkan dan dijadwalkan untuk sinkronisasi blokir."
        
def _sync_user_to_mikrotik(user: User, comment: str) -> Tuple[bool, str]:
    limit_bytes, timeout_seconds = 0, 0
    now = datetime.now(dt_timezone.utc)
    
    if not user.is_unlimited_user:
        remaining_mb = (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)
        limit_bytes = max(1, int(remaining_mb * 1024 * 1024))
    
    if user.quota_expiry_date and user.quota_expiry_date > now:
        timeout_seconds = max(1, int((user.quota_expiry_date - now).total_seconds()))
    else:
        timeout_seconds = 1
        if not user.is_unlimited_user:
            limit_bytes = 1
    
    # PERBAIKAN: Gunakan helper function untuk mendapatkan server yang tepat di mode testing
    from app.utils.mikrotik_helpers import get_server_for_user
    server_name = get_server_for_user(user)
    
    # Jika server berubah dari yang tersimpan, update dan log perubahan
    if server_name != user.mikrotik_server_name:
        current_app.logger.info(f"[TEST MODE] Overriding server for {user.full_name}: {user.mikrotik_server_name} -> {server_name}")
        user.mikrotik_server_name = server_name
    
    # Debug info
    current_app.logger.debug(f"[SYNC] User: {user.full_name}, Phone: {user.phone_number}")
    current_app.logger.debug(f"[SYNC] Server: {server_name}, Profile: {user.mikrotik_profile_name}")
    current_app.logger.debug(f"[SYNC] Test mode: {current_app.config.get('SYNC_TEST_MODE_ENABLED', False)}")
    current_app.logger.debug(f"[SYNC] Test numbers: {current_app.config.get('SYNC_TEST_PHONE_NUMBERS', [])}")

    success, msg = activate_or_update_hotspot_user(
        user_mikrotik_username=format_to_local_phone(user.phone_number) or "", 
        hotspot_password=user.mikrotik_password or _generate_password(), 
        mikrotik_profile_name=user.mikrotik_profile_name or "user", 
        server=server_name,  # Gunakan server_name dari helper function 
        limit_bytes_total=limit_bytes, 
        session_timeout_seconds=timeout_seconds,
        force_update_profile=True, 
        comment=comment
    )
    if success: user.mikrotik_user_exists = True
    return success, msg