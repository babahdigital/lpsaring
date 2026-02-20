# backend/app/services/user_management/user_profile.py

from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone as dt_timezone, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sqlalchemy import select, or_

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType, ApprovalStatus, PromoEvent, PromoEventStatus
from app.utils.formatters import (
    format_to_local_phone,
    get_app_date_time_strings,
    get_phone_number_variations,
    normalize_to_e164,
    normalize_to_local,
)
from app.services import settings_service
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.utils.quota_debt import compute_debt_mb

# Impor service lain dari paket yang sama
from . import user_role as role_service
from . import user_quota as quota_service
from . import user_debt as debt_service
from .helpers import (
    _log_admin_action, _generate_password, _send_whatsapp_notification,
    _handle_mikrotik_operation
)
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    delete_hotspot_user,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    remove_address_list_entry,
    sync_address_list_for_user,
    upsert_address_list_entry,
    upsert_ip_binding,
)
from app.services.hotspot_sync_service import sync_address_list_for_single_user


def _resolve_default_server() -> str:
    return (
        settings_service.get_setting('MIKROTIK_DEFAULT_SERVER', None)
        or settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'srv-user')
        or 'srv-user'
    )


def _resolve_active_profile() -> str:
    return (
        settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', None)
        or settings_service.get_setting('MIKROTIK_USER_PROFILE', 'user')
        or settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        or 'user'
    )


def _resolve_unlimited_profile() -> str:
    return settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited') or 'unlimited'

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
            PromoEvent.end_date.is_(None),
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
        
        variations = get_phone_number_variations(phone_number)
        if db.session.scalar(select(User.id).where(User.phone_number.in_(variations))):
            return False, f"Nomor telepon {data['phone_number']} sudah terdaftar.", None
        
        is_tamping = bool(data.get('is_tamping'))
        tamping_type = data.get('tamping_type')
        if new_role == UserRole.USER:
            if is_tamping:
                if not tamping_type:
                    return False, "Jenis tamping wajib diisi untuk peran USER tamping.", None
            else:
                if not data.get('blok') or not data.get('kamar'):
                    return False, "Blok dan Kamar wajib diisi untuk peran USER.", None

        # Instantiate without kwargs to keep type-checkers happy with SQLAlchemy's dynamic init.
        new_user = User()
        new_user.full_name = data['full_name']
        new_user.phone_number = phone_number
        new_user.role = new_role
        new_user.blok = data.get('blok') if new_role == UserRole.USER and not is_tamping else None
        new_user.kamar = f"Kamar_{data['kamar']}" if new_role == UserRole.USER and data.get('kamar') and not is_tamping else None
        new_user.is_tamping = is_tamping if new_role == UserRole.USER else False
        new_user.tamping_type = tamping_type if new_role == UserRole.USER and is_tamping else None
        new_user.approval_status = ApprovalStatus.APPROVED
        new_user.approved_at = datetime.now(dt_timezone.utc)
        new_user.approved_by_id = admin_actor.id
        new_user.is_active = True
        new_user.mikrotik_password = _generate_password()

        add_gb = float(data.get('add_gb') or 0.0)
        add_days = int(data.get('add_days') or 0)

        default_server = _resolve_default_server()
        active_profile = _resolve_active_profile()
        unlimited_profile = _resolve_unlimited_profile()
        inactive_profile = (
            settings_service.get_setting('MIKROTIK_INACTIVE_PROFILE', None)
            or settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        )

        if new_role == UserRole.SUPER_ADMIN:
            new_user.mikrotik_server_name = default_server
            new_user.mikrotik_profile_name = unlimited_profile
            new_user.is_unlimited_user = True
            new_user.quota_expiry_date = None
        
        elif new_role == UserRole.ADMIN:
            new_user.mikrotik_server_name = default_server
            new_user.mikrotik_profile_name = unlimited_profile
            new_user.is_unlimited_user = True
            initial_duration_days = settings_service.get_setting_as_int('ADMIN_INITIAL_DURATION_DAYS', 365)
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.KOMANDAN:
            new_user.mikrotik_server_name = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'srv-komandan')
            new_user.mikrotik_profile_name = active_profile
            new_user.is_unlimited_user = False 
            initial_quota_mb = settings_service.get_setting_as_int('KOMANDAN_INITIAL_QUOTA_MB', 5120)
            initial_duration_days = settings_service.get_setting_as_int('KOMANDAN_INITIAL_DURATION_DAYS', 30)
            new_user.total_quota_purchased_mb = initial_quota_mb
            new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=initial_duration_days)

        elif new_role == UserRole.USER:
            new_user.mikrotik_server_name = default_server
            new_user.mikrotik_profile_name = active_profile
            new_user.is_unlimited_user = False
            
            active_bonus = _get_active_registration_bonus()
            if active_bonus and active_bonus.bonus_value_mb and active_bonus.bonus_duration_days:
                current_app.logger.info(f"Menerapkan bonus registrasi '{active_bonus.name}' untuk user baru {new_user.full_name}")
                new_user.total_quota_purchased_mb = active_bonus.bonus_value_mb
                new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=active_bonus.bonus_duration_days)
            else:
                new_user.total_quota_purchased_mb = 0
                new_user.quota_expiry_date = None

        if new_role in [UserRole.USER, UserRole.KOMANDAN] and (add_gb > 0 or add_days > 0):
            new_user.total_quota_purchased_mb = int(add_gb * 1024)
            if add_days > 0:
                new_user.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=add_days)
            elif new_user.quota_expiry_date is None:
                new_user.quota_expiry_date = None

        if new_role == UserRole.USER and (new_user.total_quota_purchased_mb or 0) <= 0:
            new_user.mikrotik_profile_name = inactive_profile
        
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
            default_admin_link = (
                current_app.config.get("APP_LINK_ADMIN")
                or current_app.config.get("APP_PUBLIC_BASE_URL")
                or current_app.config.get("FRONTEND_URL")
                or ""
            )
            context = {
                "phone_number": format_to_local_phone(new_user.phone_number),
                "password": portal_password,
                "link_admin_app": settings_service.get_setting("LINK_ADMIN_APP", default_admin_link),
            }
            _send_whatsapp_notification(phone_number, "admin_creation_success", context)
        else:
            # === [PERBAIKAN DI SINI] ===
            # Mengubah kunci 'username' -> 'hotspot_username' dan 'password' -> 'hotspot_password'
            # agar sesuai dengan template notifikasi.
            context = {
                "full_name": new_user.full_name,
                "hotspot_username": format_to_local_phone(new_user.phone_number) or "",
                "hotspot_password": new_user.mikrotik_password,
            }
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
    # [PERBAIKAN KONSISTENSI] Menyamakan kunci placeholder di sini juga
    context = {
        "full_name": user_to_reset.full_name, 
        "hotspot_username": mikrotik_username, 
        "hotspot_password": new_mikrotik_password
    }
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
    
    default_change_password_link = (
        current_app.config.get("APP_LINK_ADMIN_CHANGE_PASSWORD")
        or ""
    )
    context = {
        "password": new_portal_password,
        "link_admin_app_change_password": settings_service.get_setting("LINK_ADMIN_CHANGE_PASSWORD", default_change_password_link),
    }
    _send_whatsapp_notification(user_to_update.phone_number, "admin_password_generated", context)
    
    return True, "Password portal baru berhasil dihasilkan dan dikirim via WhatsApp."

def update_user_by_admin_comprehensive(target_user: User, admin_actor: User, data: Dict[str, Any]) -> Tuple[bool, str, Optional[User]]:
    """Memperbarui profil pengguna dengan mendelegasikan logika kompleks ke service lain."""
    
    if not admin_actor.is_super_admin_role and target_user.is_admin_role:
        return False, "Akses ditolak: Admin tidak dapat mengubah data admin lain.", None
        
    changes = {}

    # --- Update phone_number (ADMIN/SUPER_ADMIN) ---
    # Catatan: username hotspot berbasis nomor, jadi kita harus sync MikroTik agar user tetap bisa login.
    raw_phone = None
    if isinstance(data, dict):
        raw_phone = data.get('phone_number') or data.get('phone')

    if raw_phone:
        if not admin_actor.is_super_admin_role and target_user.is_admin_role:
            return False, "Akses ditolak: Admin tidak dapat mengubah nomor telepon admin lain.", None

        try:
            new_phone_local = normalize_to_local(str(raw_phone))
        except Exception as e:
            return False, f"Nomor telepon tidak valid: {e}", None

        old_username_08 = format_to_local_phone(target_user.phone_number) or ""
        new_username_08 = format_to_local_phone(new_phone_local) or ""

        # Jika secara efektif sama (mis. +62 vs 08), anggap tidak berubah.
        if new_username_08 and old_username_08 and new_username_08 != old_username_08:
            variations = get_phone_number_variations(new_phone_local)
            existing_user = db.session.execute(
                select(User).where(User.phone_number.in_(variations), User.id != target_user.id)
            ).scalar_one_or_none()
            if existing_user:
                return False, "Nomor telepon sudah digunakan.", None

            target_user.phone_number = new_phone_local
            changes['phone_number'] = new_phone_local

            # Best-effort: sync MikroTik ke username baru lalu hapus username lama
            if not target_user.mikrotik_password:
                target_user.mikrotik_password = _generate_password()
            if not target_user.mikrotik_profile_name:
                target_user.mikrotik_profile_name = _resolve_active_profile()

            if target_user.is_active and target_user.approval_status == ApprovalStatus.APPROVED:
                ok_mt, msg_mt = _sync_user_to_mikrotik(
                    target_user,
                    f"Phone updated by {admin_actor.full_name} old={old_username_08}",
                )
                if not ok_mt:
                    return False, f"Gagal sinkronisasi MikroTik setelah ganti nomor: {msg_mt}", None

                if old_username_08 and new_username_08 and old_username_08 != new_username_08:
                    _handle_mikrotik_operation(delete_hotspot_user, username=old_username_08)

                try:
                    sync_address_list_for_single_user(target_user)
                except Exception:
                    pass

    if 'full_name' in data and data['full_name'] != target_user.full_name:
        target_user.full_name = data['full_name']
        changes['full_name'] = data['full_name']
    
    if target_user.role == UserRole.USER:
        if 'is_tamping' in data and data.get('is_tamping') != target_user.is_tamping:
            target_user.is_tamping = bool(data.get('is_tamping'))
            changes['is_tamping'] = target_user.is_tamping

        if target_user.is_tamping:
            if 'tamping_type' in data and data.get('tamping_type') != target_user.tamping_type:
                target_user.tamping_type = data.get('tamping_type')
                changes['tamping_type'] = target_user.tamping_type
            if target_user.blok is not None:
                target_user.blok = None
                changes['blok'] = None
            if target_user.kamar is not None:
                target_user.kamar = None
                changes['kamar'] = None
        else:
            if 'blok' in data and data.get('blok') != target_user.blok:
                target_user.blok = data.get('blok')
            if 'kamar' in data and data.get('kamar') != target_user.kamar:
                target_user.kamar = f"Kamar_{data['kamar']}"
            if target_user.tamping_type is not None:
                target_user.tamping_type = None
                changes['tamping_type'] = None

    if 'is_active' in data and data['is_active'] != target_user.is_active:
        success, msg = _handle_user_activation(target_user, data['is_active'], admin_actor)
        if not success:
            return False, msg, None
        changes['is_active'] = data['is_active']

    # Note: unblock guard depends on up-to-date quota/unlimited state.
    # If request includes add_gb/add_days or is_unlimited_user change, apply those first,
    # then perform unblock so the debt calculation uses the new values.
    pending_unblock = False
    pending_unblock_reason = data.get('blocked_reason') or None

    if 'is_blocked' in data and data['is_blocked'] != target_user.is_blocked:
        should_block = bool(data['is_blocked'])
        if should_block:
            success, msg = _handle_user_blocking(target_user, True, admin_actor, pending_unblock_reason)
            if not success:
                return False, msg, None
            changes['is_blocked'] = True
            changes['blocked_reason'] = pending_unblock_reason
            _log_admin_action(admin_actor, target_user, AdminActionType.BLOCK_USER, changes)
            return True, "Akun pengguna diblokir.", target_user
        pending_unblock = True

    if not target_user.is_active:
        _log_admin_action(admin_actor, target_user, AdminActionType.UPDATE_USER_PROFILE, changes)
        return True, "Data pengguna berhasil diperbarui, akun dinonaktifkan.", target_user

    if 'role' in data and UserRole(data['role']) != target_user.role:
        new_role = UserRole(data['role'])
        success, msg = role_service.change_user_role(target_user, new_role, admin_actor, data.get('blok'), data.get('kamar'))
        if not success:
            return False, msg, None
        changes['role'] = new_role.value

    if 'is_unlimited_user' in data and data['is_unlimited_user'] != target_user.is_unlimited_user:
        success, msg = quota_service.set_user_unlimited(target_user, admin_actor, data['is_unlimited_user'])
        if not success:
            return False, msg, None
        changes['is_unlimited_user'] = data['is_unlimited_user']

    # Manual debt input / clear (admin-only)
    debt_add_mb = 0
    try:
        debt_add_mb = int(data.get('debt_add_mb') or 0)
    except (TypeError, ValueError):
        debt_add_mb = 0

    if debt_add_mb and debt_add_mb > 0:
        ok_debt, msg_debt, _entry = debt_service.add_manual_debt(
            user=target_user,
            admin_actor=admin_actor,
            amount_mb=debt_add_mb,
            debt_date=data.get('debt_date'),
            note=data.get('debt_note'),
        )
        if not ok_debt:
            return False, msg_debt, None
        changes['debt_add_mb'] = debt_add_mb
        if data.get('debt_date'):
            changes['debt_date'] = data.get('debt_date')

    if data.get('debt_clear') is True:
        paid_auto_mb, paid_manual_mb = debt_service.clear_all_debts_to_zero(
            user=target_user,
            admin_actor=admin_actor,
            source='admin_clear',
        )
        changes['debt_cleared'] = {
            'paid_auto_debt_mb': int(paid_auto_mb),
            'paid_manual_debt_mb': int(paid_manual_mb),
        }
        try:
            sync_address_list_for_single_user(target_user)
        except Exception:
            pass

        # Optional WhatsApp: inform user debt is cleared.
        try:
            purchased_now = float(target_user.total_quota_purchased_mb or 0.0)
            used_now = float(target_user.total_quota_used_mb or 0.0)
            remaining_mb = max(0.0, purchased_now - used_now)
            _send_whatsapp_notification(
                target_user.phone_number,
                'user_debt_cleared',
                {
                    'full_name': target_user.full_name,
                    'paid_auto_debt_mb': int(paid_auto_mb),
                    'paid_manual_debt_mb': int(paid_manual_mb),
                    'paid_total_debt_mb': int(paid_auto_mb) + int(paid_manual_mb),
                    'remaining_mb': float(remaining_mb),
                },
            )
        except Exception:
            pass

    add_gb, add_days = float(data.get('add_gb') or 0.0), int(data.get('add_days') or 0)
    if add_gb > 0 or add_days > 0:
        success, msg = quota_service.inject_user_quota(target_user, admin_actor, int(add_gb * 1024), add_days)
        if not success:
            return False, msg, None
        changes['injected_quota'] = {'gb': add_gb, 'days': add_days}

    if pending_unblock:
        success, msg = _handle_user_blocking(target_user, False, admin_actor, pending_unblock_reason)
        if not success:
            return False, msg, None
        changes['is_blocked'] = False
        changes['blocked_reason'] = pending_unblock_reason

    if changes:
        _log_admin_action(admin_actor, target_user, AdminActionType.UPDATE_USER_PROFILE, changes)
    
    return True, "Data pengguna berhasil diperbarui.", target_user

def _handle_user_activation(user: User, should_be_active: bool, admin: User) -> Tuple[bool, str]:
    user.is_active = should_be_active

    mikrotik_enabled_raw = settings_service.get_setting('ENABLE_MIKROTIK_OPERATIONS', 'True')
    mikrotik_enabled = str(mikrotik_enabled_raw or '').strip().lower() in {'true', '1', 't', 'yes'}
    if not mikrotik_enabled:
        return True, "Status pengguna berhasil diperbarui (Mikrotik dinonaktifkan)."

    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    if should_be_active:
        if not user.mikrotik_profile_name or not user.mikrotik_server_name:
            return False, "Profil atau Server Mikrotik belum diatur."
        success, msg = _sync_user_to_mikrotik(user, f"Re-activated by {admin.full_name}")
        if success:
            list_inactive = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive')
            _handle_mikrotik_operation(
                sync_address_list_for_user,
                username=format_to_local_phone(user.phone_number),
                target_list=None,
                other_lists=[list_inactive],
                comment=f"reactivated:{admin.full_name}"
            )
        return success, msg
    current_app.logger.info(f"Deactivating user {user.full_name}. Setting profile to 'inactive' and limit-bytes-total to 1.")
    inactive_profile = settings_service.get_setting('MIKROTIK_INACTIVE_PROFILE', 'inactive')
    success, msg = _handle_mikrotik_operation(
        activate_or_update_hotspot_user,
        user_mikrotik_username=format_to_local_phone(user.phone_number),
        hotspot_password=user.mikrotik_password,
        mikrotik_profile_name=inactive_profile,
        limit_bytes_total=1,
        session_timeout='1s',
        comment=f"Deactivated by {admin.full_name}",
        server=user.mikrotik_server_name,
        force_update_profile=True,
    )
    if success:
        user.mikrotik_user_exists = True
        list_active = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_ACTIVE', 'active') or 'active'
        list_fup = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_FUP', 'fup') or 'fup'
        list_inactive = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive') or 'inactive'
        list_expired = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_EXPIRED', 'expired') or 'expired'
        list_habis = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_HABIS', 'habis') or 'habis'
        list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'

        now = datetime.now(dt_timezone.utc)
        date_str, time_str = get_app_date_time_strings(now)
        username_08 = format_to_local_phone(user.phone_number) or ""
        comment = (
            f"lpsaring|status=inactive"
            f"|user={username_08}"
            f"|role={user.role.value}"
            f"|date={date_str}"
            f"|time={time_str}"
        )

        def _sync_inactive_with_fallback(api_connection, **kwargs):
            ok, msg = sync_address_list_for_user(api_connection=api_connection, **kwargs)
            if ok:
                return ok, msg
            if msg not in ("IP belum tersedia untuk user", "IP tidak ditemukan"):
                return ok, msg

            ok_map, binding_map, _map_msg = get_hotspot_ip_binding_user_map(api_connection)
            if not ok_map:
                return ok, msg

            fallback_ip = None
            for entry in binding_map.values():
                if str(entry.get('user_id')) == str(user.id):
                    address = entry.get('address')
                    if address:
                        fallback_ip = str(address)
                        break
            if not fallback_ip:
                return ok, msg

            ok_upsert, upsert_msg = upsert_address_list_entry(
                api_connection=api_connection,
                address=fallback_ip,
                list_name=list_inactive,
                comment=comment + f"|ip={fallback_ip}",
            )
            if not ok_upsert:
                return False, upsert_msg

            for list_name in [list_active, list_fup, list_blocked, list_expired, list_habis]:
                if list_name and list_name != list_inactive:
                    remove_address_list_entry(api_connection=api_connection, address=fallback_ip, list_name=list_name)

            return True, "Sukses (fallback ip-binding)"

        _handle_mikrotik_operation(
            _sync_inactive_with_fallback,
            username=(format_to_local_phone(user.phone_number) or user.phone_number or ""),
            target_list=list_inactive,
            other_lists=[list_active, list_fup, list_blocked, list_expired, list_habis],
            comment=comment,
        )
        _send_whatsapp_notification(
            user.phone_number,
            "user_access_inactive",
            {"full_name": user.full_name},
        )
    return success, msg


def _handle_user_blocking(user: User, should_be_blocked: bool, admin: User, reason: Optional[str]) -> Tuple[bool, str]:
    user.is_blocked = should_be_blocked
    user.blocked_reason = reason if should_be_blocked else None
    user.blocked_at = datetime.now(dt_timezone.utc) if should_be_blocked else None
    user.blocked_by_id = admin.id if should_be_blocked else None

    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    if should_be_blocked:
        blocked_profile = settings_service.get_setting('MIKROTIK_BLOCKED_PROFILE', 'inactive')
        success, msg = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=format_to_local_phone(user.phone_number),
            hotspot_password=user.mikrotik_password,
            mikrotik_profile_name=blocked_profile,
            limit_bytes_total=1,
            session_timeout='1s',
            comment=f"Blocked by {admin.full_name}",
            server=user.mikrotik_server_name,
            force_update_profile=True,
        )
        if success:
            list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'
            list_active = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_ACTIVE', 'active') or 'active'
            list_fup = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_FUP', 'fup') or 'fup'
            list_inactive = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive') or 'inactive'
            list_expired = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_EXPIRED', 'expired') or 'expired'
            list_habis = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_HABIS', 'habis') or 'habis'

            now = datetime.now(dt_timezone.utc)
            date_str, time_str = get_app_date_time_strings(now)
            username_08 = format_to_local_phone(user.phone_number) or ""
            comment = (
                f"lpsaring|status=blocked"
                f"|user={username_08}"
                f"|role={user.role.value}"
                f"|date={date_str}"
                f"|time={time_str}"
            )

            def _sync_blocked_with_fallback(api_connection, **kwargs):
                ok, msg = sync_address_list_for_user(api_connection=api_connection, **kwargs)
                if ok:
                    return ok, msg
                if msg not in ("IP belum tersedia untuk user", "IP tidak ditemukan"):
                    return ok, msg

                ok_map, binding_map, _map_msg = get_hotspot_ip_binding_user_map(api_connection)
                if not ok_map:
                    return ok, msg

                fallback_ip = None
                for entry in binding_map.values():
                    if str(entry.get('user_id')) == str(user.id):
                        address = entry.get('address')
                        if address:
                            fallback_ip = str(address)
                            break
                if not fallback_ip:
                    return ok, msg

                ok_upsert, upsert_msg = upsert_address_list_entry(
                    api_connection=api_connection,
                    address=fallback_ip,
                    list_name=list_blocked,
                    comment=comment + f"|ip={fallback_ip}",
                )
                if not ok_upsert:
                    return False, upsert_msg

                for list_name in [list_active, list_fup, list_inactive, list_expired, list_habis]:
                    if list_name and list_name != list_blocked:
                        remove_address_list_entry(api_connection=api_connection, address=fallback_ip, list_name=list_name)

                return True, "Sukses (fallback ip-binding)"

            _handle_mikrotik_operation(
                _sync_blocked_with_fallback,
                username=(format_to_local_phone(user.phone_number) or user.phone_number or ""),
                target_list=list_blocked,
                other_lists=[list_active, list_fup, list_inactive, list_expired, list_habis],
                comment=comment,
            )
            _send_whatsapp_notification(
                user.phone_number,
                "user_access_blocked",
                {
                    "full_name": user.full_name,
                    "reason": reason or "Tidak disebutkan",
                },
            )
        return success, msg

    # Unblock path
    # Requirement: unblock should set debt (auto + manual) to 0.
    manual_before = int(getattr(user, 'manual_debt_mb', 0) or 0)
    auto_before = float(compute_debt_mb(float(user.total_quota_purchased_mb or 0.0), float(user.total_quota_used_mb or 0.0)))
    paid_auto_mb, paid_manual_mb = debt_service.clear_all_debts_to_zero(
        user=user,
        admin_actor=admin,
        source='unblock',
    )

    success, msg = _sync_user_to_mikrotik(user, f"Unblocked by {admin.full_name}")
    if success:
        list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'

        now = datetime.now(dt_timezone.utc)
        date_str, time_str = get_app_date_time_strings(now)
        username_08 = format_to_local_phone(user.phone_number) or ""

        def _unblock_cleanup(api_connection, **kwargs):
            # Remove from blocked list via normal path (if MikroTik can resolve IP from username).
            sync_address_list_for_user(
                api_connection=api_connection,
                username=(format_to_local_phone(user.phone_number) or user.phone_number or ""),
                target_list=None,
                other_lists=[list_blocked],
                comment=f"unblocked:{admin.full_name}",
            )

            # Re-apply allowed ip-binding type (MAC-only) and remove blocked address-list using host table as fallback.
            binding_type = resolve_allowed_binding_type_for_user(user)
            comment = (
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source=unblock|date={date_str}|time={time_str}"
            )

            ok_bind, binding_map, _bind_msg = get_hotspot_ip_binding_user_map(api_connection)
            macs = []
            if ok_bind:
                for mac, entry in binding_map.items():
                    if str(entry.get('user_id')) == str(user.id):
                        macs.append(str(mac).upper())

            ok_host, host_map, _host_msg = get_hotspot_host_usage_map(api_connection)
            if ok_host and host_map and macs:
                for mac in macs:
                    host_ip = str(host_map.get(mac, {}).get('address') or '').strip()
                    if host_ip:
                        remove_address_list_entry(api_connection=api_connection, address=host_ip, list_name=list_blocked)

            # Ensure user's status list is correct immediately (habis/aktif/fup/expired/inactive)
            # using IP(s) from hotspot host table (if present).
            try:
                list_active = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_ACTIVE', 'active') or 'active'
                list_fup = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_FUP', 'fup') or 'fup'
                list_inactive = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive') or 'inactive'
                list_expired = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_EXPIRED', 'expired') or 'expired'
                list_habis = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_HABIS', 'habis') or 'habis'
                fup_threshold = settings_service.get_setting_as_int('QUOTA_FUP_PERCENT', 20)

                purchased_mb = float(user.total_quota_purchased_mb or 0.0)
                used_mb = float(user.total_quota_used_mb or 0.0)
                remaining_mb = max(0.0, purchased_mb - used_mb)
                remaining_percent = 0.0
                if purchased_mb > 0:
                    remaining_percent = (remaining_mb / purchased_mb) * 100.0

                now_utc = datetime.now(dt_timezone.utc)
                is_expired = bool(user.quota_expiry_date and user.quota_expiry_date < now_utc)

                if is_expired:
                    target_list = list_expired
                    status_value = 'expired'
                elif user.is_unlimited_user:
                    target_list = list_active
                    status_value = 'unlimited'
                elif purchased_mb <= 0 and not is_expired:
                    target_list = list_inactive
                    status_value = 'inactive'
                elif remaining_mb <= 0:
                    target_list = list_habis
                    status_value = 'habis'
                elif remaining_percent <= float(fup_threshold):
                    target_list = list_fup
                    status_value = 'fup'
                else:
                    target_list = list_active
                    status_value = 'active'

                other_lists = [list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked]

                if ok_host and host_map and macs:
                    for mac in macs:
                        host_ip = str(host_map.get(mac, {}).get('address') or '').strip()
                        if not host_ip:
                            continue
                        upsert_address_list_entry(
                            api_connection=api_connection,
                            address=host_ip,
                            list_name=target_list,
                            comment=(
                                f"lpsaring|status={status_value}"
                                f"|user={username_08}"
                                f"|role={user.role.value}"
                                f"|source=unblock"
                                f"|date={date_str}"
                                f"|time={time_str}"
                            ),
                        )
                        for list_name in other_lists:
                            if list_name and list_name != target_list:
                                remove_address_list_entry(
                                    api_connection=api_connection,
                                    address=host_ip,
                                    list_name=list_name,
                                )
            except Exception:
                pass

            # Extra cleanup: remove stale blocked entries that reference this user in comment,
            # even if the IP is no longer present in host table.
            try:
                fw_resource = api_connection.get_resource('/ip/firewall/address-list')
                blocked_rows = fw_resource.get(list=list_blocked)
                token_uid = f"uid={user.id}"
                token_user = f"user={username_08}"
                for row in blocked_rows or []:
                    c = str(row.get('comment') or '')
                    if (token_uid in c) or (token_user in c) or (username_08 and username_08 in c):
                        row_id = row.get('id') or row.get('.id')
                        if row_id:
                            fw_resource.remove(id=row_id)
            except Exception:
                pass

            for mac in macs:
                upsert_ip_binding(
                    api_connection=api_connection,
                    mac_address=mac,
                    server=user.mikrotik_server_name,
                    binding_type=binding_type,
                    comment=comment,
                )

            return True, "Sukses (unblock cleanup)"

        _handle_mikrotik_operation(_unblock_cleanup)

    # Notify user: debt cleared + access unblocked.
    try:
        purchased_now = float(user.total_quota_purchased_mb or 0.0)
        used_now = float(user.total_quota_used_mb or 0.0)
        remaining_mb = max(0.0, purchased_now - used_now)
        _send_whatsapp_notification(
            user.phone_number,
            'user_debt_cleared_unblock',
            {
                'full_name': user.full_name,
                'paid_auto_debt_mb': int(paid_auto_mb),
                'paid_manual_debt_mb': int(paid_manual_mb),
                'paid_total_debt_mb': int(paid_auto_mb) + int(paid_manual_mb),
                'manual_debt_before_mb': int(manual_before),
                'auto_debt_before_mb': float(auto_before),
                'remaining_mb': float(remaining_mb),
                'reason': reason or '',
            },
        )
    except Exception:
        pass

    _log_admin_action(
        admin,
        user,
        AdminActionType.UNBLOCK_USER,
        {
            'blocked_reason': reason,
            'paid_auto_debt_mb': int(paid_auto_mb),
            'paid_manual_debt_mb': int(paid_manual_mb),
        },
    )
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
        if days > 0:
            timeout_parts.append(f"{days}d")
        if hours > 0:
            timeout_parts.append(f"{hours}h")
        if mins > 0:
            timeout_parts.append(f"{mins}m")
        if secs > 0:
            timeout_parts.append(f"{secs}s")
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
    if success:
        user.mikrotik_user_exists = True
    return success, msg