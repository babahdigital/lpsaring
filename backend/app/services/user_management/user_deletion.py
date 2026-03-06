# backend/app/services/user_management/user_deletion.py

from typing import Any, Optional, Sequence, Tuple
from sqlalchemy import select
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType, UserDevice, RefreshToken
from app.services import settings_service
from app.utils.formatters import format_to_local_phone
from .helpers import _log_admin_action, _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import delete_hotspot_user, get_mikrotik_connection


def _row_id(row: dict[str, Any]) -> Optional[str]:
    value = row.get("id") or row.get(".id")
    if value is None:
        return None
    return str(value)


def _remove_rows(resource: Any, rows: list[dict[str, Any]], errors: list[str], removed_ids: set[str]) -> int:
    removed = 0
    for row in rows:
        rid = _row_id(row)
        if not rid or rid in removed_ids:
            continue

        try:
            resource.remove(id=rid)
            removed += 1
            removed_ids.add(rid)
            continue
        except Exception:
            pass

        try:
            resource.remove(**{".id": rid})
            removed += 1
            removed_ids.add(rid)
        except Exception as e:
            errors.append(str(e))

    return removed


def _build_managed_list_names() -> list[str]:
    keys = [
        ("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked"),
        ("MIKROTIK_ADDRESS_LIST_ACTIVE", "active"),
        ("MIKROTIK_ADDRESS_LIST_FUP", "fup"),
        ("MIKROTIK_ADDRESS_LIST_HABIS", "habis"),
        ("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired"),
        ("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive"),
        ("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized"),
    ]

    names: list[str] = []
    for key, default_name in keys:
        value = settings_service.get_setting(key, default_name) or default_name
        normalized = str(value).strip()
        if normalized and normalized not in names:
            names.append(normalized)

    return names


def _cleanup_router_artifacts(user_to_remove: User, devices: Sequence[UserDevice]) -> dict[str, Any]:
    macs = sorted({str(d.mac_address).strip().upper() for d in devices if getattr(d, "mac_address", None)})
    ips = sorted({str(d.ip_address).strip() for d in devices if getattr(d, "ip_address", None)})

    username_08 = str(format_to_local_phone(getattr(user_to_remove, "phone_number", None)) or "").strip()
    uid_marker = f"uid={user_to_remove.id}".lower()
    user_marker = f"user={username_08}".lower() if username_08 else ""

    def _comment_matches_user(comment: object) -> bool:
        if not comment:
            return False
        text = str(comment).lower()
        return uid_marker in text or (bool(user_marker) and user_marker in text)

    summary: dict[str, Any] = {
        "mikrotik_connected": False,
        "hotspot_active_removed": 0,
        "hotspot_hosts_removed": 0,
        "ip_bindings_removed": 0,
        "dhcp_leases_removed": 0,
        "arp_entries_removed": 0,
        "address_list_entries_removed": 0,
        "comment_tagged_entries_removed": 0,
        "errors": [],
    }
    errors = summary["errors"]

    try:
        with get_mikrotik_connection(raise_on_error=False) as api:
            if not api:
                return summary

            summary["mikrotik_connected"] = True

            try:
                active_res = api.get_resource("/ip/hotspot/active")
                active_removed_ids: set[str] = set()
                for mac in macs:
                    summary["hotspot_active_removed"] += _remove_rows(
                        active_res,
                        active_res.get(**{"mac-address": mac}) or [],
                        errors,
                        active_removed_ids,
                    )
                for ip in ips:
                    summary["hotspot_active_removed"] += _remove_rows(
                        active_res,
                        active_res.get(address=ip) or [],
                        errors,
                        active_removed_ids,
                    )
                if username_08:
                    summary["hotspot_active_removed"] += _remove_rows(
                        active_res,
                        active_res.get(user=username_08) or [],
                        errors,
                        active_removed_ids,
                    )

                for row in active_res.get() or []:
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            active_res,
                            [row],
                            errors,
                            active_removed_ids,
                        )
            except Exception as e:
                errors.append(f"hotspot_active_cleanup: {e}")

            try:
                host_res = api.get_resource("/ip/hotspot/host")
                host_removed_ids: set[str] = set()
                for mac in macs:
                    summary["hotspot_hosts_removed"] += _remove_rows(
                        host_res,
                        host_res.get(**{"mac-address": mac}) or [],
                        errors,
                        host_removed_ids,
                    )
                for ip in ips:
                    summary["hotspot_hosts_removed"] += _remove_rows(
                        host_res,
                        host_res.get(address=ip) or [],
                        errors,
                        host_removed_ids,
                    )
                if username_08:
                    summary["hotspot_hosts_removed"] += _remove_rows(
                        host_res,
                        host_res.get(user=username_08) or [],
                        errors,
                        host_removed_ids,
                    )

                for row in host_res.get() or []:
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            host_res,
                            [row],
                            errors,
                            host_removed_ids,
                        )
            except Exception as e:
                errors.append(f"hotspot_host_cleanup: {e}")

            try:
                ipb_res = api.get_resource("/ip/hotspot/ip-binding")
                ipb_removed_ids: set[str] = set()
                for mac in macs:
                    summary["ip_bindings_removed"] += _remove_rows(
                        ipb_res,
                        ipb_res.get(**{"mac-address": mac}) or [],
                        errors,
                        ipb_removed_ids,
                    )
                for row in ipb_res.get() or []:
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            ipb_res,
                            [row],
                            errors,
                            ipb_removed_ids,
                        )
            except Exception as e:
                errors.append(f"ip_binding_cleanup: {e}")

            try:
                lease_res = api.get_resource("/ip/dhcp-server/lease")
                lease_removed_ids: set[str] = set()
                for mac in macs:
                    summary["dhcp_leases_removed"] += _remove_rows(
                        lease_res,
                        lease_res.get(**{"mac-address": mac}) or [],
                        errors,
                        lease_removed_ids,
                    )
                for ip in ips:
                    summary["dhcp_leases_removed"] += _remove_rows(
                        lease_res,
                        lease_res.get(address=ip) or [],
                        errors,
                        lease_removed_ids,
                    )
                for row in lease_res.get() or []:
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            lease_res,
                            [row],
                            errors,
                            lease_removed_ids,
                        )
            except Exception as e:
                errors.append(f"dhcp_lease_cleanup: {e}")

            try:
                arp_res = api.get_resource("/ip/arp")
                arp_removed_ids: set[str] = set()
                for mac in macs:
                    summary["arp_entries_removed"] += _remove_rows(
                        arp_res,
                        arp_res.get(**{"mac-address": mac}) or [],
                        errors,
                        arp_removed_ids,
                    )
                for ip in ips:
                    summary["arp_entries_removed"] += _remove_rows(
                        arp_res,
                        arp_res.get(address=ip) or [],
                        errors,
                        arp_removed_ids,
                    )
                for row in arp_res.get() or []:
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            arp_res,
                            [row],
                            errors,
                            arp_removed_ids,
                        )
            except Exception as e:
                errors.append(f"arp_cleanup: {e}")

            try:
                address_list_res = api.get_resource("/ip/firewall/address-list")
                address_removed_ids: set[str] = set()
                managed_lists = _build_managed_list_names()
                for ip in ips:
                    for list_name in managed_lists:
                        summary["address_list_entries_removed"] += _remove_rows(
                            address_list_res,
                            address_list_res.get(address=ip, list=list_name) or [],
                            errors,
                            address_removed_ids,
                        )

                managed_set = set(managed_lists)
                for row in address_list_res.get() or []:
                    row_list = str(row.get("list") or "").strip()
                    if row_list not in managed_set:
                        continue
                    if _comment_matches_user(row.get("comment")):
                        summary["comment_tagged_entries_removed"] += _remove_rows(
                            address_list_res,
                            [row],
                            errors,
                            address_removed_ids,
                        )
            except Exception as e:
                errors.append(f"address_list_cleanup: {e}")
    except Exception as e:
        errors.append(f"mikrotik_connection: {e}")

    return summary


def _run_auth_cleanup(user_to_remove: User, devices: Sequence[UserDevice]) -> tuple[int, int, dict[str, Any]]:
    tokens_deleted = (
        db.session.query(RefreshToken).filter(RefreshToken.user_id == user_to_remove.id).delete(synchronize_session=False)
    )
    devices_deleted = (
        db.session.query(UserDevice).filter(UserDevice.user_id == user_to_remove.id).delete(synchronize_session=False)
    )
    router_summary = _cleanup_router_artifacts(user_to_remove, devices)
    return int(tokens_deleted or 0), int(devices_deleted or 0), router_summary


def run_user_auth_cleanup(user_to_remove: User) -> dict[str, Any]:
    """Bersihkan token/device DB dan artefak router untuk satu user.

    Dipakai oleh endpoint delete user dan reset-login agar perilaku cleanup konsisten.
    """
    devices = db.session.scalars(select(UserDevice).where(UserDevice.user_id == user_to_remove.id)).all()
    macs = sorted({str(d.mac_address).strip().upper() for d in devices if getattr(d, "mac_address", None)})
    ips = sorted({str(d.ip_address).strip() for d in devices if getattr(d, "ip_address", None)})
    username_08 = str(format_to_local_phone(getattr(user_to_remove, "phone_number", None)) or "").strip()

    tokens_deleted, devices_deleted, router_summary = _run_auth_cleanup(user_to_remove, devices)

    return {
        "tokens_deleted": tokens_deleted,
        "devices_deleted": devices_deleted,
        "device_count_before": int(len(devices)),
        "macs": macs,
        "ips": ips,
        "mac_count": int(len(macs)),
        "ip_count": int(len(ips)),
        "username_08": username_08,
        "router": router_summary,
    }


def _format_cleanup_message(
    base_message: str,
    tokens_deleted: int,
    devices_deleted: int,
    router_summary: dict[str, Any],
) -> str:
    msg = f"{base_message} Token dibersihkan: {tokens_deleted}. Session device dibersihkan: {devices_deleted}."
    if router_summary.get("mikrotik_connected") is not True:
        msg += " Cleanup router tambahan dilewati (MikroTik tidak terhubung)."
    elif router_summary.get("errors"):
        msg += " Cleanup router selesai dengan beberapa catatan."
    return msg


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

        cleanup_summary = run_user_auth_cleanup(user_to_remove)
        tokens_deleted = int(cleanup_summary["tokens_deleted"])
        devices_deleted = int(cleanup_summary["devices_deleted"])
        router_summary = cleanup_summary["router"]

        _log_admin_action(
            admin_actor,
            user_to_remove,
            AdminActionType.MANUAL_USER_DELETE,
            details={
                "deleted_user_name": user_to_remove.full_name,
                "deleted_user_phone": user_to_remove.phone_number,
                "mikrotik_status": "Berhasil",
                "hard_delete_enabled": True,
                "tokens_deleted": tokens_deleted,
                "devices_deleted": devices_deleted,
                "router_cleanup": router_summary,
            },
        )
        db.session.delete(user_to_remove)
        base_message = f"Pengguna {user_to_remove.full_name} berhasil DIHAPUS secara permanen."
        return True, _format_cleanup_message(base_message, tokens_deleted, devices_deleted, router_summary)

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

    cleanup_summary = run_user_auth_cleanup(user_to_remove)
    tokens_deleted = int(cleanup_summary["tokens_deleted"])
    devices_deleted = int(cleanup_summary["devices_deleted"])
    router_summary = cleanup_summary["router"]

    user_to_remove.is_active = False
    user_to_remove.mikrotik_user_exists = False

    _log_admin_action(
        admin_actor,
        user_to_remove,
        AdminActionType.DEACTIVATE_USER,
        details={
            "reason": "Delete action resolved as soft delete",
            "hard_delete_enabled": allow_hard_delete,
            "tokens_deleted": tokens_deleted,
            "devices_deleted": devices_deleted,
            "router_cleanup": router_summary,
        },
    )

    if admin_actor.is_super_admin_role and not allow_hard_delete:
        base_message = (
            f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dihapus dari Mikrotik "
            "(hard delete dinonaktifkan)."
        )
        return True, _format_cleanup_message(base_message, tokens_deleted, devices_deleted, router_summary)

    base_message = f"Pengguna {user_to_remove.full_name} berhasil DINONAKTIFKAN dan dihapus dari Mikrotik."
    return True, _format_cleanup_message(base_message, tokens_deleted, devices_deleted, router_summary)
