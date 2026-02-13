# backend/app/services/user_management/user_deletion.py

from typing import Tuple
from sqlalchemy import select
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType, UserDevice
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action, _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import delete_hotspot_user
from app.services.device_management_service import _remove_ip_binding, _remove_blocked_address_list

def process_user_removal(user_to_remove: User, admin_actor: User) -> Tuple[bool, str]:
    """
    Memproses penghapusan atau penonaktifan pengguna berdasarkan peran admin.
    - Super Admin akan menghapus pengguna secara permanen.
    - Admin biasa akan menonaktifkan pengguna.
    """
    if user_to_remove.id == admin_actor.id:
        return False, "Anda tidak dapat menghapus/menonaktifkan akun Anda sendiri."

    # Super Admin tidak dapat dihapus
    if user_to_remove.role == UserRole.SUPER_ADMIN:
        return False, "Akses ditolak: Super Admin tidak dapat dihapus."
    
    # Admin biasa tidak bisa menargetkan Admin lain atau Super Admin
    if not admin_actor.is_super_admin_role and user_to_remove.is_admin_role:
        return False, "Akses ditolak: Anda tidak punya izin untuk menghapus/menonaktifkan admin lain."

    mikrotik_username = format_to_local_phone(user_to_remove.phone_number)
    devices = db.session.scalars(select(UserDevice).where(UserDevice.user_id == user_to_remove.id)).all()

    def _cleanup_devices() -> None:
        for device in devices:
            if device.mac_address:
                _remove_ip_binding(device.mac_address, user_to_remove.mikrotik_server_name or 'all')
            if device.ip_address:
                _remove_blocked_address_list(device.ip_address)
            db.session.delete(device)

    # --- LOGIKA UNTUK SUPER ADMIN (HAPUS PERMANEN) ---
    if admin_actor.is_super_admin_role:
        current_app.logger.info(f"SUPER ADMIN ACTION: Deleting user {user_to_remove.full_name} permanently.")
        if mikrotik_username:
            success, msg = _handle_mikrotik_operation(delete_hotspot_user, username=mikrotik_username)
            if not success and "tidak ditemukan" not in msg:
                return False, f"Gagal menghapus pengguna di Mikrotik ({msg}). Pengguna di database TIDAK dihapus."
        _cleanup_devices()
        
        # [PERBAIKAN BUG] Memanggil _log_admin_action dengan argumen yang benar
        if not admin_actor.is_super_admin_role:
            _log_admin_action(
                admin_actor, 
                user_to_remove, 
                AdminActionType.MANUAL_USER_DELETE, 
                details={
                    "deleted_user_name": user_to_remove.full_name,
                    "deleted_user_phone": user_to_remove.phone_number,
                    "mikrotik_status": "Berhasil"
                }
            )
        db.session.delete(user_to_remove)
        return True, f"Pengguna {user_to_remove.full_name} berhasil DIHAPUS secara permanen."

    # --- LOGIKA UNTUK ADMIN BIASA (NONAKTIFKAN + HAPUS DI MIKROTIK) ---
    else:
        current_app.logger.info(f"ADMIN ACTION: Deactivating user {user_to_remove.full_name}.")
        if not user_to_remove.is_active:
            return False, "Pengguna ini sudah dalam status nonaktif."

        # Hapus user di Mikrotik juga untuk admin biasa
        if mikrotik_username:
            mikrotik_success, mikrotik_msg = _handle_mikrotik_operation(
                delete_hotspot_user,
                username=mikrotik_username
            )
            if not mikrotik_success and "tidak ditemukan" not in mikrotik_msg:
                return False, f"Gagal menghapus pengguna di Mikrotik: {mikrotik_msg}. Aksi dibatalkan."

        user_to_remove.is_active = False
        user_to_remove.mikrotik_user_exists = False
        _cleanup_devices()

        # [PERBAIKAN BUG] Memanggil _log_admin_action dengan argumen yang benar
        _log_admin_action(
            admin_actor,
            user_to_remove,
            AdminActionType.DEACTIVATE_USER, # Menggunakan tipe log yang lebih sesuai
            details={"reason": "Admin 'delete' action"}
        )
        return True, f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dihapus dari Mikrotik."