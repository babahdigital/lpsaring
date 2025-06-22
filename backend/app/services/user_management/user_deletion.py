# backend/app/services/user_management/user_deletion.py

from typing import Tuple
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action, _handle_mikrotik_operation, _generate_password
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user, delete_hotspot_user

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

    # --- LOGIKA UNTUK SUPER ADMIN (HAPUS PERMANEN) ---
    if admin_actor.is_super_admin_role:
        current_app.logger.info(f"SUPER ADMIN ACTION: Deleting user {user_to_remove.full_name} permanently.")
        if mikrotik_username:
            success, msg = _handle_mikrotik_operation(delete_hotspot_user, username=mikrotik_username)
            if not success and "tidak ditemukan" not in msg:
                return False, f"Gagal menghapus pengguna di Mikrotik ({msg}). Pengguna di database TIDAK dihapus."
        
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

    # --- LOGIKA UNTUK ADMIN BIASA (NONAKTIFKAN) ---
    else:
        current_app.logger.info(f"ADMIN ACTION: Deactivating user {user_to_remove.full_name}.")
        if not user_to_remove.is_active:
            return False, "Pengguna ini sudah dalam status nonaktif."

        user_to_remove.is_active = False
        if not user_to_remove.mikrotik_password:
            user_to_remove.mikrotik_password = _generate_password()

        mikrotik_success, mikrotik_msg = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=mikrotik_username,
            hotspot_password=user_to_remove.mikrotik_password,
            mikrotik_profile_name='inactive',
            limit_bytes_total=1,
            comment=f"Deactivated via delete action by {admin_actor.full_name}"
        )

        if not mikrotik_success:
            # Kembalikan status jika gagal sinkronisasi Mikrotik
            user_to_remove.is_active = True
            return False, f"Gagal sinkronisasi Mikrotik: {mikrotik_msg}. Aksi dibatalkan."

        # [PERBAIKAN BUG] Memanggil _log_admin_action dengan argumen yang benar
        _log_admin_action(
            admin_actor,
            user_to_remove,
            AdminActionType.DEACTIVATE_USER, # Menggunakan tipe log yang lebih sesuai
            details={"reason": "Admin 'delete' action"}
        )
        return True, f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN."