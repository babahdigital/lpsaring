# backend/app/services/user_management/user_deletion.py
# VERSI FINAL LENGKAP: Memanggil purge_user_from_hotspot untuk pembersihan total.

from typing import Tuple
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action
from app.infrastructure.gateways.mikrotik_client import (
    purge_user_from_hotspot,
    remove_ip_from_all_address_lists,
    get_host_details_by_username,
    delete_ip_binding_by_comment,
    get_mikrotik_connection,
    delete_hotspot_user,
)

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
        mt_ops = []
        if mikrotik_username:
            # 1) Tendang sesi aktif/host
            success, msg = purge_user_from_hotspot(username=mikrotik_username)
            mt_ops.append(("purge", success, msg))

            # 2) Hapus dari semua address list (berdasar IP)
            target_ip = user_to_remove.last_login_ip
            if not target_ip:
                try:
                    ok_host, host, _ = get_host_details_by_username(mikrotik_username)
                    if ok_host and host:
                        target_ip = host.get('address')
                except Exception as e:
                    current_app.logger.warning(f"Lookup host by username gagal: {e}")
            if target_ip:
                ok_al, msg_al = remove_ip_from_all_address_lists(target_ip)
                mt_ops.append(("addr-list", ok_al, msg_al))
            else:
                current_app.logger.info("Tidak ada IP untuk pembersihan address-list.")

            # 3) Hapus hotspot user dan ip-binding (by comment)
            try:
                with get_mikrotik_connection() as api:
                    ok_del, msg_del = delete_hotspot_user(api, mikrotik_username)
                    mt_ops.append(("del-user", ok_del, msg_del))
            except Exception as e:
                mt_ops.append(("del-user", False, f"Exception: {e}"))
            try:
                ok_bind, msg_bind = delete_ip_binding_by_comment(mikrotik_username)
                mt_ops.append(("del-binding", ok_bind, msg_bind))
            except Exception as e:
                mt_ops.append(("del-binding", False, f"Exception: {e}"))

        # Log ringkasan operasi MikroTik
        for tag, ok, msg in mt_ops:
            level = 'info' if ok else 'warning'
            getattr(current_app.logger, level)(f"[DELETE][{tag}] {msg}")

        _log_admin_action(
            admin_actor, 
            user_to_remove, 
            AdminActionType.MANUAL_USER_DELETE, 
            details={
                "deleted_user_name": user_to_remove.full_name,
                "deleted_user_phone": user_to_remove.phone_number,
                "mikrotik_ops": [{"step": t, "ok": o, "msg": m} for (t,o,m) in mt_ops],
            }
        )
        db.session.delete(user_to_remove)
        return True, f"Pengguna {user_to_remove.full_name} dihapus dan dibersihkan dari MikroTik (sebisa mungkin)."

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