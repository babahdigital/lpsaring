# backend/app/infrastructure/gateways/mikrotik_client.py
# VERSI FINAL: Perbaikan menyeluruh, termasuk proses penghapusan user yang lebih robust.

import os
import time
import re
import logging
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any
from flask import current_app
import routeros_api
import routeros_api.exceptions

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Konfigurasi Mikrotik
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))
MIKROTIK_USE_SSL = os.environ.get('MIKROTIK_USE_SSL', 'False').lower() == 'true'
MIKROTIK_SSL_VERIFY = os.environ.get('MIKROTIK_SSL_VERIFY', 'False').lower() == 'true'
MIKROTIK_PLAIN_TEXT_LOGIN = os.environ.get('MIKROTIK_PLAIN_TEXT_LOGIN', 'True').lower() == 'true'

# Inisialisasi connection pool
_connection_pool = None

def init_mikrotik_pool():
    """Menginisialisasi pool koneksi MikroTik"""
    global _connection_pool
    if _connection_pool is not None:
        return True

    if not all([MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD]):
        logger.error("Konfigurasi MikroTik tidak lengkap")
        return False

    try:
        _connection_pool = routeros_api.RouterOsApiPool(
            MIKROTIK_HOST,
            username=MIKROTIK_USERNAME,
            password=MIKROTIK_PASSWORD,
            port=MIKROTIK_PORT,
            use_ssl=MIKROTIK_USE_SSL,
            ssl_verify=MIKROTIK_SSL_VERIFY,
            plaintext_login=MIKROTIK_PLAIN_TEXT_LOGIN
        )
        logger.info(f"Pool koneksi MikroTik berhasil diinisialisasi untuk {MIKROTIK_HOST}")
        return True
    except Exception as e:
        logger.error(f"Gagal menginisialisasi pool koneksi: {e}", exc_info=True)
        return False

@contextmanager
def get_mikrotik_connection() -> Optional[Any]:
    """Menyediakan koneksi API MikroTik dari pool"""
    api_instance = None
    try:
        if _connection_pool is None:
            if not init_mikrotik_pool():
                logger.error("Pool koneksi tidak tersedia")
                yield None
                return

        api_instance = _connection_pool.get_api()
        logger.debug(f"Koneksi API berhasil didapatkan: {MIKROTIK_HOST}")
        yield api_instance
    except Exception as e:
        logger.error(f"Error mendapatkan koneksi: {e}", exc_info=True)
        yield None
    finally:
        if api_instance and _connection_pool:
            try:
                _connection_pool.return_api(api_instance)
                logger.debug("Koneksi dikembalikan ke pool")
            except:
                pass

def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """Memformat nomor telepon ke format lokal"""
    if not phone_number:
        return None
        
    try:
        cleaned = re.sub(r'[\s\-()+]', '', str(phone_number)).lstrip('+')
        if cleaned.startswith('628') and len(cleaned) >= 10:
            return '0' + cleaned[2:]
        if cleaned.startswith('08') and len(cleaned) >= 9:
            return cleaned
        if cleaned.startswith('8') and len(cleaned) >= 9:
            return '0' + cleaned
        return cleaned
    except Exception as e:
        logger.error(f"Format error: {e}", exc_info=True)
        return None

def activate_or_update_hotspot_user(
    api_connection: Any,
    user_mikrotik_username: str,
    mikrotik_profile_name: str,
    hotspot_password: str,
    comment: str = "",
    limit_bytes_total: Optional[int] = None,
    session_timeout_seconds: Optional[int] = None,
    force_update_profile: bool = False,
    max_retries: int = 3
) -> Tuple[bool, str]:
    """
    Mengaktifkan/memperbarui user hotspot dengan penanganan error yang lebih robust
    untuk parameter opsional dan tipe data error.
    """
    try:
        send_limit_cfg = current_app.config.get('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', False)
        send_timeout_cfg = current_app.config.get('MIKROTIK_SEND_SESSION_TIMEOUT', False)
    except RuntimeError:
        send_limit_cfg = False
        send_timeout_cfg = False
    
    user_resource = api_connection.get_resource('/ip/hotspot/user')
    
    for attempt in range(1, max_retries + 1):
        try:
            users = user_resource.get(name=user_mikrotik_username)
            user_id = None

            if users:
                user_entry = users[0]
                user_id = user_entry.get('.id') or user_entry.get('id')
                if not user_id:
                    return False, f"User {user_mikrotik_username} ditemukan tapi tidak punya ID."

                update_data = {
                    '.id': user_id,
                    'password': hotspot_password,
                    'comment': comment
                }
                if force_update_profile or user_entry.get('profile') != mikrotik_profile_name:
                    update_data['profile'] = mikrotik_profile_name
                
                user_resource.set(**update_data)
                logger.info(f"User {user_mikrotik_username} berhasil diperbarui.")
            else:
                add_data = {
                    'name': user_mikrotik_username,
                    'password': hotspot_password,
                    'profile': mikrotik_profile_name,
                    'server': 'all',
                    'comment': comment
                }
                user_resource.add(**add_data)
                logger.info(f"User {user_mikrotik_username} berhasil dibuat. Melanjutkan ke update parameter opsional.")
                time.sleep(0.5)
                new_users = user_resource.get(name=user_mikrotik_username)
                if not new_users:
                    logger.warning(f"User {user_mikrotik_username} tidak ditemukan setelah dibuat, percobaan {attempt}/{max_retries}")
                    time.sleep(0.5 * attempt)
                    continue
                user_id = (new_users[0].get('.id') or new_users[0].get('id'))

            if not user_id:
                return False, f"Gagal mendapatkan ID untuk user {user_mikrotik_username} setelah dibuat/ditemukan."
            
            if send_limit_cfg and limit_bytes_total is not None and limit_bytes_total >= 0:
                try:
                    user_resource.set(**{'.id': user_id, 'limit-bytes-total': str(limit_bytes_total)})
                    logger.info(f"Set limit-bytes-total: {limit_bytes_total} untuk {user_mikrotik_username} berhasil.")
                except routeros_api.exceptions.RouterOsApiError as e_limit:
                    error_str = str(e_limit).lower()
                    if 'no such item' in error_str or 'unknown parameter' in error_str or 'no such argument' in error_str:
                        logger.warning(f"Parameter 'limit-bytes-total' tidak didukung di RouterOS ini, melewati. Pesan: {e_limit}")
                    else:
                        raise e_limit

            if send_timeout_cfg and session_timeout_seconds is not None and session_timeout_seconds > 0:
                try:
                    user_resource.set(**{'.id': user_id, 'session-timeout': str(session_timeout_seconds)})
                    logger.info(f"Set session-timeout: {session_timeout_seconds} untuk {user_mikrotik_username} berhasil.")
                except routeros_api.exceptions.RouterOsApiError as e_timeout:
                    error_str = str(e_timeout).lower()
                    if 'no such item' in error_str or 'unknown parameter' in error_str or 'no such argument' in error_str:
                        logger.warning(f"Parameter 'session-timeout' tidak didukung di RouterOS ini, melewati. Pesan: {e_timeout}")
                    else:
                        raise e_timeout
            
            return True, f"User {user_mikrotik_username} berhasil diproses."

        except routeros_api.exceptions.RouterOsApiError as e:
            raw_message = getattr(e, 'original_message', str(e))
            error_msg_str = ""
            if isinstance(raw_message, bytes):
                try:
                    error_msg_str = raw_message.decode('utf-8', errors='ignore')
                except:
                    error_msg_str = str(raw_message)
            elif isinstance(raw_message, tuple) and len(raw_message) > 1 and isinstance(raw_message[1], bytes):
                 error_msg_str = raw_message[1].decode('utf-8', errors='ignore')
            else:
                error_msg_str = str(raw_message)

            if 'already exists' in error_msg_str:
                logger.info(f"User {user_mikrotik_username} sudah ada, mencoba lagi untuk update.")
                time.sleep(0.5 * attempt)
                continue
            
            logger.error(f"API Error (attempt {attempt}/{max_retries}) untuk {user_mikrotik_username}: {error_msg_str}")
            time.sleep(0.5 * attempt)
            
        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt}/{max_retries}) pada user {user_mikrotik_username}: {str(e)}", exc_info=True)
            time.sleep(1 * attempt)
    
    return False, f"Gagal memproses user {user_mikrotik_username} setelah {max_retries} percobaan"

# --- FUNGSI DELETE DENGAN PENYEMPURNAAN ---
def delete_hotspot_user(
    api_connection: Any,
    username: str,
    max_retries: int = 3
) -> Tuple[bool, str]:
    """
    Menghapus user hotspot dengan robust:
    1. Hapus sesi aktif terlebih dahulu.
    2. Hapus data user.
    """
    if not username:
        return False, "Username tidak valid"
    
    # --- PENAMBAHAN LOGIKA: HAPUS SESI AKTIF TERLEBIH DAHULU ---
    try:
        active_resource = api_connection.get_resource('/ip/hotspot/active')
        active_sessions = active_resource.get(user=username)
        if active_sessions:
            active_id = active_sessions[0].get('.id') or active_sessions[0].get('id')
            if active_id:
                logger.info(f"Menemukan sesi aktif untuk {username} (ID: {active_id}). Menghapus sesi...")
                active_resource.remove(id=active_id)
                logger.info(f"Sesi aktif untuk {username} berhasil dihapus.")
    except Exception as e:
        logger.warning(f"Tidak dapat menghapus sesi aktif untuk {username} (mungkin tidak ada): {str(e)}")
    # --- AKHIR PENAMBAHAN LOGIKA ---

    user_resource = api_connection.get_resource('/ip/hotspot/user')
    for attempt in range(1, max_retries + 1):
        try:
            users = user_resource.get(name=username)
            if not users:
                return True, f"User {username} tidak ditemukan (dianggap sudah terhapus)"
            
            user_entry = users[0]
            user_id = user_entry.get('.id') or user_entry.get('id')
            if not user_id:
                return False, f"User {username} ditemukan tapi tidak punya ID"
            
            logger.info(f"Menghapus data user {username} (ID: {user_id})...")
            user_resource.remove(id=user_id)
            
            time.sleep(0.5)
            verify_users = user_resource.get(name=username)
            if not verify_users:
                return True, f"User {username} berhasil dihapus sepenuhnya"
            
            logger.warning(f"Verifikasi gagal, user {username} masih ada (attempt {attempt}/{max_retries})")
            time.sleep(1 * attempt)
            
        except routeros_api.exceptions.RouterOsApiError as e:
            raw_message = getattr(e, 'original_message', str(e))
            error_msg_str = str(raw_message.decode('utf-8', errors='ignore') if isinstance(raw_message, bytes) else raw_message)
            
            if 'no such item' in error_msg_str.lower():
                return True, f"User {username} tidak ditemukan saat mencoba menghapus (dianggap terhapus)"
                
            logger.error(f"API Error saat hapus user (attempt {attempt}/{max_retries}): {error_msg_str}")
            time.sleep(0.5 * attempt)
            
        except Exception as e:
            logger.error(f"Unexpected error saat hapus user (attempt {attempt}/{max_retries}): {str(e)}", exc_info=True)
            time.sleep(1 * attempt)
    
    return False, f"Gagal menghapus user {username} setelah {max_retries} percobaan"

def get_hotspot_user_details(
    api_connection: Any,
    username: str
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Mengambil detail user hotspot"""
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        users = user_resource.get(name=username)
        if users:
            return True, users[0], "Sukses"
        return True, None, "User tidak ditemukan"
    except Exception as e:
        logger.error(f"Gagal ambil detail: {e}", exc_info=True)
        return False, None, str(e)

def set_hotspot_user_limit(
    api_connection: Any,
    username: str,
    limit_bytes_total: int,
    max_retries: int = 2
) -> Tuple[bool, str]:
    """Mengatur limit bytes total user"""
    for attempt in range(1, max_retries + 1):
        try:
            user_resource = api_connection.get_resource('/ip/hotspot/user')
            users = user_resource.get(name=username)
            if not users:
                return False, f"User {username} tidak ditemukan"
            
            user_id = users[0].get('.id') or users[0].get('id')
            if not user_id:
                return False, f"User {username} tidak punya ID valid"
            
            user_resource.set(id=user_id, **{'limit-bytes-total': str(limit_bytes_total)})
            return True, f"Limit {limit_bytes_total} bytes berhasil diatur"
        except Exception as e:
            logger.error(f"Gagal set limit (attempt {attempt}): {e}")
            time.sleep(0.3 * attempt)
    
    return False, f"Gagal mengatur limit setelah {max_retries} percobaan"

def set_hotspot_user_profile(
    api_connection: Any,
    username_or_id: str,
    new_profile_name: str
) -> Tuple[bool, str]:
    """Mengubah profil user hotspot"""
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        users = user_resource.get(name=username_or_id)
        if not users:
            try:
                users = user_resource.get(id=username_or_id)
            except:
                pass
        
        if not users:
            return False, f"User {username_or_id} tidak ditemukan"
        
        user_id = users[0].get('.id') or users[0].get('id')
        if not user_id:
            return False, f"User {username_or_id} tidak punya ID valid"
        
        current_profile = users[0].get('profile', '')
        if current_profile == new_profile_name:
            return True, f"User sudah menggunakan profil {new_profile_name}"
        
        user_resource.set(id=user_id, profile=new_profile_name)
        return True, f"Profil berhasil diubah ke {new_profile_name}"
    except Exception as e:
        logger.error(f"Gagal ubah profil: {e}", exc_info=True)
        return False, str(e)