# mikrotik_client/__init__.py
# Reexport semua fungsi dari modul parent
"""Mikrotik client package lazy wrapper.

Semua logika utama sekarang berada di `mikrotik_client_impl.py`.
File ini hanya melakukan lazy import agar:
1. Menghindari circular import saat app factory belum siap
2. Mempercepat startup saat beberapa modul tidak dipakai
3. Menyediakan fallback error yang jelas jika implementasi gagal di-load
"""
from typing import Optional, Tuple, Dict, Any

"""
PENTING:
File __init__.py ini sekarang hanya menyediakan *lazy wrapper* agar menghindari circular import
tetapi tetap memanggil implementasi asli di mikrotik_client.py ketika tersedia.

Jika implementasi asli gagal di-import (misal saat fase migrasi awal), wrapper akan mengembalikan
pesan error yang jelas tanpa mengembalikan MAC palsu '00:00:00:00:00:00'.

Hindari menaruh logika bisnis baru di sini.
"""

def _lazy_impl():  # type: ignore
    """Lazy import modul implementasi.
    Implementasi sekarang berada di `mikrotik_client_impl.py` (memecah konflik nama
    antara package dan file). Wrapper ini tetap mempertahankan API publik lama.
    """
    from app.infrastructure.gateways import mikrotik_client_impl as _impl  # type: ignore
    return _impl

_PLACEHOLDER_MAC = "00:00:00:00:00:00"

def find_mac_by_ip_comprehensive(ip_address: str, force_refresh: bool = False) -> Tuple[bool, Optional[str], str]:
    try:
        return _lazy_impl().find_mac_by_ip_comprehensive(ip_address, force_refresh=force_refresh)  # type: ignore
    except Exception as e:  # pragma: no cover - defensive
        return False, None, f"lazy-wrapper error: {e}"

def activate_or_update_hotspot_user(user_mikrotik_username: str, mikrotik_profile_name: str,
                                    hotspot_password: Optional[str], **kwargs) -> Tuple[bool, str]:
    try:
        return _lazy_impl().activate_or_update_hotspot_user(user_mikrotik_username, mikrotik_profile_name, hotspot_password, **kwargs)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def disable_ip_binding_by_comment(comment: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().disable_ip_binding_by_comment(comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def create_or_update_ip_binding(mac_address: str, ip_address: str, comment: str, **kwargs) -> Tuple[bool, str]:
    try:
        return _lazy_impl().create_or_update_ip_binding(mac_address, ip_address, comment, **kwargs)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def get_active_session_by_ip(ip_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        return _lazy_impl().get_active_session_by_ip(ip_address)  # type: ignore
    except Exception as e:
        return False, None, f"lazy-wrapper error: {e}"

def get_ip_binding_details(mac_or_ip_or_comment: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        return _lazy_impl().get_ip_binding_details(mac_or_ip_or_comment)  # type: ignore
    except Exception as e:
        return False, None, f"lazy-wrapper error: {e}"

def get_host_details_by_mac(mac_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        return _lazy_impl().get_host_details_by_mac(mac_address)  # type: ignore
    except Exception as e:
        return False, None, f"lazy-wrapper error: {e}"

def get_host_details_by_username(username: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        return _lazy_impl().get_host_details_by_username(username)  # type: ignore
    except Exception as e:
        return False, None, f"lazy-wrapper error: {e}"

def add_ip_to_address_list(list_name: str, address: str, comment: str = "") -> Tuple[bool, str]:
    try:
        return _lazy_impl().add_ip_to_address_list(list_name, address, comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def remove_ip_from_address_list(list_name: str, address: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().remove_ip_from_address_list(list_name, address)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def move_user_to_inactive_list(user_ip: str, comment: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().move_user_to_inactive_list(user_ip, comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def find_and_update_address_list_entry(list_name: str, address: str,
                                       new_comment: Optional[str] = None) -> Tuple[bool, str]:
    try:
        return _lazy_impl().find_and_update_address_list_entry(list_name, address, new_comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def purge_user_from_hotspot(username: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().purge_user_from_hotspot(username)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def purge_user_from_hotspot_by_comment(comment: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().purge_user_from_hotspot_by_comment(comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def ensure_ip_binding_status_matches_profile(username: str, profile_name: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().ensure_ip_binding_status_matches_profile(username, profile_name)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def find_and_remove_static_lease_by_mac(mac: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().find_and_remove_static_lease_by_mac(mac)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def create_static_lease(ip: str, mac: str, comment: str) -> Tuple[bool, str]:
    try:
        return _lazy_impl().create_static_lease(ip, mac, comment)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def get_hotspot_user_details(username: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        return _lazy_impl().get_hotspot_user_details(username)  # type: ignore
    except Exception as e:
        return False, None, f"lazy-wrapper error: {e}"

def sync_address_list_for_user(username: str, new_ip_address: str, target_profile_name: str, old_ip_address: Optional[str] = None) -> Tuple[bool, str]:
    try:
        return _lazy_impl().sync_address_list_for_user(username, new_ip_address, target_profile_name, old_ip_address)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"
    
def _get_api_from_pool(pool_name=None) -> Any:  # pylint: disable=unused-argument
    try:
        return _lazy_impl()._get_api_from_pool(pool_name)  # type: ignore
    except Exception:
        return None

def get_mikrotik_connection():
    try:
        return _lazy_impl().get_mikrotik_connection()  # type: ignore
    except Exception as e:
        raise RuntimeError(f"lazy-wrapper error: {e}")

def delete_hotspot_user(api, username: str):
    try:
        return _lazy_impl().delete_hotspot_user(api, username)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"

def format_to_local_phone(phone: str):  # simple passthrough
    try:
        return _lazy_impl().format_to_local_phone(phone)  # type: ignore
    except Exception:
        return None

def set_hotspot_user_profile(username: str, new_profile_name: str):
    try:
        return _lazy_impl().set_hotspot_user_profile(username, new_profile_name)  # type: ignore
    except Exception as e:
        return False, f"lazy-wrapper error: {e}"
