# backend/app/infrastructure/gateways/mikrotik_client.py
# VERSI FINAL: Memisahkan perintah SET untuk menangani RouterOS yang tidak mendukung semua parameter.

import os
import time
import re
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any
from flask import current_app
import logging

try:
    import routeros_api
    ROUTEROS_API_AVAILABLE = True
except ImportError:
    ROUTEROS_API_AVAILABLE = False
    print("WARNING: routeros_api is not installed. Mikrotik functions will be dummy.")

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))
MIKROTIK_USE_SSL = os.environ.get('MIKROTIK_USE_SSL', 'False').lower() == 'true'
MIKROTIK_SSL_VERIFY = os.environ.get('MIKROTIK_SSL_VERIFY', 'False').lower() == 'true'
MIKROTIK_PLAIN_TEXT_LOGIN = os.environ.get('MIKROTIK_PLAIN_TEXT_LOGIN', 'True').lower() == 'true'

_connection_pool: Optional[routeros_api.RouterOsApiPool] = None

def init_mikrotik_pool() -> bool:
    global _connection_pool
    if _connection_pool is not None:
        return True
    if not (MIKROTIK_HOST and MIKROTIK_USERNAME and MIKROTIK_PASSWORD):
        logger.error("Konfigurasi MikroTik tidak lengkap.")
        return False
    if not ROUTEROS_API_AVAILABLE:
        logger.error("routeros_api library not installed.")
        return False
    try:
        _connection_pool = routeros_api.RouterOsApiPool(
            MIKROTIK_HOST, username=MIKROTIK_USERNAME, password=MIKROTIK_PASSWORD,
            port=MIKROTIK_PORT, use_ssl=MIKROTIK_USE_SSL, ssl_verify=MIKROTIK_SSL_VERIFY,
            plaintext_login=MIKROTIK_PLAIN_TEXT_LOGIN
        )
        logger.info(f"Pool koneksi MikroTik berhasil diinisialisasi untuk {MIKROTIK_HOST}:{MIKROTIK_PORT}.")
        return True
    except Exception as e:
        logger.error(f"Gagal menginisialisasi pool koneksi MikroTik: {e}", exc_info=True)
        return False

@contextmanager
def get_mikrotik_connection() -> Optional[Any]:
    api_instance: Optional[Any] = None
    try:
        if not init_mikrotik_pool():
            yield None
            return
        api_instance = _connection_pool.get_api()
        yield api_instance
    except Exception as e:
        logger.error(f"Error mendapatkan koneksi MikroTik: {e}", exc_info=True)
        yield None
    finally:
        if api_instance and _connection_pool:
            _connection_pool.put_api(api_instance)

def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    if not phone_number: return None
    try:
        cleaned_number = re.sub(r'[\s\-()+]', '', str(phone_number)).lstrip('+')
        if cleaned_number.startswith('628'): return '0' + cleaned_number[2:]
        if cleaned_number.startswith('08'): return cleaned_number
        if cleaned_number.startswith('8'): return '0' + cleaned_number
        return cleaned_number
    except Exception:
        return None

def _execute_set_command(api_resource, user_id, parameter, value, parameter_name_log):
    """Fungsi helper untuk menjalankan satu perintah SET dan menangani error."""
    try:
        api_resource.set(**{'.id': user_id, parameter: str(value)})
        logger.info(f"SET SUKSES untuk user ID {user_id}: {parameter_name_log} diatur ke {value}.")
        return True
    except routeros_api.exceptions.RouterOsApiError as e:
        if 'unknown parameter' in str(e.original_message):
            logger.warning(f"SET PERINGATAN untuk user ID {user_id}: Parameter '{parameter_name_log}' tidak didukung oleh RouterOS versi ini. Melewati.")
            return True # Anggap sukses agar tidak menghentikan operasi lain
        else:
            logger.error(f"SET GAGAL untuk user ID {user_id} saat mengatur {parameter_name_log}: {e.original_message}", exc_info=False)
            return False
    except Exception as e:
        logger.error(f"SET GAGAL (error tidak terduga) untuk user ID {user_id} saat mengatur {parameter_name_log}: {e}", exc_info=True)
        return False

def activate_or_update_hotspot_user(
    api_connection: Any, user_mikrotik_username: str, mikrotik_profile_name: str,
    hotspot_password: str, comment: str = "", limit_bytes_total: Optional[int] = None,
    session_timeout_seconds: Optional[int] = None, force_update_profile: bool = False
) -> Tuple[bool, str]:
    try:
        user_hotspot_resource = api_connection.get_resource('/ip/hotspot/user')
        send_limit_cfg = current_app.config.get('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', False)
        send_timeout_cfg = current_app.config.get('MIKROTIK_SEND_SESSION_TIMEOUT', False)

        existing_users_list = user_hotspot_resource.get(name=user_mikrotik_username)
        
        if not existing_users_list:
            logger.info(f"User '{user_mikrotik_username}' tidak ditemukan. Membuat baru...")
            add_data = {'name': user_mikrotik_username, 'password': hotspot_password, 'profile': mikrotik_profile_name, 'server': 'all', 'comment': comment}
            user_hotspot_resource.add(**add_data)
            time.sleep(0.5)
            existing_users_list = user_hotspot_resource.get(name=user_mikrotik_username)
            if not existing_users_list:
                return False, f"Gagal membuat dan mengambil ulang user '{user_mikrotik_username}'."
        
        user_entry = existing_users_list[0]
        mikrotik_internal_id = user_entry.get('.id')
        if not mikrotik_internal_id:
            return False, f"User '{user_mikrotik_username}' tidak memiliki ID valid di MikroTik."

        logger.info(f"Memproses user '{user_mikrotik_username}' (ID: {mikrotik_internal_id})...")
        
        # Selalu update password & comment
        _execute_set_command(user_hotspot_resource, mikrotik_internal_id, 'password', hotspot_password, 'password')
        _execute_set_command(user_hotspot_resource, mikrotik_internal_id, 'comment', comment, 'comment')
        
        # Update profil jika perlu
        if force_update_profile or user_entry.get('profile') != mikrotik_profile_name:
             _execute_set_command(user_hotspot_resource, mikrotik_internal_id, 'profile', mikrotik_profile_name, 'profile')

        # Update limit kuota jika diaktifkan dan nilainya ada
        if send_limit_cfg and limit_bytes_total is not None and limit_bytes_total >= 0:
            _execute_set_command(user_hotspot_resource, mikrotik_internal_id, 'limit-bytes-total', limit_bytes_total, 'limit-bytes-total')

        # Update timeout sesi jika diaktifkan dan nilainya ada
        if send_timeout_cfg and session_timeout_seconds is not None and session_timeout_seconds >= 0:
            _execute_set_command(user_hotspot_resource, mikrotik_internal_id, 'session-timeout', session_timeout_seconds, 'session-timeout')
            
        return True, f"User '{user_mikrotik_username}' berhasil diproses."

    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API MikroTik: {getattr(e, 'original_message', str(e))}"
        logger.error(f"Aksi MikroTik untuk user '{user_mikrotik_username}' gagal: {msg}", exc_info=False)
        return False, msg
    except Exception as e:
        logger.error(f"Error tidak terduga saat aksi MikroTik untuk user '{user_mikrotik_username}': {e}", exc_info=True)
        return False, f"Error internal server: {e}"

# --- Fungsi lainnya tetap sama ---
def update_mikrotik_user_password(
    api_connection: Any,
    username_mikrotik_fmt: str,
    new_password: str
) -> Tuple[bool, str]:
    if not username_mikrotik_fmt: return False, "Username tidak valid."
    if not new_password: return False, "Password tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list = user_resource.get(name=username_mikrotik_fmt)
        if user_list:
            user_id = user_list[0].get('.id')
            if not user_id: return False, "User ditemukan tapi tidak punya ID."
            user_resource.set(id=user_id, password=new_password)
            return True, "Password berhasil diperbarui."
        return False, "User tidak ditemukan."
    except Exception as e:
        logger.error(f"Gagal update password Mikrotik untuk {username_mikrotik_fmt}: {e}", exc_info=True)
        return False, str(e)

def get_hotspot_user_details(
    api_connection: Any,
    username: str
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not username: return False, None, "Username tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list = user_resource.get(name=username)
        if user_list:
            return True, user_list[0], "Sukses"
        return True, None, "User tidak ditemukan."
    except Exception as e:
        logger.error(f"Gagal ambil detail user {username} dari Mikrotik: {e}", exc_info=True)
        return False, None, str(e)

def get_hotspot_user_usage(
    api_connection: Any,
    username: str
) -> Tuple[bool, Optional[Dict[str, int]], str]:
    success, details, msg = get_hotspot_user_details(api_connection, username)
    if not success:
        return False, None, msg
    if details:
        bytes_in = int(details.get('bytes-in', 0) or 0)
        bytes_out = int(details.get('bytes-out', 0) or 0)
        return True, {'bytes_in': bytes_in, 'bytes_out': bytes_out}, "Sukses"
    return True, None, "User tidak ditemukan."

def set_hotspot_user_limit(
    api_connection: Any,
    username: str,
    limit_bytes_total: int
) -> Tuple[bool, str]:
    if not username: return False, "Username tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list = user_resource.get(name=username)
        if user_list:
            user_id = user_list[0].get('.id')
            if not user_id: return False, "User ditemukan tapi tidak punya ID."
            return _execute_set_command(user_resource, user_id, 'limit-bytes-total', limit_bytes_total, 'limit-bytes-total')
        return False, "User tidak ditemukan."
    except Exception as e:
        logger.error(f"Gagal set limit untuk {username}: {e}", exc_info=True)
        return False, str(e)

def set_hotspot_user_profile(
    api_connection: Any,
    username_or_id: str,
    new_profile_name: str
) -> Tuple[bool, str]:
    if not username_or_id: return False, "Username/ID tidak valid."
    if not new_profile_name: return False, "Nama profil tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list = user_resource.get(name=username_or_id)
        if not user_list:
             user_list = user_resource.get(id=username_or_id)
        if user_list:
            user_id = user_list[0].get('.id')
            if not user_id: return False, "User ditemukan tapi tidak punya ID."
            return _execute_set_command(user_resource, user_id, 'profile', new_profile_name, 'profile')
        return False, "User tidak ditemukan."
    except Exception as e:
        logger.error(f"Gagal set profil untuk {username_or_id}: {e}", exc_info=True)
        return False, str(e)

def add_mikrotik_hotspot_user_profile(
    api_connection: Any,
    profile_name: str,
    rate_limit: Optional[str] = None,
    shared_users: Optional[int] = None,
    comment: Optional[str] = None
) -> Tuple[bool, str]:
    if not profile_name: return False, "Nama profil tidak valid."
    try:
        profiles = api_connection.get_resource('/ip/hotspot/user/profile')
        if profiles.get(name=profile_name):
            return True, "Profil sudah ada."
        add_data = {'name': profile_name}
        if rate_limit: add_data['rate-limit'] = rate_limit
        if shared_users: add_data['shared-users'] = str(shared_users)
        if comment: add_data['comment'] = comment
        profiles.add(**add_data)
        return True, "Profil berhasil ditambahkan."
    except Exception as e:
        logger.error(f"Gagal menambah profil {profile_name}: {e}", exc_info=True)
        return False, str(e)

def delete_hotspot_user(
    api_connection: Any,
    username: str
) -> Tuple[bool, str]:
    if not username: return False, "Username tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list = user_resource.get(name=username)
        if user_list:
            user_id = user_list[0].get('.id')
            if not user_id: return False, "User ditemukan tapi tidak punya ID."
            user_resource.remove(id=user_id)
            return True, "Perintah hapus terkirim."
        return True, "User tidak ditemukan (dianggap sudah terhapus)."
    except Exception as e:
        logger.error(f"Gagal hapus user {username}: {e}", exc_info=True)
        return False, str(e)