# backend/app/services/user_management/user_deletion.py
# VERSI FINAL LENGKAP: Memanggil purge_user_from_hotspot untuk pembersihan total.

from typing import Tuple
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action
from app.infrastructure.gateways.mikrotik_client import purge_user_from_hotspot

def process_user_removal(user_to_remove: User, admin_actor: User) -> Tuple[bool, str]:
    """
    Memproses penghapusan atau penonaktifan pengguna berdasarkan peran admin.
    """
    if user_to_remove.id == admin_actor.id:
        return False, "Anda tidak dapat menghapus/menonaktifkan akun Anda sendiri."

    if user_to_remove.role == UserRole.SUPER_ADMIN:
        return False, "Akses ditolak: Super Admin tidak dapat dihapus."
    
    if not admin_actor.is_super_admin_role and user_to_remove.is_admin_role:
        return False, "Akses ditolak: Anda tidak punya izin untuk menghapus/menonaktifkan admin lain."

    mikrotik_username = format_to_local_phone(user_to_remove.phone_number)

    if admin_actor.is_super_admin_role:
        current_app.logger.info(f"SUPER ADMIN ACTION: Menghapus total user {user_to_remove.full_name}.")
        if mikrotik_username:
            success, msg = purge_user_from_hotspot(username=mikrotik_username)
            
            if not success:
                return False, f"Gagal membersihkan pengguna di Mikrotik ({msg}). Pengguna di database TIDAK dihapus."
        
        _log_admin_action(
            admin_actor, 
            user_to_remove, 
            AdminActionType.MANUAL_USER_DELETE, 
            details={
                "deleted_user_name": user_to_remove.full_name,
                "deleted_user_phone": user_to_remove.phone_number,
                "mikrotik_status": "Pembersihan total dijalankan."
            }
        )
        db.session.delete(user_to_remove)
        return True, f"Pengguna {user_to_remove.full_name} berhasil DIHAPUS secara permanen dan semua jejak di MikroTik telah dibersihkan."

    else:
        current_app.logger.info(f"ADMIN ACTION: Deactivating user {user_to_remove.full_name}.")
        if not user_to_remove.is_active and user_to_remove.is_blocked:
            return False, "Pengguna ini sudah dalam status nonaktif dan terblokir."

        user_to_remove.is_active = False
        user_to_remove.is_blocked = True
        
        from app.tasks import sync_single_user_status
        sync_single_user_status.delay(user_id=str(user_to_remove.id))

        _log_admin_action(
            admin_actor,
            user_to_remove,
            AdminActionType.DEACTIVATE_USER,
            details={"reason": "Admin 'delete' action"}
        )
        return True, f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dijadwalkan untuk sinkronisasi blokir."