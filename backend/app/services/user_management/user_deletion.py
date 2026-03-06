# backend/app/services/user_management/user_deletion.py

from typing import Tuple
from sqlalchemy import select
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType, UserDevice
from app.services import settings_service
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action, _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import delete_hotspot_user
from app.services.device_management_service import _remove_ip_binding, _remove_blocked_address_list


def process_user_removal(user_to_remove: User, admin_actor: User) -> Tuple[bool, str]:
    """
    Memproses penghapusan atau penonaktifan pengguna berdasarkan peran admin.
    - Secara default semua aksi bersifat nonaktifkan (soft delete).
    - Hard delete hanya diizinkan jika ALLOW_USER_HARD_DELETE=True.
    """
    if user_to_remove.id == admin_actor.id:
        return False, "Anda tidak dapat menghapus/menonaktifkan akun Anda sendiri."

    allow_hard_delete = settings_service.get_setting_as_bool("ALLOW_USER_HARD_DELETE", False)

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
                _remove_ip_binding(device.mac_address, user_to_remove.mikrotik_server_name or "all")
            if device.ip_address:
                _remove_blocked_address_list(device.ip_address)
            db.session.delete(device)

    # --- LOGIKA UNTUK SUPER ADMIN (HAPUS PERMANEN) ---
    if admin_actor.is_super_admin_role and allow_hard_delete:
        current_app.logger.warning(
            "SUPER ADMIN ACTION: Hard deleting user %s (ALLOW_USER_HARD_DELETE=True).",
            user_to_remove.full_name,
        )
        if mikrotik_username:
            success, msg = _handle_mikrotik_operation(delete_hotspot_user, username=mikrotik_username)
            if not success and "tidak ditemukan" not in msg:
                return False, f"Gagal menghapus pengguna di Mikrotik ({msg}). Pengguna di database TIDAK dihapus."
        _cleanup_devices()

        _log_admin_action(
            admin_actor,
            user_to_remove,
            AdminActionType.MANUAL_USER_DELETE,
            details={
                "deleted_user_name": user_to_remove.full_name,
                "deleted_user_phone": user_to_remove.phone_number,
                "mikrotik_status": "Berhasil",
                "hard_delete_enabled": True,
            },
        )
        db.session.delete(user_to_remove)
        return True, f"Pengguna {user_to_remove.full_name} berhasil DIHAPUS secara permanen."

    # --- LOGIKA DEFAULT (SOFT DELETE / NONAKTIFKAN) ---
    if admin_actor.is_super_admin_role and not allow_hard_delete:
        current_app.logger.warning(
            "SUPER ADMIN ACTION: Hard delete disabled; deactivating user %s.",
            user_to_remove.full_name,
        )
    else:
        current_app.logger.info(f"ADMIN ACTION: Deactivating user {user_to_remove.full_name}.")

    if not user_to_remove.is_active and not user_to_remove.mikrotik_user_exists:
        return False, "Pengguna ini sudah dalam status nonaktif."

    if mikrotik_username:
        mikrotik_success, mikrotik_msg = _handle_mikrotik_operation(delete_hotspot_user, username=mikrotik_username)
        if not mikrotik_success and "tidak ditemukan" not in mikrotik_msg:
            return False, f"Gagal menghapus pengguna di Mikrotik: {mikrotik_msg}. Aksi dibatalkan."

    user_to_remove.is_active = False
    user_to_remove.mikrotik_user_exists = False
    _cleanup_devices()

    _log_admin_action(
        admin_actor,
        user_to_remove,
        AdminActionType.DEACTIVATE_USER,
        details={
            "reason": "Delete action resolved as soft delete",
            "hard_delete_enabled": allow_hard_delete,
        },
    )

    if admin_actor.is_super_admin_role and not allow_hard_delete:
        return True, (
            f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dihapus dari Mikrotik "
            "(hard delete dinonaktifkan)."
        )

    return True, f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dihapus dari Mikrotik."
