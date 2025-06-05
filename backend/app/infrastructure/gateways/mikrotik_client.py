# backend/app/infrastructure/gateways/mikrotik_client.py
# Versi Update: Perbaikan verifikasi pada delete_hotspot_user.

import routeros_api
from flask import current_app
from routeros_api.exceptions import RouterOsApiConnectionError, RouterOsApiCommunicationError, RouterOsApiError
from typing import Optional, Any, Tuple, Dict
import uuid
import re
import time # Import time untuk jeda kecil (opsional)

# Import model User dan instance db
from app.extensions import db
try:
    from app.infrastructure.db.models import User
except ImportError:
    logger = current_app.logger if current_app else print
    logger.critical("Gagal mengimpor model User di mikrotik_client.py. Periksa path.")
    class User: # type: ignore
        id: uuid.UUID
        phone_number: str
        full_name: str | None
        total_quota_purchased_mb: int | None
        total_quota_used_mb: float | None

# --- Fungsi Helper Format Nomor Telepon ---
def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """Mengubah format +62... atau 62... menjadi 08... Mengembalikan None jika input None."""
    logger = current_app.logger if current_app else print
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

# --- Fungsi Koneksi ---
def get_mikrotik_connection() -> Optional[routeros_api.RouterOsApiPool]:
    """Membuat dan mengembalikan objek pool koneksi API ke MikroTik."""
    logger = current_app.logger if current_app else print
    host: Optional[str] = current_app.config.get('MIKROTIK_HOST')
    port: int = current_app.config.get('MIKROTIK_PORT', 8728)
    user_cfg: Optional[str] = current_app.config.get('MIKROTIK_USER')
    password_cfg: Optional[str] = current_app.config.get('MIKROTIK_PASSWORD')
    use_ssl: bool = current_app.config.get('MIKROTIK_USE_SSL', False)
    ssl_verify_cfg = current_app.config.get('MIKROTIK_SSL_VERIFY', False)

    if not all([host, user_cfg, password_cfg]):
        logger.error("Konfigurasi MikroTik (MIKROTIK_HOST, MIKROTIK_USER, MIKROTIK_PASSWORD) tidak lengkap.")
        return None

    should_use_plaintext_login: bool = not use_ssl

    logger.debug(f"[MikroTik Client] Mencoba koneksi dengan: Host={host}, Port={port}, User={user_cfg}, SSL={use_ssl}, SSLVerify={ssl_verify_cfg}, PlaintextLogin={should_use_plaintext_login}")

    try:
        connection_pool = routeros_api.RouterOsApiPool(
            host, username=user_cfg, password=password_cfg, port=port,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify_cfg,
            ssl_verify_hostname=ssl_verify_cfg,
            plaintext_login=should_use_plaintext_login
        )
        return connection_pool
    except Exception as e: # Tangkap exception lebih umum di sini
        logger.error(f"Error saat membuat pool koneksi MikroTik: {e}", exc_info=True)
        return None

# --- Fungsi Aksi Hotspot ---

def activate_or_update_hotspot_user(
    connection_pool: Optional[routeros_api.RouterOsApiPool],
    user_db_id: str,
    mikrotik_profile_name: str,
    hotspot_password: str,
    comment: str = ""
) -> Tuple[bool, str]:
    """
    Mengaktifkan/mengupdate user hotspot di MikroTik berdasarkan data dari DB.
    """
    logger = current_app.logger if current_app else print
    if User is None: return False, "Model User tidak termuat."
    if not connection_pool:
        msg = "Tidak dapat mengaktifkan/update user hotspot: Pool koneksi MikroTik tidak valid."
        logger.error(msg); return False, msg

    api: Optional[routeros_api.RouterOsApi] = None
    username_mikrotik_formatted: Optional[str] = None
    user_uuid: Optional[uuid.UUID] = None

    try:
        try: user_uuid = uuid.UUID(user_db_id)
        except ValueError:
            msg = f"Format user_db_id tidak valid: '{user_db_id}'. Harus berupa UUID."
            logger.error(msg); return False, msg

        user_in_db = db.session.get(User, user_uuid)
        if not user_in_db:
            msg = f"User dengan ID DB {user_db_id} tidak ditemukan."
            logger.error(msg); return False, msg

        username_mikrotik_formatted = format_to_local_phone(user_in_db.phone_number)
        if not username_mikrotik_formatted:
             msg = f"Format nomor telepon tidak valid untuk User ID DB {user_db_id} (PhoneNumber DB: {user_in_db.phone_number})."
             logger.error(msg); return False, msg

        if not hotspot_password:
             msg = f"Password hotspot wajib diisi untuk user '{username_mikrotik_formatted}'."
             logger.error(msg); return False, msg

        purchased_mb = getattr(user_in_db, 'total_quota_purchased_mb', 0) or 0
        used_mb = getattr(user_in_db, 'total_quota_used_mb', 0.0) or 0.0
        remaining_mb = max(0.0, purchased_mb - used_mb)
        limit_bytes_total_val = int(remaining_mb * 1024 * 1024)
        logger.debug(f"Kuota user '{username_mikrotik_formatted}': Beli={purchased_mb}MB, Pakai={used_mb}MB, Sisa={remaining_mb}MB, LimitBytesTotal={limit_bytes_total_val}")

        server_target = "all"
        api = connection_pool.get_api()
        user_hotspot_resource = api.get_resource('/ip/hotspot/user')
        logger.debug(f"Mencari user '{username_mikrotik_formatted}' di MikroTik...")
        existing_users_list: list[dict[str, Any]] = user_hotspot_resource.get(name=username_mikrotik_formatted)
        final_comment = comment or f"DB_ID:{user_db_id};Name:{getattr(user_in_db, 'full_name', 'N/A')};"

        if existing_users_list:
            mikrotik_internal_id = existing_users_list[0]['id']
            logger.info(f"User '{username_mikrotik_formatted}' ditemukan (ID: {mikrotik_internal_id}). Memperbarui...")
            update_payload = { 'id': mikrotik_internal_id, 'password': hotspot_password, 'profile': mikrotik_profile_name, 'server': server_target, 'limit-bytes-total': str(limit_bytes_total_val), 'comment': final_comment, }
            user_hotspot_resource.set(**update_payload)
            msg = f"User MikroTik '{username_mikrotik_formatted}' berhasil diperbarui. Profil: {mikrotik_profile_name}, Limit: {limit_bytes_total_val} bytes."
            logger.info(msg)
            return True, msg
        else:
            logger.info(f"User '{username_mikrotik_formatted}' tidak ditemukan. Membuat baru...")
            add_payload = { 'name': username_mikrotik_formatted, 'password': hotspot_password, 'profile': mikrotik_profile_name, 'server': server_target, 'limit-bytes-total': str(limit_bytes_total_val), 'comment': final_comment }
            user_hotspot_resource.add(**add_payload)
            msg = f"User MikroTik baru '{username_mikrotik_formatted}' berhasil dibuat. Profil: {mikrotik_profile_name}, Limit: {limit_bytes_total_val} bytes."
            logger.info(msg)
            return True, msg

    except RouterOsApiError as e:
        ctx = f"untuk user '{username_mikrotik_formatted or user_db_id}'"
        msg = f"Gagal aksi MikroTik {ctx}. Error API: {e}. Detail: {getattr(e, 'original_message', '')}"
        logger.error(msg, exc_info=False)
        return False, f"Error API MikroTik: {getattr(e, 'original_message', str(e))}"
    except Exception as e:
        ctx = f"untuk user '{username_mikrotik_formatted or user_db_id}'"
        msg = f"Error tidak terduga selama aksi MikroTik {ctx}: {e}"
        logger.error(msg, exc_info=True)
        return False, f"Error internal server saat operasi MikroTik: {e}"
    finally:
        if api and connection_pool:
            try: connection_pool.disconnect(); logger.debug("Mikrotik API connection returned (activate/update).")
            except Exception as e_disc: logger.error(f"Error disconnect (activate/update): {e_disc}", exc_info=True)

# --- Fungsi Update Password User Hotspot ---
def update_mikrotik_user_password(
    connection_pool: Optional[routeros_api.RouterOsApiPool],
    username_db: str,
    new_password: str
) -> Tuple[bool, str]:
    """Memperbarui password user hotspot yang sudah ada di MikroTik."""
    logger = current_app.logger if current_app else print
    if not connection_pool: msg = "..."; logger.error(msg); return False, msg
    if not username_db: msg = "..."; logger.error(msg); return False, msg
    if not new_password: msg = "..."; logger.error(msg); return False, msg

    api: Optional[routeros_api.RouterOsApi] = None
    username_mikrotik_fmt: Optional[str] = format_to_local_phone(username_db)

    if not username_mikrotik_fmt: msg = "..."; logger.error(msg); return False, msg

    try:
        api = connection_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')
        logger.debug(f"Mencari user '{username_mikrotik_fmt}' untuk update password...")
        existing_user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)

        if existing_user_list:
            user_mikrotik_id = existing_user_list[0]['id']
            logger.info(f"User '{username_mikrotik_fmt}' ditemukan (ID: {user_mikrotik_id}). Memperbarui password...")
            user_resource.set(id=user_mikrotik_id, password=new_password)
            msg = f"Password MikroTik '{username_mikrotik_fmt}' berhasil diperbarui."
            logger.info(msg); return True, msg
        else:
            msg = f"User '{username_mikrotik_fmt}' tidak ditemukan. Password tidak diperbarui."
            logger.warning(msg); return False, msg

    except RouterOsApiError as e: msg = f"..."; logger.error(msg, exc_info=False); return False, f"..."
    except Exception as e: msg = f"..."; logger.error(msg, exc_info=True); return False, f"..."
    finally:
        if api and connection_pool:
            try: connection_pool.disconnect(); logger.debug("Mikrotik API connection returned (update_password).")
            except Exception as e_disc: logger.error(f"Error disconnect (update_password): {e_disc}", exc_info=True)

# --- Fungsi Helper Lainnya ---

def get_hotspot_user_usage(
    connection_pool: Optional[routeros_api.RouterOsApiPool],
    username: str
) -> Tuple[bool, Optional[Dict[str, int]], str]:
    """Mengambil data penggunaan (bytes-in, bytes-out) user dari Mikrotik."""
    logger = current_app.logger if current_app else print
    if not connection_pool: return False, None, "Pool koneksi tidak valid."
    api: Optional[routeros_api.RouterOsApi] = None
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, None, f"Username '{username}' tidak valid."

    try:
        api = connection_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
        if user_list:
            data = user_list[0]; bytes_in = int(data.get('bytes-in', 0) or 0); bytes_out = int(data.get('bytes-out', 0) or 0)
            logger.debug(f"Usage data found for '{username_mikrotik_fmt}': In={bytes_in}, Out={bytes_out}")
            return True, {'bytes_in': bytes_in, 'bytes_out': bytes_out}, "Sukses"
        else: logger.warning(f"User '{username_mikrotik_fmt}' tidak ditemukan saat get_usage."); return True, None, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except RouterOsApiError as e: msg = f"..."; logger.error(msg, exc_info=False); return False, None, msg
    except Exception as e: msg = f"..."; logger.error(msg, exc_info=True); return False, None, str(e)
    finally:
        if api and connection_pool:
            try: connection_pool.disconnect(); logger.debug("Mikrotik API connection returned (get_usage).")
            except Exception as e_disc: logger.error(f"Error disconnect (get_usage): {e_disc}", exc_info=True)


def set_hotspot_user_limit(
    connection_pool: Optional[routeros_api.RouterOsApiPool],
    username: str,
    limit_bytes_total: int
) -> Tuple[bool, str]:
    """Menetapkan limit-bytes-total untuk user hotspot Mikrotik."""
    logger = current_app.logger if current_app else print
    if not connection_pool: return False, "Pool koneksi tidak valid."
    api: Optional[routeros_api.RouterOsApi] = None
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, f"Username '{username}' tidak valid."
    try:
        api = connection_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
        if user_list:
            user_id = user_list[0]['id']; user_resource.set(id=user_id, **{'limit-bytes-total': str(limit_bytes_total)})
            logger.info(f"Limit bytes '{username_mikrotik_fmt}' diatur ke {limit_bytes_total}."); return True, "Sukses"
        else: logger.warning(f"User '{username_mikrotik_fmt}' tidak ditemukan saat set_limit."); return False, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except RouterOsApiError as e: msg = f"..."; logger.error(msg, exc_info=False); return False, msg
    except Exception as e: msg = f"..."; logger.error(msg, exc_info=True); return False, str(e)
    finally:
        if api and connection_pool:
            try: connection_pool.disconnect(); logger.debug("Mikrotik API connection returned (set_limit).")
            except Exception as e_disc: logger.error(f"Error disconnect (set_limit): {e_disc}", exc_info=True)

# --- FUNGSI DELETE DENGAN VERIFIKASI ---
def delete_hotspot_user(
    connection_pool: Optional[routeros_api.RouterOsApiPool],
    username: str # Username hotspot (format 08...)
) -> Tuple[bool, str]:
    """Menghapus user hotspot dari Mikrotik dan memverifikasi penghapusan."""
    logger = current_app.logger if current_app else print
    if not connection_pool: return False, "Pool koneksi tidak valid."
    api: Optional[routeros_api.RouterOsApi] = None
    # Username sudah diformat oleh pemanggil (user_commands.py)
    username_mikrotik_fmt = username
    if not username_mikrotik_fmt: return False, f"Username '{username}' tidak valid."

    try:
        api = connection_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')
        logger.debug(f"Mencari user '{username_mikrotik_fmt}' untuk dihapus...")
        user_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)

        if user_list:
            user_id = user_list[0]['id']
            logger.info(f"User '{username_mikrotik_fmt}' ditemukan (ID: {user_id}). Mencoba menghapus...")
            try:
                 # Kirim perintah remove
                 user_resource.remove(id=user_id)
                 logger.info(f"Perintah remove untuk user '{username_mikrotik_fmt}' (ID: {user_id}) telah dikirim.")

                 # --- VERIFIKASI PENGHAPUSAN ---
                 # Beri jeda sedikit (misal 0.5 detik) agar Mikrotik sempat memproses
                 time.sleep(0.5)
                 logger.debug(f"Memverifikasi penghapusan user '{username_mikrotik_fmt}'...")
                 verify_list: list[dict[str, Any]] = user_resource.get(name=username_mikrotik_fmt)
                 if not verify_list:
                     # Jika daftar kosong, berarti berhasil dihapus
                     logger.info(f"Verifikasi SUKSES: User '{username_mikrotik_fmt}' tidak lagi ditemukan di Mikrotik.")
                     return True, "Sukses dihapus dari Mikrotik."
                 else:
                     # Jika masih ada, berarti gagal dihapus
                     logger.error(f"Verifikasi GAGAL: User '{username_mikrotik_fmt}' masih ditemukan di Mikrotik setelah perintah remove.")
                     return False, f"Gagal menghapus user '{username_mikrotik_fmt}' dari Mikrotik (masih terdeteksi)."
            except RouterOsApiError as e_remove:
                 # Tangkap error spesifik saat remove
                 msg = f"Error API Mikrotik saat remove user {username_mikrotik_fmt}: {getattr(e_remove, 'original_message', str(e_remove))}"
                 logger.error(msg, exc_info=False)
                 return False, msg
        else:
            # User memang tidak ada dari awal
            logger.info(f"User hotspot '{username_mikrotik_fmt}' tidak ditemukan di Mikrotik (dianggap sudah terhapus).")
            return True, f"User '{username_mikrotik_fmt}' tidak ditemukan."
    except RouterOsApiError as e:
        msg = f"Error API Mikrotik saat proses delete user {username_mikrotik_fmt}: {getattr(e, 'original_message', str(e))}"
        logger.error(msg, exc_info=False)
        return False, msg
    except Exception as e:
        msg = f"Error tidak terduga saat delete user Mikrotik {username_mikrotik_fmt}: {e}"
        logger.error(msg, exc_info=True)
        return False, str(e)
    finally:
        if api and connection_pool:
            try:
                connection_pool.disconnect()
                logger.debug("Mikrotik API connection returned to pool (delete_user).")
            except Exception as e_disc:
                 logger.error(f"Error during Mikrotik pool disconnect (delete_user): {e_disc}", exc_info=True)