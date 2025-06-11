# backend/app/infrastructure/gateways/mikrotik_client.py
# VERSI FINAL: Memperbaiki masalah inisialisasi RouterOsApiPool,
# Menambahkan force_update_profile, logging yang lebih baik, dan penanganan parameter opsional.
# PERBAIKAN FINAL: Menambahkan pengecekan '.id' untuk mencegah KeyError.
# PERBAIKAN V3: Logika yang lebih tangguh untuk menangani user yang ada tanpa '.id'
# PERBAIKAN V4 (Fokus Approve): Memastikan nilai 0 untuk limit/timeout tetap dikirim ke Mikrotik.

import os
import time
import re
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any
from flask import current_app # Import current_app di sini
import logging

# Coba import routeros_api, jika gagal, berikan placeholder
try:
    import routeros_api
    ROUTEROS_API_AVAILABLE = True
except ImportError:
    ROUTEROS_API_AVAILABLE = False
    print("WARNING: routeros_api is not installed. Mikrotik functions will be dummy.")

# Global logger yang bisa diakses di mana saja
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Konfigurasi Mikrotik dari environment variables
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))
MIKROTIK_USE_SSL = os.environ.get('MIKROTIK_USE_SSL', 'False').lower() == 'true'
MIKROTIK_SSL_VERIFY = os.environ.get('MIKROTIK_SSL_VERIFY', 'False').lower() == 'true'
MIKROTIK_PLAIN_TEXT_LOGIN = os.environ.get('MIKROTIK_PLAIN_TEXT_LOGIN', 'True').lower() == 'true'

_connection_pool: Optional[routeros_api.RouterOsApiPool] = None

def init_mikrotik_pool() -> bool:
    """Menginisialisasi pool koneksi MikroTik. Dipanggil sekali."""
    global _connection_pool
    
    if _connection_pool is not None:
        logger.debug("Pool koneksi MikroTik sudah diinisialisasi.")
        return True

    if not (MIKROTIK_HOST and MIKROTIK_USERNAME and MIKROTIK_PASSWORD):
        logger.error("Konfigurasi MikroTik (MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD) tidak lengkap.")
        _connection_pool = None
        return False
    
    if not ROUTEROS_API_AVAILABLE:
        logger.error("routeros_api library not installed. Cannot initialize Mikrotik connection pool.")
        _connection_pool = None
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
        logger.info(f"Pool koneksi MikroTik berhasil diinisialisasi untuk {MIKROTIK_HOST}:{MIKROTIK_PORT}.")
        return True
    except Exception as e:
        logger.error(f"Gagal menginisialisasi pool koneksi MikroTik: {e}", exc_info=True)
        _connection_pool = None
        return False

@contextmanager
def get_mikrotik_connection() -> Optional[Any]:
    """Menyediakan koneksi API MikroTik dari pool menggunakan context manager."""
    api_instance: Optional[Any] = None 
    try:
        if _connection_pool is None:
            if not init_mikrotik_pool():
                logger.error("Pool koneksi MikroTik tidak tersedia atau gagal diinisialisasi. Tidak bisa mendapatkan koneksi API.")
                yield None
                return

        api_instance = _connection_pool.get_api()
        logger.debug(f"[MikroTik Client] Koneksi API MikroTik berhasil didapatkan dari pool: {MIKROTIK_HOST}")
        yield api_instance
    except (routeros_api.exceptions.RouterOsApiError, routeros_api.exceptions.RouterOsApiConnectionError, routeros_api.exceptions.RouterOsApiCommunicationError) as e:
        logger.error(f"RouterOS API Error saat mendapatkan koneksi dari pool: {e}", exc_info=True)
        yield None
    except Exception as e:
        logger.error(f"Error tidak terduga saat mendapatkan koneksi MikroTik dari pool: {e}", exc_info=True)
        yield None
    finally:
        if api_instance and _connection_pool:
            logger.debug("Koneksi MikroTik API sedang dikembalikan ke pool.")


def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """
    Memformat nomor telepon internasional menjadi format lokal (misal: +628... menjadi 08...).
    """
    if not phone_number: return None
    try:
        cleaned_number = re.sub(r'[\s\-()+]', '', str(phone_number)).lstrip('+')
        if cleaned_number.startswith('628') and len(cleaned_number) >= 10 :
            return '0' + cleaned_number[2:]
        if cleaned_number.startswith('08') and len(cleaned_number) >= 9:
            return cleaned_number
        if cleaned_number.startswith('8') and len(cleaned_number) >= 9:
            return '0' + cleaned_number
        logger.warning(f"Tidak dapat memformat nomor telepon '{phone_number}' ke format lokal 08... Mengembalikan nomor asli yang dibersihkan: '{cleaned_number}'.")
        return cleaned_number
    except Exception as e:
        logger.error(f"Error dalam format_to_local_phone untuk '{phone_number}': {e}", exc_info=True)
        return None

# --- FUNGSI AKSI HOTSPOT DENGAN PERBAIKAN LOGIKA ---
def activate_or_update_hotspot_user(
    api_connection: Any,
    user_mikrotik_username: str,
    mikrotik_profile_name: str,
    hotspot_password: str,
    comment: str = "",
    limit_bytes_total: Optional[int] = None,
    session_timeout_seconds: Optional[int] = None,
    force_update_profile: bool = False
) -> Tuple[bool, str]:
    """
    Mengaktifkan atau memperbarui pengguna hotspot di MikroTik.
    Memastikan nilai limit 0 tetap dikirim ke Mikrotik.
    """
    try:
        user_hotspot_resource = api_connection.get_resource('/ip/hotspot/user')
        
        # Cek konfigurasi pengiriman limit dari Flask app context
        send_limit_bytes_total_cfg = False
        send_session_timeout_cfg = False
        try:
            send_limit_bytes_total_cfg = current_app.config.get('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', False)
            send_session_timeout_cfg = current_app.config.get('MIKROTIK_SEND_SESSION_TIMEOUT', False)
        except RuntimeError:
            logger.warning("Di luar app context, tidak bisa akses config. Menggunakan default False untuk pengiriman limit.")

        # Persiapan data untuk Mikrotik API
        base_user_data = {
            'name': user_mikrotik_username,
            'password': hotspot_password,
            'profile': mikrotik_profile_name,
            'server': 'all',
            'comment': comment,
        }
        
        # --- PERBAIKAN UTAMA: Gunakan '>= 0' untuk mengirim nilai 0 ---
        # Ini memastikan bahwa jika kuota adalah 0, perintah untuk mengaturnya menjadi 0 tetap dikirim.
        if send_limit_bytes_total_cfg and limit_bytes_total is not None and limit_bytes_total >= 0:
            base_user_data['limit-bytes-total'] = str(limit_bytes_total)
            logger.debug(f"Menambahkan 'limit-bytes-total': {limit_bytes_total} ke payload Mikrotik untuk {user_mikrotik_username}.")
        
        if send_session_timeout_cfg and session_timeout_seconds is not None and session_timeout_seconds >= 0:
            base_user_data['session-timeout'] = str(session_timeout_seconds)
            logger.debug(f"Menambahkan 'session-timeout': {session_timeout_seconds} ke payload Mikrotik untuk {user_mikrotik_username}.")

        # Cek apakah pengguna sudah ada
        existing_users_list: list[dict[str, Any]] = user_hotspot_resource.get(name=user_mikrotik_username)
        
        if existing_users_list:
            # Pengguna ditemukan, lakukan UPDATE (SET)
            user_entry = existing_users_list[0]
            mikrotik_internal_id = user_entry.get('.id') or user_entry.get('id')
            
            if not mikrotik_internal_id:
                error_msg = f"User '{user_mikrotik_username}' ditemukan tetapi tidak memiliki ID valid. Data: {user_entry}"
                logger.error(error_msg)
                return False, "User ditemukan di MikroTik tetapi data ID-nya tidak valid."

            logger.info(f"User '{user_mikrotik_username}' ditemukan (ID: {mikrotik_internal_id}). Memperbarui...")
            
            # Gabungkan data dasar dengan ID untuk operasi SET
            user_data_to_set = {**base_user_data, '.id': mikrotik_internal_id}
            
            if force_update_profile or user_entry.get('profile') != mikrotik_profile_name:
                user_data_to_set['profile'] = mikrotik_profile_name
                logger.info(f"Memperbarui profil untuk {user_mikrotik_username} ke {mikrotik_profile_name}.")

            user_hotspot_resource.set(**user_data_to_set)

            msg = f"User MikroTik '{user_mikrotik_username}' berhasil diperbarui."
            logger.info(msg)
            return True, msg
        else:
            # Pengguna tidak ditemukan, lakukan CREATE (ADD)
            logger.info(f"User '{user_mikrotik_username}' tidak ditemukan. Mencoba membuat baru...")

            user_hotspot_resource.add(**base_user_data)
            
            msg = f"User MikroTik baru '{user_mikrotik_username}' berhasil dibuat."
            logger.info(msg)
            return True, msg

    except routeros_api.exceptions.RouterOsApiError as e:
        ctx = f"untuk user '{user_mikrotik_username}'"
        msg = f"Gagal aksi MikroTik {ctx}. Error API: {e}. Detail: {getattr(e, 'original_message', '')}."
        logger.error(msg, exc_info=False)
        return False, f"Error API MikroTik: {getattr(e, 'original_message', str(e))}"
    except Exception as e:
        ctx = f"untuk user '{user_mikrotik_username}'"
        msg = f"Error tidak terduga selama aksi MikroTik {ctx}: {e}"
        logger.error(msg, exc_info=True)
        return False, f"Error internal server saat operasi MikroTik: {e}"


def update_mikrotik_user_password(
    api_connection: Any,
    username_mikrotik_fmt: str,
    new_password: str
) -> Tuple[bool, str]:
    """Memperbarui password user hotspot di Mikrotik."""
    if not username_mikrotik_fmt: msg = "Username Mikrotik tidak boleh kosong."; logger.error(msg); return False, msg
    if not new_password: msg = "Password baru tidak boleh kosong."; logger.error(msg); return False, msg

    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        logger.debug(f"Mencari user '{username_mikrotik_fmt}' untuk update password...")
        existing_user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)

        if existing_user_list:
            user_entry = existing_user_list[0]
            user_mikrotik_id = user_entry.get('.id') or user_entry.get('id')
            if not user_mikrotik_id:
                return False, f"User '{username_mikrotik_fmt}' ditemukan tetapi tidak memiliki ID yang valid."
                
            logger.info(f"User '{username_mikrotik_fmt}' ditemukan (ID: {user_mikrotik_id}). Memperbarui password...")
            user_resource.set(id=user_mikrotik_id, password=new_password)
            msg = f"Password MikroTik '{username_mikrotik_fmt}' berhasil diperbarui."
            logger.info(msg); return True, msg
        else:
            msg = f"User '{username_mikrotik_fmt}' tidak ditemukan. Password tidak diperbarui."
            logger.warning(msg); return False, msg

    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API Mikrotik saat update password user {username_mikrotik_fmt}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False); return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat update password Mikrotik user {username_mikrotik_fmt}: {e}"
        logger.error(msg, exc_info=True); return False, str(e)


def get_hotspot_user_usage(
    api_connection: Any,
    username: str
) -> Tuple[bool, Optional[Dict[str, int]], str]:
    """Mengambil data penggunaan (bytes-in, bytes-out) user dari Mikrotik."""
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, None, f"Username '{username}' tidak valid."

    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
        if user_list:
            data = user_list[0]; bytes_in = int(data.get('bytes-in', 0) or 0); bytes_out = int(data.get('bytes-out', 0) or 0)
            logger.debug(f"Usage data found for '{username_mikrotik_fmt}': In={bytes_in}, Out={bytes_out}")
            return True, {'bytes_in': bytes_in, 'bytes_out': bytes_out}, "Sukses"
        else: logger.warning(f"User '{username_mikrotik_fmt}' tidak ditemukan saat get_usage."); return True, None, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API Mikrotik saat get_usage user {username_mikrotik_fmt}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False); return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat get_usage Mikrotik user {username_mikrotik_fmt}: {e}"
        logger.error(msg, exc_info=True); return False, str(e)


def set_hotspot_user_limit(
    api_connection: Any,
    username: str,
    limit_bytes_total: int
) -> Tuple[bool, str]:
    """Menetapkan limit-bytes-total untuk user hotspot Mikrotik."""
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, f"Username '{username}' tidak valid."
    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
        if user_list:
            user_entry = user_list[0]
            user_id = user_entry.get('.id') or user_entry.get('id')
            if not user_id:
                return False, f"User '{username_mikrotik_fmt}' ditemukan tetapi tidak memiliki ID yang valid."
            
            user_resource.set(id=user_id, **{'limit-bytes-total': str(limit_bytes_total)})
            logger.info(f"Limit bytes '{username_mikrotik_fmt}' diatur ke {limit_bytes_total}."); return True, "Sukses"
        else: logger.warning(f"User '{username_mikrotik_fmt}' tidak ditemukan saat set_limit."); return False, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API Mikrotik saat set_limit user {username_mikrotik_fmt}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False); return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat set_limit Mikrotik user {username_mikrotik_fmt}: {e}"
        logger.error(msg, exc_info=True); return False, str(e)


def set_hotspot_user_profile(
    api_connection: Any,
    username_or_id: str,
    new_profile_name: str
) -> Tuple[bool, str]:
    """Mengubah profil hotspot untuk user Mikrotik berdasarkan username atau ID."""
    if not username_or_id: return False, "Username atau ID Mikrotik tidak boleh kosong."
    if not new_profile_name: return False, "Nama profil baru tidak boleh kosong."

    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        
        users = user_resource.get(name=username_or_id)
        
        if not users:
            try: users = user_resource.get(id=username_or_id)
            except Exception: pass

        if not users:
            msg = f"User hotspot '{username_or_id}' tidak ditemukan di Mikrotik."
            logger.warning(msg); return False, msg

        user_entry = users[0]
        user_mikrotik_id = user_entry.get('.id') or user_entry.get('id')
        if not user_mikrotik_id:
            return False, f"User '{username_or_id}' ditemukan tetapi tidak memiliki ID yang valid."

        current_profile = user_entry.get('profile')

        if current_profile == new_profile_name:
            msg = f"User '{username_or_id}' sudah berada di profil '{new_profile_name}'. Tidak perlu update."
            logger.info(msg); return True, msg
        
        logger.info(f"Mengubah profil user '{username_or_id}' dari '{current_profile or 'N/A'}' ke '{new_profile_name}'...")
        user_resource.set(id=user_mikrotik_id, profile=new_profile_name)
        
        msg = f"Profil user '{username_or_id}' berhasil diubah ke '{new_profile_name}'."
        logger.info(msg); return True, msg

    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API Mikrotik saat mengubah profil user {username_or_id}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False); return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat mengubah profil Mikrotik user {username_or_id}: {e}"
        logger.error(msg, exc_info=True); return False, str(e)

def add_mikrotik_hotspot_user_profile(
    api_connection: Any,
    profile_name: str,
    rate_limit: Optional[str] = None,
    shared_users: Optional[int] = None,
    comment: Optional[str] = None
) -> Tuple[bool, str]:
    """Menambahkan profil hotspot baru di Mikrotik."""
    if not api_connection: return False, "API connection is not established."
    if not ROUTEROS_API_AVAILABLE: return False, "routeros_api library not installed."
    
    attrs = {}
    try:
        profiles = api_connection.get_resource('/ip/hotspot/user/profile')

        if profiles.get(name=profile_name):
            return False, f"Profile '{profile_name}' already exists in Mikrotik."

        attrs = {'name': profile_name}
        if rate_limit: attrs['rate-limit'] = rate_limit
        if shared_users is not None and shared_users > 0: attrs['shared-users'] = str(shared_users)
        if comment: attrs['comment'] = comment

        profiles.add(**attrs)
        logger.info(f"Hotspot user profile '{profile_name}' added to Mikrotik.")
        return True, f"Profile '{profile_name}' added successfully."

    except routeros_api.exceptions.RouterOsApiError as e:
        error_message = f"Mikrotik API error adding profile '{profile_name}'. Payload: {attrs}. Error: {e.original_message or e}"
        logger.error(error_message, exc_info=True)
        return False, error_message
    except Exception as e:
        error_message = f"Unexpected error adding Mikrotik profile '{profile_name}': {e}"
        logger.error(error_message, exc_info=True)
        return False, error_message

def delete_hotspot_user(
    api_connection: Any,
    username: str
) -> Tuple[bool, str]:
    """Menghapus user hotspot dari Mikrotik dan melakukan verifikasi penghapusan."""
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, f"Username '{username}' tidak valid."

    try:
        user_resource = api_connection.get_resource('/ip/hotspot/user')
        logger.debug(f"Mencari user '{username_mikrotik_fmt}' untuk dihapus...")
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)

        if user_list:
            user_entry = user_list[0]
            user_id = user_entry.get('.id') or user_entry.get('id')
            if not user_id:
                return False, f"Gagal menghapus. User '{username_mikrotik_fmt}' ditemukan tetapi tidak memiliki ID yang valid."

            logger.info(f"User '{username_mikrotik_fmt}' ditemukan (ID: {user_id}). Mencoba menghapus...")
            try:
                 user_resource.remove(id=user_id)
                 logger.info(f"Perintah remove untuk user '{username_mikrotik_fmt}' (ID: {user_id}) telah dikirim.")
                 time.sleep(0.5)
                 logger.debug(f"Memverifikasi penghapusan user '{username_mikrotik_fmt}'...")
                 verify_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
                 if not verify_list:
                     logger.info(f"Verifikasi SUKSES: User '{username_mikrotik_fmt}' tidak lagi ditemukan di Mikrotik.")
                     return True, "Sukses dihapus dari Mikrotik."
                 else:
                     logger.error(f"Verifikasi GAGAL: User '{username_mikrotik_fmt}' masih ditemukan di Mikrotik setelah perintah remove.")
                     return False, f"Gagal menghapus user '{username_mikrotik_fmt}' dari Mikrotik (masih terdeteksi)."
            except routeros_api.exceptions.RouterOsApiError as e_remove:
                 msg = f"Error API Mikrotik saat remove user {username_mikrotik_fmt}: {getattr(e_remove, 'original_message', str(e_remove))}"
                 logger.error(msg, exc_info=False)
                 return False, msg
        else:
            logger.info(f"User hotspot '{username_mikrotik_fmt}' tidak ditemukan di Mikrotik (dianggap sudah terhapus).")
            return True, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except routeros_api.exceptions.RouterOsApiError as e:
        msg = f"Error API Mikrotik saat proses delete user {username_mikrotik_fmt}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False); return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat delete user Mikrotik {username_mikrotik_fmt}: {e}"
        logger.error(msg, exc_info=True); return False, str(e)