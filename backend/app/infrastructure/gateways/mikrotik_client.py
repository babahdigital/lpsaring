# backend/app/infrastructure/gateways/mikrotik_client.py
# VERSI FINAL: Logika penanganan respons dari .add() dibuat lebih tangguh.

import os
import time
import logging
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any
import routeros_api
import routeros_api.exceptions

logger = logging.getLogger(__name__)

MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))
MIKROTIK_USE_SSL = os.environ.get('MIKROTIK_USE_SSL', 'False').lower() == 'true'
MIKROTIK_SSL_VERIFY = os.environ.get('MIKROTIK_SSL_VERIFY', 'False').lower() == 'true'
MIKROTIK_PLAIN_TEXT_LOGIN = os.environ.get('MIKROTIK_PLAIN_TEXT_LOGIN', 'True').lower() == 'true'
_connection_pool = None

def init_mikrotik_pool():
    global _connection_pool
    if _connection_pool is not None: return True
    if not all([MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD]):
        logger.error("Konfigurasi MikroTik tidak lengkap")
        return False
    try:
        _connection_pool = routeros_api.RouterOsApiPool(
            MIKROTIK_HOST, username=MIKROTIK_USERNAME, password=MIKROTIK_PASSWORD,
            port=MIKROTIK_PORT, use_ssl=MIKROTIK_USE_SSL, ssl_verify=MIKROTIK_SSL_VERIFY,
            plaintext_login=MIKROTIK_PLAIN_TEXT_LOGIN
        )
        logger.info(f"Pool koneksi MikroTik berhasil diinisialisasi untuk {MIKROTIK_HOST}")
        return True
    except Exception as e:
        logger.error(f"Gagal menginisialisasi pool koneksi: {e}", exc_info=True)
        return False

@contextmanager
def get_mikrotik_connection() -> Optional[Any]:
    api_instance = None
    try:
        if _connection_pool is None:
            if not init_mikrotik_pool():
                logger.error("Pool koneksi tidak tersedia")
                yield None
                return
        api_instance = _connection_pool.get_api()
        yield api_instance
    except Exception as e:
        logger.error(f"Error mendapatkan koneksi: {e}", exc_info=True)
        yield None
    finally:
        if api_instance and _connection_pool:
            try: _connection_pool.return_api(api_instance)
            except: pass

def _get_hotspot_profiles(api_connection: Any) -> Tuple[bool, List[Dict[str, Any]], str]:
    try:
        profiles = api_connection.get_resource('/ip/hotspot/user/profile').get()
        return True, profiles, "Sukses"
    except Exception as e:
        return False, [], str(e)

def _is_profile_valid(api_connection: Any, requested_profile_name: str) -> Tuple[bool, str]:
    if not requested_profile_name:
        return False, "Nama profil Mikrotik tidak boleh kosong."
    success, profiles, message = _get_hotspot_profiles(api_connection)
    if not success: return False, f"Gagal memverifikasi profil: {message}"
    for p in profiles:
        if p.get('name', '').lower() == requested_profile_name.lower():
            return True, p.get('name')
    return False, f"Profil '{requested_profile_name}' tidak ditemukan di Mikrotik."

def activate_or_update_hotspot_user(
    api_connection: Any, user_mikrotik_username: str, mikrotik_profile_name: str,
    hotspot_password: str, comment: str = "", limit_bytes_total: Optional[int] = None,
    session_timeout_seconds: Optional[int] = None, force_update_profile: bool = False,
    server: Optional[str] = 'all', max_retries: int = 3
) -> Tuple[bool, str]:
    is_valid_profile, profile_result = _is_profile_valid(api_connection, mikrotik_profile_name)
    if not is_valid_profile:
        return False, profile_result
    
    user_resource = api_connection.get_resource('/ip/hotspot/user')

    for attempt in range(1, max_retries + 1):
        try:
            users = user_resource.get(name=user_mikrotik_username)
            user_entry = users[0] if users else None

            if user_entry:
                user_id = user_entry.get('.id') or user_entry.get('id')
                if not user_id:
                    logger.error(f"User {user_mikrotik_username} ditemukan tapi tidak punya ID. Data: {user_entry}")
                    return False, f"Gagal update, user {user_mikrotik_username} tidak memiliki ID."

                update_data = {'.id': user_id, 'password': hotspot_password, 'comment': comment}
                if force_update_profile or user_entry.get('profile') != profile_result:
                    update_data['profile'] = profile_result
                if server:
                    update_data['server'] = server
                
                user_resource.set(**update_data)
                
                if limit_bytes_total is not None:
                    user_resource.set(**{'.id': user_id, 'limit-bytes-total': str(limit_bytes_total)})
                if session_timeout_seconds is not None:
                    user_resource.set(**{'.id': user_id, 'limit-uptime': str(session_timeout_seconds)})
                
                return True, f"User {user_mikrotik_username} berhasil diperbarui."
            else:
                add_data = {
                    'name': user_mikrotik_username, 
                    'password': hotspot_password, 
                    'profile': profile_result, 
                    'server': server or 'all', 
                    'comment': comment
                }
                new_user_info = user_resource.add(**add_data)
                
                # --- [PERBAIKAN FINAL] ---
                # Logika baru yang lebih aman untuk menangani berbagai kemungkinan respons
                user_id = None
                if isinstance(new_user_info, list) and new_user_info:
                    # Jika hasilnya list, ambil elemen pertama (yang seharusnya dict)
                    user_id = new_user_info[0].get('.id')
                elif isinstance(new_user_info, dict):
                    # Jika hasilnya sudah dict
                    user_id = new_user_info.get('.id')
                
                if not user_id:
                    logger.error(f"Mikrotik 'add' tidak mengembalikan ID untuk user {user_mikrotik_username}. Respons: {new_user_info}")
                    time.sleep(0.5)
                    continue

                if limit_bytes_total is not None:
                    user_resource.set(**{'.id': user_id, 'limit-bytes-total': str(limit_bytes_total)})
                if session_timeout_seconds is not None:
                    user_resource.set(**{'.id': user_id, 'limit-uptime': str(session_timeout_seconds)})

                return True, f"User {user_mikrotik_username} berhasil dibuat."

        except routeros_api.exceptions.RouterOsApiError as e:
            raw_message = getattr(e, 'original_message', str(e))
            error_msg_str = str(raw_message.decode('utf-8', errors='ignore') if isinstance(raw_message, bytes) else raw_message)
            
            if "already have user with this name" in error_msg_str:
                logger.warning(f"Terjadi konflik (user sudah ada) saat mencoba membuat {user_mikrotik_username}. Mencoba lagi (Percobaan {attempt})...")
                time.sleep(0.5 * attempt)
                continue
            else:
                logger.error(f"Error RouterOS API pada percobaan {attempt}: {error_msg_str}")
                time.sleep(0.5 * attempt)
        
        except Exception as e:
            logger.error(f"Error tak terduga pada percobaan {attempt}: {e}", exc_info=True)
            time.sleep(1 * attempt)
            
    return False, f"Gagal memproses user {user_mikrotik_username} setelah {max_retries} percobaan."

def delete_hotspot_user(api_connection: Any, username: str, max_retries: int = 3) -> Tuple[bool, str]:
    if not username: 
        return False, "Username tidak valid"
    
    logger.info(f"[MIKROTIK DELETE] Memulai proses hapus untuk user: {username}")
    
    try:
        active_resource = api_connection.get_resource('/ip/hotspot/active')
        active_sessions = active_resource.get(user=username)
        if active_sessions:
            session_id = active_sessions[0].get('.id')
            if session_id:
                active_resource.remove(id=session_id)
                logger.info(f"[MIKROTIK DELETE] Sesi aktif untuk {username} berhasil dihapus.")
    except Exception as e:
        logger.warning(f"[MIKROTIK DELETE] Gagal menghapus sesi aktif untuk {username}: {e}", exc_info=True)

    user_resource = api_connection.get_resource('/ip/hotspot/user')
    for attempt in range(max_retries):
        try:
            users = user_resource.get(name=username)
            if not users:
                return True, f"User {username} tidak ditemukan (dianggap terhapus)."
            
            user_id = users[0].get('.id')
            if not user_id:
                return False, f"Gagal menghapus {username}: entri user ditemukan di Mikrotik tanpa ID."
            
            user_resource.remove(id=user_id)
            return True, f"User {username} berhasil dihapus."
        except Exception as e:
            logger.error(f"[MIKROTIK DELETE] Error pada percobaan hapus user {username}: {e}", exc_info=True)
            time.sleep(0.5 * (attempt + 1))

    return False, f"Gagal menghapus user {username} dari Mikrotik setelah beberapa percobaan."

def set_hotspot_user_profile(api_connection: Any, username_or_id: str, new_profile_name: str) -> Tuple[bool, str]:
    is_valid, profile_name = _is_profile_valid(api_connection, new_profile_name)
    if not is_valid: return False, profile_name
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        users = user_resource.get(name=username_or_id) or user_resource.get(id=username_or_id)
        if not users: return False, f"User {username_or_id} tidak ditemukan."
        
        user_id = users[0].get('.id')
        if not user_id: return False, f"Gagal mengubah profil, user {username_or_id} tidak memiliki ID."

        user_resource.set(id=user_id, profile=profile_name)
        return True, f"Profil berhasil diubah ke {profile_name}."
    except Exception as e: return False, str(e)

def get_hotspot_user_details(api_connection: Any, username: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        users = api_connection.get_resource('/ip/hotspot/user').get(name=username)
        return (True, users[0], "Sukses") if users else (True, None, "User tidak ditemukan")
    except Exception as e:
        return False, None, str(e)