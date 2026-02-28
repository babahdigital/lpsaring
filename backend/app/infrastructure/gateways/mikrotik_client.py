# backend/app/infrastructure/gateways/mikrotik_client.py
# VERSI PERBAIKAN DEFINITIF: Memperbaiki logika pengambilan ID di fungsi delete_hotspot_user.

import os
import time
import logging
import re
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any, Iterator, cast, TypedDict
import routeros_api
import routeros_api.exceptions
from flask import current_app

from app.utils.circuit_breaker import record_failure, record_success, should_allow_call

logger = logging.getLogger(__name__)

_connection_pool = None
_pool_config_key = None


class MikrotikConfig(TypedDict):
    host: Optional[str]
    username: Optional[str]
    password: Optional[str]
    port: int
    use_ssl: bool
    ssl_verify: bool
    plaintext_login: bool


def _get_mikrotik_config() -> MikrotikConfig:
    try:
        host = cast(Optional[str], current_app.config.get("MIKROTIK_HOST"))
        username = cast(
            Optional[str],
            (current_app.config.get("MIKROTIK_USERNAME") or current_app.config.get("MIKROTIK_USER")),
        )
        password = cast(Optional[str], current_app.config.get("MIKROTIK_PASSWORD"))
        port_raw = current_app.config.get("MIKROTIK_PORT", 8728)
        port = int(port_raw or 8728)
        use_ssl = str(current_app.config.get("MIKROTIK_USE_SSL", "False")).lower() == "true"
        ssl_verify = str(current_app.config.get("MIKROTIK_SSL_VERIFY", "False")).lower() == "true"
        plaintext_login = str(current_app.config.get("MIKROTIK_PLAIN_TEXT_LOGIN", "True")).lower() == "true"
    except Exception:
        host = os.environ.get("MIKROTIK_HOST")
        username = os.environ.get("MIKROTIK_USERNAME") or os.environ.get("MIKROTIK_USER")
        password = os.environ.get("MIKROTIK_PASSWORD")
        port = int(os.environ.get("MIKROTIK_PORT") or 8728)
        use_ssl = (os.environ.get("MIKROTIK_USE_SSL", "False")).lower() == "true"
        ssl_verify = (os.environ.get("MIKROTIK_SSL_VERIFY", "False")).lower() == "true"
        plaintext_login = (os.environ.get("MIKROTIK_PLAIN_TEXT_LOGIN", "True")).lower() == "true"

    return cast(
        MikrotikConfig,
        {
            "host": host,
            "username": username,
            "password": password,
            "port": port,
            "use_ssl": use_ssl,
            "ssl_verify": ssl_verify,
            "plaintext_login": plaintext_login,
        },
    )


def _make_config_key(config: MikrotikConfig) -> str:
    return "|".join(
        [
            str(config.get("host")),
            str(config.get("username")),
            str(config.get("port")),
            str(config.get("use_ssl")),
            str(config.get("ssl_verify")),
            str(config.get("plaintext_login")),
        ]
    )


def init_mikrotik_pool():
    global _connection_pool
    global _pool_config_key
    config = _get_mikrotik_config()
    config_key = _make_config_key(config)
    if _connection_pool is not None and _pool_config_key == config_key:
        return True
    if not should_allow_call("mikrotik"):
        logger.warning("Mikrotik circuit breaker open. Skipping pool init.")
        return False

    host = config.get("host")
    username = config.get("username")
    password = config.get("password")
    port = config.get("port")
    use_ssl = config.get("use_ssl")
    ssl_verify = config.get("ssl_verify")
    plaintext_login = config.get("plaintext_login")

    if host is None or username is None or password is None:
        logger.error("Konfigurasi MikroTik tidak lengkap")
        return False
    if host == "" or username == "" or password == "":
        logger.error("Konfigurasi MikroTik tidak lengkap: host/username/password kosong")
        return False

    try:
        if _connection_pool is not None and _pool_config_key != config_key:
            try:
                _connection_pool.disconnect()
            except Exception:
                pass

        _connection_pool = routeros_api.RouterOsApiPool(
            host,
            username=username,
            password=password,
            port=port,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
            plaintext_login=plaintext_login,
        )
        _pool_config_key = config_key
        logger.info(f"Pool koneksi MikroTik berhasil diinisialisasi untuk {host}")
        record_success("mikrotik")
        return True
    except Exception as e:
        logger.error(f"Gagal menginisialisasi pool koneksi: {e}", exc_info=True)
        record_failure("mikrotik")
        return False


@contextmanager
def get_mikrotik_connection(raise_on_error: bool = False) -> Iterator[Optional[Any]]:
    api_instance = None

    if not should_allow_call("mikrotik"):
        logger.warning("Mikrotik circuit breaker open. Skipping connection.")
        yield None
        return

    if not init_mikrotik_pool() or _connection_pool is None:
        yield None
        return

    try:
        api_instance = _connection_pool.get_api()
        record_success("mikrotik")
    except Exception as e:
        logger.error(f"Error mendapatkan koneksi: {e}", exc_info=True)
        record_failure("mikrotik")
        yield None
        return

    try:
        yield api_instance
    except Exception as e:
        logger.error(f"Error saat operasi MikroTik: {e}", exc_info=True)
        record_failure("mikrotik")
        if raise_on_error:
            raise
        return
    finally:
        if api_instance and _connection_pool:
            try:
                return_api_fn = getattr(_connection_pool, "return_api", None)
                if callable(return_api_fn):
                    return_api_fn(api_instance)
            except Exception:
                pass


def _get_hotspot_profiles(api_connection: Any) -> Tuple[bool, List[Dict[str, Any]], str]:
    try:
        profiles = api_connection.get_resource("/ip/hotspot/user/profile").get()
        return True, profiles, "Sukses"
    except Exception as e:
        return False, [], str(e)


def _is_profile_valid(api_connection: Any, requested_profile_name: str) -> Tuple[bool, str]:
    if not requested_profile_name:
        logger.error("Validasi profil MikroTik gagal: nama profil kosong.")
        return False, "Nama profil Mikrotik tidak boleh kosong."
    success, profiles, message = _get_hotspot_profiles(api_connection)
    if not success:
        logger.error(f"Gagal memuat daftar profil MikroTik: {message}")
        return False, f"Gagal memverifikasi profil: {message}"
    for p in profiles:
        if p.get("name", "").lower() == requested_profile_name.lower():
            return True, cast(str, p.get("name") or requested_profile_name)
    available = sorted({str(p.get("name")) for p in profiles if p.get("name")})
    logger.error(
        "Profil MikroTik tidak ditemukan. Requested='%s', Available=%s",
        requested_profile_name,
        available,
    )
    return False, f"Profil '{requested_profile_name}' tidak ditemukan di Mikrotik."


def activate_or_update_hotspot_user(
    api_connection: Any,
    user_mikrotik_username: str,
    mikrotik_profile_name: str,
    hotspot_password: str,
    comment: str = "",
    limit_bytes_total: Optional[int] = None,
    session_timeout_seconds: Optional[int] = None,
    force_update_profile: bool = False,
    server: Optional[str] = "all",
    max_retries: int = 3,
) -> Tuple[bool, str]:
    is_valid_profile, profile_result = _is_profile_valid(api_connection, mikrotik_profile_name)
    if not is_valid_profile:
        return False, profile_result

    user_resource = api_connection.get_resource("/ip/hotspot/user")

    for attempt in range(1, max_retries + 1):
        try:
            users = user_resource.get(name=user_mikrotik_username)
            user_entry = users[0] if users else None

            if user_entry:
                user_id = user_entry.get("id") or user_entry.get(".id")  # Dibuat robust
                if not user_id:
                    return False, f"Gagal update, user {user_mikrotik_username} tidak memiliki ID."

                update_data = {".id": user_id, "password": hotspot_password, "comment": comment}
                if force_update_profile or user_entry.get("profile") != profile_result:
                    update_data["profile"] = profile_result
                if server:
                    update_data["server"] = server

                user_resource.set(**update_data)

                if limit_bytes_total is not None:
                    user_resource.set(**{".id": user_id, "limit-bytes-total": str(limit_bytes_total)})
                if session_timeout_seconds is not None:
                    user_resource.set(**{".id": user_id, "limit-uptime": str(session_timeout_seconds)})

                return True, f"User {user_mikrotik_username} berhasil diperbarui."
            else:
                add_data = {
                    "name": user_mikrotik_username,
                    "password": hotspot_password,
                    "profile": profile_result,
                    "server": server or "all",
                    "comment": comment,
                }
                new_user_info = user_resource.add(**add_data)

                user_id = None
                if isinstance(new_user_info, list) and new_user_info:
                    user_id = new_user_info[0].get("id") or new_user_info[0].get(".id")
                elif isinstance(new_user_info, dict):
                    user_id = new_user_info.get("id") or new_user_info.get(".id")

                if not user_id:
                    logger.warning(
                        f"Mikrotik 'add' tidak mengembalikan ID untuk user {user_mikrotik_username}. "
                        f"Mencoba verifikasi ulang. Respons: {new_user_info}"
                    )
                    time.sleep(0.5)
                    created_users = user_resource.get(name=user_mikrotik_username)
                    if created_users:
                        created_id = created_users[0].get("id") or created_users[0].get(".id")
                        if created_id:
                            if limit_bytes_total is not None:
                                user_resource.set(**{".id": created_id, "limit-bytes-total": str(limit_bytes_total)})
                            if session_timeout_seconds is not None:
                                user_resource.set(**{".id": created_id, "limit-uptime": str(session_timeout_seconds)})
                            return True, f"User {user_mikrotik_username} berhasil dibuat (ID diverifikasi ulang)."
                    continue

                if limit_bytes_total is not None:
                    user_resource.set(**{".id": user_id, "limit-bytes-total": str(limit_bytes_total)})
                if session_timeout_seconds is not None:
                    user_resource.set(**{".id": user_id, "limit-uptime": str(session_timeout_seconds)})

                return True, f"User {user_mikrotik_username} berhasil dibuat."

        except routeros_api.exceptions.RouterOsApiError as e:
            raw_message = getattr(e, "original_message", str(e))
            error_msg_str = str(
                raw_message.decode("utf-8", errors="ignore") if isinstance(raw_message, bytes) else raw_message
            )

            if "already have user with this name" in error_msg_str:
                logger.warning(
                    f"Konflik (user sudah ada) saat membuat {user_mikrotik_username}. Percobaan {attempt}..."
                )
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
    """
    [PERBAIKAN DEFINITIF] Menghapus user dengan memeriksa kunci ID yang benar.
    """
    if not username:
        return False, "Username tidak valid"

    logger.info(f"[MIKROTIK DELETE] Memulai proses hapus untuk user: {username}")

    # Hapus user dari /ip/hotspot/user
    user_resource = api_connection.get_resource("/ip/hotspot/user")
    for attempt in range(max_retries):
        try:
            users = user_resource.get(name=username)
            if not users:
                return True, f"User {username} tidak ditemukan (dianggap terhapus)."

            user_entry = users[0]
            # --- [PERBAIKAN UTAMA DI SINI] ---
            # Berdasarkan log Anda, kunci yang benar adalah 'id' (tanpa titik).
            # Kode ini sekarang memeriksa 'id' terlebih dahulu, lalu '.id' sebagai cadangan.
            user_id = user_entry.get("id") or user_entry.get(".id")

            if not user_id:
                # Log ini sekarang lebih akurat berdasarkan apa yang terjadi
                logger.error(
                    f"[MIKROTIK DELETE] Entri user {username} ditemukan tanpa kunci 'id' atau '.id'. Data: {user_entry}"
                )
                return False, f"Gagal menghapus {username}: entri user ditemukan di Mikrotik tanpa ID."

            user_resource.remove(id=user_id)
            time.sleep(0.3)  # Beri jeda untuk verifikasi

            if not user_resource.get(name=username):
                logger.info(f"[MIKROTIK DELETE] Verifikasi berhasil. User {username} telah dihapus.")
                return True, f"User {username} berhasil dihapus."
            else:
                logger.warning(f"[MIKROTIK DELETE] Verifikasi gagal, user {username} masih ada. Mencoba lagi...")
        except Exception as e:
            logger.error(f"[MIKROTIK DELETE] Error pada percobaan hapus user {username}: {e}", exc_info=True)
            time.sleep(0.5 * (attempt + 1))

    return False, f"Gagal menghapus user {username} dari Mikrotik setelah beberapa percobaan."


def set_hotspot_user_profile(api_connection: Any, username_or_id: str, new_profile_name: str) -> Tuple[bool, str]:
    is_valid, profile_name = _is_profile_valid(api_connection, new_profile_name)
    if not is_valid:
        return False, profile_name
    try:
        user_resource = api_connection.get_resource("/ip/hotspot/user")
        users = user_resource.get(name=username_or_id) or user_resource.get(id=username_or_id)
        if not users:
            return False, f"User {username_or_id} tidak ditemukan."

        user_id = users[0].get("id") or users[0].get(".id")
        if not user_id:
            return False, f"Gagal mengubah profil, user {username_or_id} tidak memiliki ID."

        user_resource.set(id=user_id, profile=profile_name)
        return True, f"Profil berhasil diubah ke {profile_name}."
    except Exception as e:
        return False, str(e)


def get_hotspot_user_details(api_connection: Any, username: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        users = api_connection.get_resource("/ip/hotspot/user").get(name=username)
        return (True, users[0], "Sukses") if users else (True, None, "User tidak ditemukan")
    except Exception as e:
        return False, None, str(e)


def get_hotspot_user_usage_map(api_connection: Any) -> Tuple[bool, Dict[str, Dict[str, Any]], str]:
    """Mengambil peta pemakaian hotspot user dari MikroTik dalam satu kali panggilan."""
    try:
        users = api_connection.get_resource("/ip/hotspot/user").get()
        usage_map: Dict[str, Dict[str, Any]] = {}
        for user in users:
            name = user.get("name")
            if not name:
                continue
            usage_map[str(name)] = {
                "bytes_in": int(user.get("bytes-in", "0")),
                "bytes_out": int(user.get("bytes-out", "0")),
                "profile": user.get("profile"),
            }
        return True, usage_map, "Sukses"
    except Exception as e:
        return False, {}, str(e)


def get_hotspot_host_usage_map(api_connection: Any) -> Tuple[bool, Dict[str, Dict[str, Any]], str]:
    """Mengambil pemakaian hotspot host berdasarkan MAC address."""
    try:
        hosts = api_connection.get_resource("/ip/hotspot/host").get()
        usage_map: Dict[str, Dict[str, Any]] = {}
        for host in hosts:
            mac = host.get("mac-address")
            if not mac:
                continue
            usage_map[str(mac).upper()] = {
                "bytes_in": int(host.get("bytes-in", "0")),
                "bytes_out": int(host.get("bytes-out", "0")),
                "address": host.get("address"),
                "server": host.get("server"),
                "bypassed": str(host.get("bypassed", "false")).lower() == "true",
                "authorized": str(host.get("authorized", "false")).lower() == "true",
            }
        return True, usage_map, "Sukses"
    except Exception as e:
        return False, {}, str(e)


def get_hotspot_hosts(api_connection: Any) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Ambil daftar /ip/hotspot/host mentah (untuk kebutuhan scan unauthorized)."""
    try:
        hosts = api_connection.get_resource("/ip/hotspot/host").get()
        result: List[Dict[str, Any]] = []
        for host in hosts:
            # Normalize keys we care about.
            result.append(
                {
                    "address": host.get("address"),
                    "mac-address": host.get("mac-address"),
                    "server": host.get("server"),
                    "user": host.get("user"),
                    "uptime": host.get("uptime"),
                    "bypassed": host.get("bypassed"),
                    "authorized": host.get("authorized"),
                }
            )
        return True, result, "Sukses"
    except Exception as e:
        return False, [], str(e)


def get_firewall_address_list_entries(
    api_connection: Any,
    list_name: str,
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Ambil semua entri address-list untuk list tertentu."""
    if not list_name:
        return False, [], "Nama list kosong"
    try:
        resource = api_connection.get_resource("/ip/firewall/address-list")
        entries = resource.get(list=list_name)
        normalized: List[Dict[str, Any]] = []
        for e in entries:
            entry_id = e.get("id") or e.get(".id")
            normalized.append(
                {
                    "id": entry_id,
                    "address": e.get("address"),
                    "list": e.get("list"),
                    "comment": e.get("comment"),
                    "dynamic": e.get("dynamic"),
                    "timeout": e.get("timeout"),
                }
            )
        return True, normalized, "Sukses"
    except Exception as e:
        return False, [], str(e)


def _extract_user_id_from_comment(comment: Optional[str]) -> Optional[str]:
    if not comment:
        return None
    text = str(comment)
    match = re.search(r"(?:^|[|\s])uid=([^|\s]+)", text)
    if match:
        return match.group(1).strip() or None
    match = re.search(r"(?:^|[|\s])user_id=([^|\s]+)", text)
    if match:
        return match.group(1).strip() or None
    match = re.search(r"(?:^|[|\s])user=([^|\s]+)", text)
    if match:
        return match.group(1).strip() or None
    return None


def get_hotspot_ip_binding_user_map(api_connection: Any) -> Tuple[bool, Dict[str, Dict[str, Any]], str]:
    """Mengambil peta ip-binding (MAC -> user_id) berdasarkan comment."""
    try:
        bindings = api_connection.get_resource("/ip/hotspot/ip-binding").get()
        usage_map: Dict[str, Dict[str, Any]] = {}
        for entry in bindings:
            mac = entry.get("mac-address")
            if not mac:
                continue
            user_id = _extract_user_id_from_comment(entry.get("comment"))
            if not user_id:
                continue
            usage_map[str(mac).upper()] = {
                "user_id": user_id,
                "address": entry.get("address"),
                "type": entry.get("type"),
                "comment": entry.get("comment"),
            }
        return True, usage_map, "Sukses"
    except Exception as e:
        return False, {}, str(e)


def has_hotspot_ip_binding_for_user(
    api_connection: Any,
    *,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    mac_address: Optional[str] = None,
) -> Tuple[bool, bool, str]:
    """Cek apakah user memiliki ip-binding non-blocked.

    Match user berdasarkan token comment (`user=...`, `uid=...`) dan opsional dipersempit oleh MAC.
    Return: (success, has_binding, message)
    """
    username_norm = str(username or "").strip()
    user_id_norm = str(user_id or "").strip()
    mac_norm = str(mac_address or "").strip().upper()

    if not username_norm and not user_id_norm:
        return False, False, "Identitas user tidak valid"

    try:
        resource = api_connection.get_resource("/ip/hotspot/ip-binding")
        query: Dict[str, Any] = {}
        if mac_norm:
            query["mac-address"] = mac_norm

        bindings = resource.get(**query) if query else resource.get()
        for entry in bindings or []:
            entry_type = str(entry.get("type") or "").strip().lower()
            if entry_type == "blocked":
                continue

            comment_user = _extract_user_id_from_comment(entry.get("comment"))
            if not comment_user:
                continue

            comment_user_norm = str(comment_user).strip()
            if username_norm and comment_user_norm == username_norm:
                return True, True, "Sukses"
            if user_id_norm and comment_user_norm == user_id_norm:
                return True, True, "Sukses"

        return True, False, "IP binding user tidak ditemukan"
    except Exception as e:
        return False, False, str(e)


def get_hotspot_user_ip(api_connection: Any, username: str) -> Tuple[bool, Optional[str], str]:
    """Mencari IP user berdasarkan host hotspot, DHCP lease, atau ARP."""
    if not username:
        return False, None, "Username tidak valid"
    try:
        host_resource = api_connection.get_resource("/ip/hotspot/host")
        hosts = host_resource.get(user=username)
        if hosts:
            address = hosts[0].get("address")
            if address:
                return True, str(address), "Sukses (hotspot host)"
    except Exception:
        pass

    try:
        lease_resource = api_connection.get_resource("/ip/dhcp-server/lease")
        leases = lease_resource.get()
        marker = f"user={username}".lower()
        for lease in leases or []:
            comment = str(lease.get("comment") or "").lower()
            if marker in comment:
                address = lease.get("address")
                if address:
                    return True, str(address), "Sukses (DHCP lease)"
    except Exception:
        pass

    try:
        arp_resource = api_connection.get_resource("/ip/arp")
        arps = arp_resource.get()
        marker = f"user={username}".lower()
        for arp in arps or []:
            comment = str(arp.get("comment") or "").lower()
            if marker in comment:
                address = arp.get("address")
                if address:
                    return True, str(address), "Sukses (ARP)"
    except Exception as e:
        return False, None, str(e)

    return True, None, "IP tidak ditemukan"


def upsert_address_list_entry(
    api_connection: Any, address: str, list_name: str, comment: Optional[str] = None, timeout: Optional[str] = None
) -> Tuple[bool, str]:
    if not address or not list_name:
        return False, "Alamat atau nama list kosong"
    try:
        resource = api_connection.get_resource("/ip/firewall/address-list")
        entries = resource.get(address=address, list=list_name)
        if entries:
            entry_id = entries[0].get("id") or entries[0].get(".id")
            if not entry_id:
                return False, "Entri address-list tidak memiliki ID"
            update_data = {".id": entry_id}
            if comment is not None:
                update_data["comment"] = comment
            if timeout is not None:
                update_data["timeout"] = timeout
            resource.set(**update_data)
        else:
            add_data = {"address": address, "list": list_name}
            if comment is not None:
                add_data["comment"] = comment
            if timeout is not None:
                add_data["timeout"] = timeout
            resource.add(**add_data)
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def remove_address_list_entry(api_connection: Any, address: str, list_name: str) -> Tuple[bool, str]:
    if not address or not list_name:
        return False, "Alamat atau nama list kosong"
    try:
        resource = api_connection.get_resource("/ip/firewall/address-list")
        entries = resource.get(address=address, list=list_name)
        removed = 0
        for entry in entries:
            entry_id = entry.get(".id") or entry.get("id")
            if entry_id:
                try:
                    resource.remove(**{".id": entry_id})
                except Exception:
                    resource.remove(id=entry_id)
                removed += 1

        if entries and removed == 0:
            return False, "Entri ditemukan tetapi gagal dihapus (ID tidak valid)"
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def sync_address_list_for_user(
    api_connection: Any,
    username: str,
    target_list: Optional[str],
    other_lists: Optional[List[str]] = None,
    comment: Optional[str] = None,
    timeout: Optional[str] = None,
) -> Tuple[bool, str]:
    """Sinkronkan address-list berdasarkan username user hotspot."""
    success, address, message = get_hotspot_user_ip(api_connection, username)
    if not success:
        return False, message
    if not address:
        return False, "IP belum tersedia untuk user"

    if target_list:
        ok, msg = upsert_address_list_entry(api_connection, address, target_list, comment=comment, timeout=timeout)
        if not ok:
            return False, msg

    if other_lists:
        for list_name in other_lists:
            if list_name and list_name != target_list:
                remove_address_list_entry(api_connection, address, list_name)

    return True, "Sukses"


def get_mac_by_ip(api_connection: Any, ip_address: str) -> Tuple[bool, Optional[str], str]:
    """Mencari MAC address berdasarkan IP melalui hotspot host, ARP, atau DHCP lease."""
    if not ip_address:
        return False, None, "IP address tidak valid"

    try:
        host_resource = api_connection.get_resource("/ip/hotspot/host")
        hosts = host_resource.get(address=ip_address)
        if hosts:
            mac = hosts[0].get("mac-address")
            if mac:
                return True, str(mac), "Sukses (hotspot host)"
    except Exception:
        pass

    try:
        arp_resource = api_connection.get_resource("/ip/arp")
        arps = arp_resource.get(address=ip_address)
        if arps:
            mac = arps[0].get("mac-address")
            if mac:
                return True, str(mac), "Sukses (ARP)"
    except Exception:
        pass

    try:
        lease_resource = api_connection.get_resource("/ip/dhcp-server/lease")
        leases = lease_resource.get(address=ip_address)
        if leases:
            mac = leases[0].get("mac-address")
            if mac:
                return True, str(mac), "Sukses (DHCP lease)"
    except Exception as e:
        return False, None, str(e)

    return True, None, "MAC tidak ditemukan"


def get_ip_by_mac(api_connection: Any, mac_address: str) -> Tuple[bool, Optional[str], str]:
    """Mencari IP address berdasarkan MAC melalui hotspot host, ARP, atau DHCP lease."""
    if not mac_address:
        return False, None, "MAC address tidak valid"

    try:
        host_resource = api_connection.get_resource("/ip/hotspot/host")
        hosts = host_resource.get(**{"mac-address": mac_address})
        if hosts:
            address = hosts[0].get("address")
            if address:
                return True, str(address), "Sukses (hotspot host)"
    except Exception:
        pass

    try:
        arp_resource = api_connection.get_resource("/ip/arp")
        arps = arp_resource.get(**{"mac-address": mac_address})
        if arps:
            address = arps[0].get("address")
            if address:
                return True, str(address), "Sukses (ARP)"
    except Exception:
        pass

    try:
        lease_resource = api_connection.get_resource("/ip/dhcp-server/lease")
        leases = lease_resource.get(**{"mac-address": mac_address})
        if leases:
            address = leases[0].get("address")
            if address:
                return True, str(address), "Sukses (DHCP lease)"
    except Exception as e:
        return False, None, str(e)

    return True, None, "IP tidak ditemukan"


def upsert_dhcp_static_lease(
    api_connection: Any,
    mac_address: str,
    address: str,
    comment: Optional[str] = None,
    server: Optional[str] = None,
) -> Tuple[bool, str]:
    """Buat/perbarui DHCP static lease (MAC -> IP).

    Catatan:
    - Ini opsional untuk menstabilkan IP supaya address-list berbasis IP tidak mudah stale.
    - Jika lease yang ditemukan masih dynamic, coba `make-static` dulu.
    """
    mac_address = str(mac_address or "").strip().upper()
    address = str(address or "").strip()
    if not mac_address:
        return False, "MAC address tidak valid"
    if not address:
        return False, "IP address tidak valid"

    managed_marker = None
    if comment:
        text = str(comment)
        if "lpsaring|static-dhcp" in text:
            managed_marker = "lpsaring|static-dhcp"

    server_norm = str(server).strip() if server is not None else ""
    if server_norm == "":
        server_norm = ""
        server = None

    # Safety: if this is a managed static-dhcp comment, require an explicit DHCP server pin.
    # Otherwise, we could accidentally update a lease that belongs to another DHCP server (Kamtib/AOP/etc).
    if managed_marker and server is None:
        return False, "MIKROTIK_DHCP_LEASE_SERVER_NAME wajib diset untuk managed static-dhcp (lpsaring|static-dhcp)"

    try:
        resource = api_connection.get_resource("/ip/dhcp-server/lease")
        leases = resource.get(**{"mac-address": mac_address}) or []

        # Cleanup any *managed* leases for this MAC that ended up on other DHCP servers.
        # This prevents cross-server duplication caused by older behavior/misconfiguration.
        if managed_marker and server is not None:
            for lease in list(leases):
                lease_id = lease.get("id") or lease.get(".id")
                lease_server = str(lease.get("server") or "").strip()
                lease_comment = str(lease.get("comment") or "")
                if not lease_id:
                    continue
                if managed_marker not in lease_comment:
                    continue
                if lease_server == server_norm:
                    continue
                try:
                    resource.remove(id=lease_id)
                except Exception:
                    # Best-effort cleanup.
                    pass

            # Refresh leases snapshot after cleanup attempts.
            leases = resource.get(**{"mac-address": mac_address}) or []

        chosen: Optional[dict] = None
        if leases:
            if server is not None:
                for lease in leases:
                    if str(lease.get("server") or "").strip() == server_norm:
                        chosen = lease
                        break
            else:
                chosen = leases[0]

        if chosen:
            lease_id = chosen.get("id") or chosen.get(".id")
            if not lease_id:
                return False, "Entri DHCP lease tidak memiliki ID"

            is_dynamic = str(chosen.get("dynamic") or "").strip().lower() in {"true", "yes", "1"}
            if is_dynamic:
                try:
                    resource.call("make-static", {"numbers": lease_id})
                except Exception as e:
                    return False, f"Gagal make-static DHCP lease: {e}"

            update_data: dict[str, Any] = {".id": lease_id, "address": address}
            if comment is not None:
                update_data["comment"] = comment
            # NOTE: don't rewrite server when chosen already matches server_norm.
            resource.set(**update_data)
            return True, "Sukses"

        # If server is pinned and no lease exists for that server, create a new one.
        add_data: dict[str, Any] = {"mac-address": mac_address, "address": address}
        if comment is not None:
            add_data["comment"] = comment
        if server is not None:
            add_data["server"] = server_norm
        resource.add(**add_data)
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def remove_dhcp_lease(
    api_connection: Any,
    mac_address: str,
    server: Optional[str] = None,
) -> Tuple[bool, str]:
    mac_address = str(mac_address or "").strip().upper()
    if not mac_address:
        return False, "MAC address tidak valid"
    try:
        resource = api_connection.get_resource("/ip/dhcp-server/lease")
        query: dict[str, Any] = {"mac-address": mac_address}
        if server:
            query["server"] = server
        leases = resource.get(**query)
        for lease in leases or []:
            lease_id = lease.get("id") or lease.get(".id")
            if lease_id:
                resource.remove(id=lease_id)
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def upsert_ip_binding(
    api_connection: Any,
    mac_address: str,
    address: Optional[str] = None,
    server: Optional[str] = None,
    binding_type: str = "regular",
    comment: Optional[str] = None,
) -> Tuple[bool, str]:
    """Buat atau perbarui ip-binding untuk MAC tertentu.

    Catatan: untuk menjaga stabilitas di jaringan hotspot (DHCP/roaming), ip-binding dibuat
    berbasis MAC saja (tanpa mengunci ke IP) untuk semua type (regular/blocked/bypassed).
    Policy firewall tetap dikelola via address-list (berbasis IP).
    """
    if not mac_address:
        return False, "MAC address tidak valid"
    try:
        resource = api_connection.get_resource("/ip/hotspot/ip-binding")
        # Ambil semua entry untuk MAC ini untuk menghindari duplikat/konflik.
        # Kasus paling bermasalah: ada entry server=all dengan type=blocked yang meng-override entry server spesifik.
        all_entries = resource.get(**{"mac-address": mac_address})

        server_norm = str(server).strip() if server else ""
        entries: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for e in all_entries or []:
            e_server = str(e.get("server") or "").strip()

            # Jika kita sedang menulis untuk server spesifik, hapus semua entry server=all untuk MAC ini.
            if server_norm and e_server.lower() == "all":
                conflicts.append(e)
                continue

            if not server_norm:
                entries.append(e)
            else:
                if e_server == server_norm:
                    entries.append(e)

        for entry in conflicts:
            entry_id = entry.get("id") or entry.get(".id")
            if entry_id:
                resource.remove(id=entry_id)

        payload = {"mac-address": mac_address, "type": binding_type, "disabled": "false"}
        mac_only = True
        if server:
            payload["server"] = server
        if comment is not None:
            payload["comment"] = comment

        if entries:
            # Jika ada duplikat pada server yang sama, bersihkan agar hanya tersisa satu.
            if len(entries) > 1:
                keep = entries[0]
                for extra in entries[1:]:
                    extra_id = extra.get("id") or extra.get(".id")
                    if extra_id:
                        resource.remove(id=extra_id)
                entries = [keep]

            # Jika entry lama mengunci address, recreate agar jadi MAC-only.
            if mac_only and any(str(e.get("address") or "").strip() for e in entries):
                for entry in entries:
                    entry_id = entry.get("id") or entry.get(".id")
                    if entry_id:
                        resource.remove(id=entry_id)
                resource.add(**payload)
                return True, "Sukses (recreate mac-only)"

            entry_id = entries[0].get("id") or entries[0].get(".id")
            if not entry_id:
                return False, "Entri ip-binding tidak memiliki ID"
            resource.set(**{".id": entry_id, **payload})
        else:
            resource.add(**payload)
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def remove_ip_binding(api_connection: Any, mac_address: str, server: Optional[str] = None) -> Tuple[bool, str]:
    if not mac_address:
        return False, "MAC address tidak valid"
    try:
        resource = api_connection.get_resource("/ip/hotspot/ip-binding")
        query = {"mac-address": mac_address}
        if server:
            query["server"] = server
        entries = resource.get(**query)
        for entry in entries:
            entry_id = entry.get("id") or entry.get(".id")
            if entry_id:
                resource.remove(id=entry_id)
        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def sync_walled_garden_rules(
    api_connection: Any, allowed_hosts: List[str], allowed_ips: List[str], comment_prefix: str = "lpsaring"
) -> Tuple[bool, str]:
    """Sinkronkan walled-garden host & IP yang dikelola aplikasi."""
    try:
        host_resource = api_connection.get_resource("/ip/hotspot/walled-garden")
        ip_resource = api_connection.get_resource("/ip/hotspot/walled-garden/ip")

        desired_hosts = {h.strip() for h in allowed_hosts if h and h.strip()}
        desired_ips = {ip.strip() for ip in allowed_ips if ip and ip.strip()}

        existing_hosts = host_resource.get()
        for entry in existing_hosts:
            comment = entry.get("comment") or ""
            if not comment.startswith(comment_prefix):
                continue
            dst_host = entry.get("dst-host")
            if dst_host and dst_host not in desired_hosts:
                entry_id = entry.get("id") or entry.get(".id")
                if entry_id:
                    host_resource.remove(id=entry_id)

        existing_ips = ip_resource.get()
        for entry in existing_ips:
            comment = entry.get("comment") or ""
            if not comment.startswith(comment_prefix):
                continue
            dst_address = entry.get("dst-address")
            if dst_address and dst_address not in desired_ips:
                entry_id = entry.get("id") or entry.get(".id")
                if entry_id:
                    ip_resource.remove(id=entry_id)

        for host in desired_hosts:
            entries = host_resource.get(**{"dst-host": host})
            payload = {"dst-host": host, "comment": f"{comment_prefix}:host"}
            if entries:
                entry_id = entries[0].get("id") or entries[0].get(".id")
                if entry_id:
                    host_resource.set(**{".id": entry_id, **payload})
            else:
                host_resource.add(**payload)

        for ip in desired_ips:
            entries = ip_resource.get(**{"dst-address": ip})
            payload = {"dst-address": ip, "comment": f"{comment_prefix}:ip"}
            if entries:
                entry_id = entries[0].get("id") or entries[0].get(".id")
                if entry_id:
                    ip_resource.set(**{".id": entry_id, **payload})
            else:
                ip_resource.add(**payload)

        return True, "Sukses"
    except Exception as e:
        return False, str(e)


def get_walled_garden_rules(
    api_connection: Any,
    comment_prefix: str = "lpsaring",
) -> Tuple[bool, Dict[str, List[str]], str]:
    try:
        host_resource = api_connection.get_resource("/ip/hotspot/walled-garden")
        ip_resource = api_connection.get_resource("/ip/hotspot/walled-garden/ip")

        hosts = []
        ips = []

        for entry in host_resource.get():
            comment = entry.get("comment") or ""
            if comment.startswith(comment_prefix):
                dst_host = entry.get("dst-host")
                if dst_host:
                    hosts.append(str(dst_host))

        for entry in ip_resource.get():
            comment = entry.get("comment") or ""
            if comment.startswith(comment_prefix):
                dst_address = entry.get("dst-address")
                if dst_address:
                    ips.append(str(dst_address))

        return True, {"hosts": sorted(set(hosts)), "ips": sorted(set(ips))}, "Sukses"
    except Exception as e:
        return False, {"hosts": [], "ips": []}, str(e)
