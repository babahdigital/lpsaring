# backend/app/infrastructure/gateways/mikrotik_client_impl.py
"""Unified MikroTik client implementation.

Fokus:
- Connection pooling resilien + cooldown error
- Manajemen hotspot user, ip-binding, address-list
- Deteksi MAC komprehensif (host, dhcp, active, arp, ping, binding, bridge fdb, dns)
- Cache hasil MAC (positive & negative) via mikrotik_cache
- Kompatibel dengan API lama yang dipakai oleh service/routes

Catatan Struktur:
Wrapper publik: app.infrastructure.gateways.mikrotik_client.__init__ memanggil
_lazy_impl() -> modul ini, sehingga pemanggil tinggal import
from app.infrastructure.gateways import mikrotik_client

Jika menambah fungsi baru ekspor tambahkan di __all__ di bawah.
"""
from __future__ import annotations
import logging, time, threading, socket, collections
from typing import Optional, Any, Tuple, List, Dict, Callable
from functools import lru_cache

from flask import current_app
from routeros_api.api import RouterOsApi  # type: ignore
from routeros_api.exceptions import RouterOsApiError  # type: ignore

from .mikrotik_cache import (
    get_cached_mac_by_ip,
    cache_mac_by_ip,
    invalidate_ip_cache,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection Pool
# ---------------------------------------------------------------------------
_connection_pool_lock = threading.RLock()
_global_connection_pool = None  # legacy single
_connection_pools: List[Any] = []  # multi-pool list
_pool_index = 0
_last_connection_time = 0.0
_connection_error_count = 0
_MAX_ERROR_COUNT = 5
_CONNECTION_COOLDOWN = 60  # detik (base). Akan dieksponensialkan berdasarkan jumlah error.
_last_backoff_until = 0.0
_log_suppression_state = {'errors': 0, 'first_ts': 0.0}


def _get_connection_config() -> Dict[str, Any]:
    try:
        import os
        from config import config_options  # type: ignore
        flask_env = os.environ.get("FLASK_ENV", "development")
        cfg = config_options[flask_env]
        return {
            "host": os.environ.get("MIKROTIK_HOST", cfg.MIKROTIK_HOST),
            "username": os.environ.get("MIKROTIK_USERNAME", cfg.MIKROTIK_USERNAME),
            "password": os.environ.get("MIKROTIK_PASSWORD", cfg.MIKROTIK_PASSWORD),
            "port": int(os.environ.get("MIKROTIK_PORT", cfg.MIKROTIK_PORT)),
            "use_ssl": os.environ.get("MIKROTIK_USE_SSL", str(getattr(cfg, "MIKROTIK_USE_SSL", "false")).lower() == "true"),
            "plaintext_login": True,
        }
    except Exception as e:  # pragma: no cover
        logger.error(f"[MT-CONFIG] Fallback config karena error: {e}")
        return {
            "host": "172.16.0.1",
            "username": "hotspot",
            "password": "",
            "port": 8728,
            "use_ssl": False,
            "plaintext_login": True,
        }


def _create_connection_pool():
    """Buat connection pool dengan timeout socket diset sesuai konfigurasi.

    RouterOsApiPool tidak expose timeout secara langsung; kita set default socket timeout
    sementara proses koneksi berlangsung. Timeout ini akan mempengaruhi koneksi bawah (TCP).
    """
    global _global_connection_pool, _last_connection_time, _connection_error_count, _last_backoff_until
    import routeros_api  # type: ignore
    cfg = _get_connection_config()
    connect_timeout = _safe_cfg('MIKROTIK_CONNECT_TIMEOUT_SECONDS', 3)
    read_timeout = _safe_cfg('MIKROTIK_READ_TIMEOUT_SECONDS', 5)
    prev_default = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(connect_timeout)
        pool = routeros_api.RouterOsApiPool(
            host=cfg["host"],
            username=cfg["username"],
            password=cfg["password"],
            port=cfg["port"],
            use_ssl=cfg["use_ssl"],
            plaintext_login=cfg["plaintext_login"],
        )
        api = None
        try:
            api = pool.get_api()
        except Exception as e:
            raise e
        if api:
            # Set read timeout via underlying socket jika memungkinkan
            try:
                # routeros_api tidak expose langsung, jadi best-effort: akses private transport
                transport = getattr(api, 'connection', None)
                sock = getattr(transport, 'socket', None)
                if sock and hasattr(sock, 'settimeout'):
                    sock.settimeout(read_timeout)
            except Exception:  # pragma: no cover
                pass
            _last_connection_time = time.time()
            _connection_error_count = 0
            _last_backoff_until = 0.0
            logger.info(f"[MT-CONNECT] ✅ Pool ke {cfg['host']}:{cfg['port']} siap (timeout c={connect_timeout}s r={read_timeout}s)")
            return pool
    except Exception as e:
        _connection_error_count += 1
        backoff_factor = min(_connection_error_count, 6)
        dynamic_cooldown = _CONNECTION_COOLDOWN * (2 ** (backoff_factor - 1)) if _connection_error_count >= _MAX_ERROR_COUNT else _CONNECTION_COOLDOWN
        _last_backoff_until = time.time() + dynamic_cooldown
        _suppressable_log('error', f"[MT-CONNECT] ❌ Gagal buat pool (err#{_connection_error_count}) backoff {int(dynamic_cooldown)}s: {e}")
    finally:
        socket.setdefaulttimeout(prev_default)
    return None


def _get_api_from_pool(pool_name=None) -> Optional[RouterOsApi]:  # noqa: D401
    global _global_connection_pool, _last_connection_time, _connection_error_count, _last_backoff_until, _pool_index
    # Coba ambil dari context Flask
    try:
        pool = getattr(current_app, "mikrotik_api_pool", None)
        if pool:
            try:
                return pool.get_api()
            except Exception as e:
                logger.warning(f"[MT-CONNECT] Pool app error: {e}")
    except Exception:
        pass

    # Cooldown jika terlalu banyak error
    # Exponential backoff window
    if _connection_error_count >= _MAX_ERROR_COUNT:
        now = time.time()
        if now < _last_backoff_until:
            # sekali saja per window
            if int(now) % 10 == 0:  # reduce spam
                logger.warning("[MT-CONNECT] Cooldown aktif (exponential backoff)")
            return None
        # Half-open probe: coba satu koneksi ringan (tidak reset counters jika gagal)
        api = None
        try:
            pool = _create_connection_pool()
            if pool:
                api = pool.get_api()
        except Exception:
            return None
        if api:
            return api

    with _connection_pool_lock:
        desired_size = int(_safe_cfg('MIKROTIK_POOL_SIZE', 1))
        if desired_size <= 1:
            if _global_connection_pool is None:
                _global_connection_pool = _create_connection_pool()
            if _global_connection_pool:
                try:
                    return _global_connection_pool.get_api()
                except Exception:
                    _global_connection_pool = _create_connection_pool()
                    if _global_connection_pool:
                        try:
                            return _global_connection_pool.get_api()
                        except Exception:
                            return None
        else:
            # Multi pool
            # Grow if needed
            while len(_connection_pools) < desired_size:
                p = _create_connection_pool()
                if p:
                    _connection_pools.append(p)
                else:
                    break
            if not _connection_pools:
                return None
            # Round-robin
            _pool_index = (_pool_index + 1) % len(_connection_pools)
            pool = _connection_pools[_pool_index]
            try:
                return pool.get_api()
            except Exception:
                # Attempt recreate single pool slot
                newp = _create_connection_pool()
                if newp:
                    _connection_pools[_pool_index] = newp
                    try:
                        return newp.get_api()
                    except Exception:
                        return None
                return None
    return None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_item_id(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    return item.get(".id") or item.get("id")


def _add_to_address_list(api: RouterOsApi, address: str, list_name: str, comment: str):
    if not address:
        return
    res = api.get_resource("/ip/firewall/address-list")
    if not res.get(address=address, list=list_name):
        res.add(address=address, list=list_name, comment=comment)
        logger.info(f"[ADDR-LIST] + {address} -> {list_name} ({comment})")


def remove_from_address_list_by_comment(api: RouterOsApi, comment: str, list_name: str):
    if not comment or not list_name:
        return
    res = api.get_resource("/ip/firewall/address-list")
    for entry in res.get(comment=comment, list=list_name):
        if entry_id := _get_item_id(entry):
            res.remove(id=entry_id)

# ---------------------------------------------------------------------------
# IP Binding & User Management
# ---------------------------------------------------------------------------

def disable_ip_binding_by_comment(comment: str) -> Tuple[bool, str]:
    if not comment:
        return False, "Komentar (username) tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource("/ip/hotspot/ip-binding")
        bindings = res.get(comment=comment)
        if not bindings:
            return True, "IP Binding tidak ditemukan."
        if binding_id := _get_item_id(bindings[0]):
            res.set(id=binding_id, disabled="yes")
            return True, "IP Binding dinonaktifkan."
        return False, "IP Binding tanpa ID."
    except Exception as e:
        logger.error(f"[BINDING] disable error: {e}")
        return False, str(e)


def create_or_update_ip_binding(
    mac_address: str,
    ip_address: str,
    comment: str,
    server: Optional[str] = None,
    type: str = "bypassed",
) -> Tuple[bool, str]:
    if not all([mac_address, ip_address, comment]):
        return False, "MAC, IP, comment wajib."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource("/ip/hotspot/ip-binding")
        existing = res.get(comment=comment)
        # Valid MikroTik binding type mapping
        type_map = {
            "bypassed": "bypassed",
            "blocked": "blocked",
            "quota-finished": "regular",  # fallback ke regular
            "regular": "regular",
        }
        mt_type = type_map.get(type, "regular")
        disabled = "yes" if mt_type in ["blocked"] else "no"
        # Build data payload while preserving existing 'server' when updating.
        data = {
            "mac-address": mac_address.upper(),
            "address": ip_address,
            "comment": comment,
            "type": mt_type,
            # Do NOT force 'server' to 'all'. Only set if explicitly provided.
            "disabled": disabled,
        }
        if server:
            data["server"] = server
        if existing:
            b_id = _get_item_id(existing[0])
            if not b_id:
                return False, "Binding ditemukan tanpa ID"
            # Preserve existing server if not provided
            data[".id"] = b_id
            if not server and "server" in data:
                data.pop("server", None)
            res.set(**data)
            return True, "Binding diperbarui"
        # For new binding, include server only when explicitly specified
        res.add(**data)
        return True, "Binding dibuat"
    except RouterOsApiError as e:  # pragma: no cover
        logger.error(f"[BINDING] RouterOS error: {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"[BINDING] general error: {e}")
        return False, str(e)


def get_ip_binding_details(username_comment: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "API tidak tersedia."
        bindings = api.get_resource("/ip/hotspot/ip-binding").get(comment=username_comment)
        return True, bindings[0] if bindings else None, "Sukses"
    except Exception as e:
        return False, None, str(e)


def find_and_update_address_list_entry(
    list_name: str, address: str, new_comment: Optional[str] = None
) -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource("/ip/firewall/address-list")
        entries = res.get(address=address, list=list_name)
        if not entries:
            return False, "Entry tidak ditemukan"
        if new_comment and (entry_id := _get_item_id(entries[0])):
            res.set(id=entry_id, comment=new_comment)
            return True, "Entry diperbarui"
        return True, "Entry ditemukan (no change)"
    except Exception as e:
        return False, str(e)


def find_and_remove_static_lease_by_mac(mac: str) -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        leases_res = api.get_resource("/ip/dhcp-server/lease")
        leases = leases_res.get(**{"mac-address": mac})
        removed = 0
        for lease in leases:
            if lease.get("dynamic") == "false":
                if l_id := _get_item_id(lease):
                    leases_res.remove(id=l_id)
                    removed += 1
        return True, f"Removed {removed} static leases"
    except Exception as e:
        return False, str(e)


def create_static_lease(ip: str, mac: str, comment: str) -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        leases_res = api.get_resource("/ip/dhcp-server/lease")

        # Ambil semua lease untuk MAC ini
        by_mac = leases_res.get(**{"mac-address": mac})

        # Tentukan DHCP server yang tepat (hindari memaksa 'all')
        server_name: Optional[str] = None
        try:
            # Prefer server dari lease yang sudah ada untuk MAC ini
            for lease in by_mac:
                srv = lease.get('server')
                if srv and str(srv).lower() != 'all':
                    server_name = srv
                    break
            # Jika belum diketahui, coba dari lease berdasarkan IP
            if not server_name and ip:
                by_ip = leases_res.get(address=ip)
                for lease in by_ip:
                    srv = lease.get('server')
                    if srv and str(srv).lower() != 'all':
                        server_name = srv
                        break
        except Exception:
            # Silent fallback
            server_name = server_name or None

        # Jika belum ada server_name, coba petakan IP ke network DHCP untuk mendapatkan server
        if not server_name and ip:
            try:
                # Ambil daftar network dan server DHCP
                dhcp_net_res = api.get_resource("/ip/dhcp-server/network")
                dhcp_srv_res = api.get_resource("/ip/dhcp-server")
                networks = dhcp_net_res.get()
                servers = dhcp_srv_res.get()

                # Build mapping network -> server via subnet match (best-effort)
                def ip_to_int(addr: str) -> int:
                    parts = [int(p) for p in addr.split('.')]
                    return (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]

                def cidr_to_netmask(prefix: int) -> int:
                    return (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF

                target = ip_to_int(ip)
                best_prefix = -1
                chosen_network = None
                for net in networks:
                    addr = net.get('address')  # e.g., '192.168.88.0/24'
                    if not addr or '/' not in addr:
                        continue
                    net_ip, pref = addr.split('/')
                    try:
                        pref_i = int(pref)
                        n_int = ip_to_int(net_ip)
                        mask = cidr_to_netmask(pref_i)
                        if (target & mask) == (n_int & mask):
                            if pref_i > best_prefix:
                                best_prefix = pref_i
                                chosen_network = addr
                    except Exception:
                        continue

                # If we have a chosen network, try to guess server by pool; else leave None
                if chosen_network:
                    pool_name = None
                    try:
                        for net in networks:
                            if net.get('address') == chosen_network:
                                pool_name = net.get('address-pool')
                                break
                    except Exception:
                        pool_name = None
                    if pool_name:
                        for srv in servers:
                            if srv.get('address-pool') == pool_name:
                                candidate = srv.get('name') or srv.get('id')
                                if candidate and str(candidate).lower() != 'all':
                                    server_name = candidate
                                    break
                    if not server_name and len(servers) == 1:
                        candidate = servers[0].get('name') or servers[0].get('id')
                        if candidate and str(candidate).lower() != 'all':
                            server_name = candidate
            except Exception:
                # Ignore mapping failures
                pass

        # Fallback ke konfigurasi default jika tersedia
        if not server_name:
            try:
                server_name = current_app.config.get('MIKROTIK_DEFAULT_DHCP_SERVER') or None
            except Exception:
                server_name = None

        updated = False
        messages: list[str] = []
        primary_id: Optional[str] = None
        previous_ips: list[str] = []

        # Jika ada lease untuk MAC ini, normalisasi: jadikan static, update address/comment (dan server bila diketahui)
        for lease in by_mac:
            l_id = _get_item_id(lease)
            if not l_id:
                continue
            if primary_id is None:
                primary_id = l_id
            current_addr = lease.get('address')
            current_comment = lease.get('comment', '') or ''
            is_dynamic = str(lease.get('dynamic', '')).lower() in ("true", "yes", "1")

            if current_addr and current_addr != ip:
                previous_ips.append(current_addr)

            # Convert dynamic -> static jika perlu
            if is_dynamic:
                try:
                    if hasattr(leases_res, 'call'):
                        leases_res.call('make-static', {'numbers': l_id})
                    else:
                        leases_res.set(id=l_id, disabled='no')
                    messages.append(f"made-static:{l_id}")
                    updated = True
                    is_dynamic = False
                except Exception as me:
                    logger.debug(f"[LEASE] make-static failed for {l_id}: {me}")

            # Update address/comment (dan server jika ada)
            try:
                set_fields: Dict[str, Any] = {}
                if ip and current_addr != ip:
                    set_fields['address'] = ip
                if comment and current_comment != comment:
                    set_fields['comment'] = comment
                if server_name:
                    set_fields['server'] = server_name
                if set_fields:
                    # Jangan pernah set server=all; hapus field bila demikian
                    if set_fields.get('server', '').lower() == 'all':
                        set_fields.pop('server', None)
                    leases_res.set(id=l_id, **set_fields)
                    messages.append(f"updated:{l_id}:{set_fields}")
                    updated = True
            except Exception as se:
                logger.debug(f"[LEASE] set failed for {l_id}: {se}")

        # Bila tidak ada lease sama sekali untuk MAC ini, buat baru sebagai static
        if not by_mac:
            add_fields: Dict[str, Any] = {"address": ip, "mac-address": mac, "comment": comment}
            if server_name and str(server_name).lower() != 'all':
                add_fields['server'] = server_name
            try:
                leases_res.add(**add_fields)
            except Exception as add_e:
                # Jika gagal tanpa server, coba lagi dengan default server jika ada
                if not server_name:
                    try:
                        default_srv = current_app.config.get('MIKROTIK_DEFAULT_DHCP_SERVER')
                    except Exception:
                        default_srv = None
                    if default_srv and str(default_srv).lower() != 'all':
                        add_fields['server'] = default_srv
                        leases_res.add(**add_fields)
                else:
                    raise add_e
            messages.append("created:new-static")
            updated = True

        # Cleanup: hapus static duplicates lain untuk MAC yang sama (selain primary)
        if by_mac:
            try:
                for lease in by_mac:
                    l_id = _get_item_id(lease)
                    if not l_id or (primary_id and l_id == primary_id):
                        continue
                    is_dyn = str(lease.get('dynamic', '')).lower() in ("true", "yes", "1")
                    if not is_dyn:
                        try:
                            leases_res.remove(id=l_id)
                            messages.append(f"removed-duplicate:{l_id}")
                        except Exception:
                            pass
            except Exception:
                pass

        # Invalidate caches untuk IP lama/baru
        try:
            for ipx in set(previous_ips + ([ip] if ip else [])):
                try:
                    from .mikrotik_cache import invalidate_ip_cache  # type: ignore
                    invalidate_ip_cache(ipx)
                except Exception:
                    pass
        except Exception:
            pass

        return True, "; ".join(messages) if messages else "Lease ensured"
    except Exception as e:
        return False, str(e)


def purge_user_from_hotspot(username: str) -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        messages: List[str] = []
        # active
        active = api.get_resource("/ip/hotspot/active").get(user=username)
        if active and (sid := _get_item_id(active[0])):
            api.get_resource("/ip/hotspot/active").remove(id=sid)
            messages.append("Active session removed")
        # binding -> host -> user cleanup
        if bindings := api.get_resource("/ip/hotspot/ip-binding").get(comment=username):
            b = bindings[0]
            mac = b.get("mac-address")
            b_id = _get_item_id(b)
            if mac:
                hosts = api.get_resource("/ip/hotspot/host").get(**{"mac-address": mac})
                if hosts and (hid := _get_item_id(hosts[0])):
                    api.get_resource("/ip/hotspot/host").remove(id=hid)
                    messages.append("Host removed")
            if b_id:
                api.get_resource("/ip/hotspot/ip-binding").remove(id=b_id)
                messages.append("Binding removed")
        if users := api.get_resource("/ip/hotspot/user").get(name=username):
            if uid := _get_item_id(users[0]):
                api.get_resource("/ip/hotspot/user").remove(id=uid)
                messages.append("User removed")
        if not messages:
            return True, f"Tidak ada jejak untuk {username}"
        return True, "; ".join(messages)
    except Exception as e:
        return False, str(e)


def purge_user_from_hotspot_by_comment(comment: str) -> Tuple[bool, str]:
    return purge_user_from_hotspot(comment)

# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_host_details_by_ip(ip_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not ip_address:
        return False, None, "IP Address tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "API tidak tersedia."
        hosts = api.get_resource("/ip/hotspot/host").get(address=ip_address)
        return True, hosts[0] if hosts else None, "Sukses"
    except Exception as e:
        return False, None, str(e)


def get_host_details_by_mac(mac_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "API tidak tersedia."
        hosts = api.get_resource("/ip/hotspot/host").get(**{"mac-address": mac_address})
        return True, hosts[0] if hosts else None, "Sukses"
    except Exception as e:
        return False, None, str(e)


def get_mac_from_dhcp_lease(ip_address: str) -> Tuple[bool, Optional[str], str]:
    if not ip_address:
        return False, None, "IP Address tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "API tidak tersedia."
        leases = api.get_resource("/ip/dhcp-server/lease").get(address=ip_address, status="bound")
        if not leases:
            return True, None, "Lease tidak ditemukan."
        mac_address = leases[0].get("mac-address")
        return True, mac_address, "Sukses"
    except Exception as e:
        return False, None, str(e)


def get_active_session_by_ip(ip_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not ip_address:
        return False, None, "IP Address tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "API tidak tersedia."
        sessions = api.get_resource("/ip/hotspot/active").get(address=ip_address)
        return True, sessions[0] if sessions else None, "Sukses"
    except Exception as e:
        return False, None, str(e)


def delete_ip_binding_by_comment(comment: str) -> Tuple[bool, str]:
    if not comment:
        return False, "Komentar tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource("/ip/hotspot/ip-binding")
        binds = res.get(comment=comment)
        if not binds:
            return True, "IP Binding tidak ditemukan."
        if b_id := _get_item_id(binds[0]):
            res.remove(id=b_id)
            return True, "IP Binding dihapus."
        return False, "Binding tanpa ID"
    except Exception as e:
        return False, str(e)


def remove_active_hotspot_user_by_ip(ip_address: str) -> bool:
    if not ip_address:
        return False
    try:
        api = _get_api_from_pool()
        if api is None:
            return False
        active = api.get_resource("/ip/hotspot/active").get(address=ip_address)
        if not active:
            return True
        for a in active:
            if aid := a.get("id") or a.get(".id"):
                api.get_resource("/ip/hotspot/active").remove(id=aid)
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# MAC Detection (Simplified: Host -> DHCP -> ARP + Grace Cache)
# ---------------------------------------------------------------------------
_last_positive_mac: Dict[str, Tuple[str, float]] = {}  # ip -> (mac, ts)
_last_positive_mac_lock = threading.RLock()
_adaptive_force_counts: Dict[str, List[float]] = collections.defaultdict(list)  # ip -> timestamps of force_refresh

# Metrics counters (simple in-memory; optional exposure via /metrics route)
_metrics = {
    'mac_lookup_total': 0,
    'mac_lookup_cache_hits': 0,
    'mac_lookup_cache_grace_hits': 0,
    'mac_lookup_fail': 0,
    'mac_lookup_duration_ms_sum': 0.0,
    # histogram buckets dynamic: counts stored under mac_lookup_duration_bucket_{le}
    # Prometheus style aliases (seconds & count) ditambahkan saat expose
}
_histogram_buckets: List[float] = []

def _init_histogram_buckets():
    global _histogram_buckets
    if _histogram_buckets:
        return
    raw = str(_safe_cfg('METRICS_LATENCY_BUCKETS', '5,10,25,50,100,250,500,1000,2000'))
    buckets = []
    for p in raw.split(','):
        try:
            buckets.append(float(p.strip()))
        except Exception:
            pass
    buckets = sorted(set(buckets))
    if not buckets or buckets[-1] != float('inf'):
        buckets.append(float('inf'))
    _histogram_buckets = buckets

def _record_histogram(duration_ms: float):
    _init_histogram_buckets()
    for le in _histogram_buckets:
        key = f'mac_lookup_duration_bucket_{int(le) if le != float("inf") else "inf"}'
        if key not in _metrics:
            _metrics[key] = 0
        if duration_ms <= le:
            _metrics[key] += 1
    # also count total observations (alias of mac_lookup_total already)

def get_internal_metrics_snapshot() -> Dict[str, Any]:
    # Ensure histogram buckets initialized even if no observation yet
    _init_histogram_buckets()
    for le in _histogram_buckets:
        key = f'mac_lookup_duration_bucket_{int(le) if le != float("inf") else "inf"}'
        if key not in _metrics:
            _metrics[key] = 0
    snap = dict(_metrics)
    # Gauge: grace cache size
    try:
        snap['mac_grace_cache_size'] = len(_last_positive_mac)
    except Exception:
        snap['mac_grace_cache_size'] = 0
    # Failure ratio gauge (computed, not stored): fail / total
    total = snap.get('mac_lookup_total', 0) or 0
    fails = snap.get('mac_lookup_fail', 0) or 0
    snap['mac_lookup_failure_ratio'] = (fails / total) if total > 0 else 0.0
    # Tambahkan alias prom style: mac_lookup_duration_seconds_bucket & _sum/_count
    # Konversi ms -> seconds untuk _sum
    total_seconds = snap.get('mac_lookup_duration_ms_sum', 0.0) / 1000.0
    snap['mac_lookup_duration_seconds_sum'] = total_seconds
    # _count = mac_lookup_total
    snap['mac_lookup_duration_seconds_count'] = snap.get('mac_lookup_total', 0)
    # bucket alias
    for k,v in list(snap.items()):
        if k.startswith('mac_lookup_duration_bucket_'):
            le = k.split('_')[-1]
            snap[f'mac_lookup_duration_seconds_bucket_{le}'] = v
    return snap

def _record_metric(name: str, value: float = 1.0):
    if name in _metrics:
        if name.endswith('_sum'):
            _metrics[name] += value
        else:
            _metrics[name] += value

def _suppressable_log(level: str, message: str):
    threshold = int(_safe_cfg('LOG_SUPPRESSION_THRESHOLD', 20))
    window = int(_safe_cfg('LOG_SUPPRESSION_WINDOW_SECONDS', 300))
    now = time.time()
    state = _log_suppression_state
    if state['first_ts'] == 0:
        state['first_ts'] = now
    if now - state['first_ts'] > window:
        # reset window
        state['first_ts'] = now
        state['errors'] = 0
    state['errors'] += 1
    logger_method = getattr(logger, level, logger.info)
    if state['errors'] <= threshold:
        logger_method(message)
    elif state['errors'] == threshold + 1:
        logger_method(f"[LOG-SUPPRESS] Threshold reached, further similar messages suppressed (window {window}s)")



def _safe_cfg(key: str, default: Any) -> Any:
    try:  # current_app mungkin tidak tersedia di beberapa unit test sederhana
        return current_app.config.get(key, default)  # type: ignore
    except Exception:
        return default


def find_mac_by_ip_comprehensive(ip_address: str, force_refresh: bool = False) -> Tuple[bool, Optional[str], str]:
    """Cari MAC untuk IP dengan rantai minimal dan cache bijak.

    Urutan:
      1. In-memory grace positive cache (_last_positive_mac)
      2. Redis cache (via get_cached_mac_by_ip)
      3. Host table (/ip/hotspot/host)
      4. DHCP lease (/ip/dhcp-server/lease)
      5. ARP table (/ip/arp)

    Dihilangkan: active sessions, ping, binding, bridge FDB, DNS (diminta user agar lebih ringan & senyap).

    Grace positive cache: jika pernah dapat MAC valid, kita simpan di memori untuk X detik
    (MAC_POSITIVE_GRACE_SECONDS) agar refresh page tidak bikin flicker / None sementara.
    """
    if not ip_address:
        return False, None, "IP Address tidak boleh kosong."

    now = time.time()
    grace_seconds = _safe_cfg('MAC_POSITIVE_GRACE_SECONDS', 90)

    # 1. In-memory grace cache (skip jika force_refresh namun tetap fallback jika gagal)
    with _last_positive_mac_lock:
        grace_entry = _last_positive_mac.get(ip_address)
    if grace_entry and (now - grace_entry[1] <= grace_seconds) and not force_refresh:
        _record_metric('mac_lookup_cache_grace_hits')
        return True, grace_entry[0], 'Grace Cache'

    # 2. Redis / persistent cache (kecuali explicit force_refresh)
    redis_cached: Optional[Tuple[bool, Optional[str], str]] = None
    if not force_refresh:
        redis_cached = get_cached_mac_by_ip(ip_address)
        if redis_cached and redis_cached[0] and redis_cached[1]:
            # perbarui grace cache timestamp
            with _last_positive_mac_lock:
                _last_positive_mac[ip_address] = (redis_cached[1], now)
            _record_metric('mac_lookup_cache_hits')
            return True, redis_cached[1], redis_cached[2]
        # Jika redis negative, lanjutkan pencarian tanpa early return

    if force_refresh:
        # Invalidate hanya redis; grace positif tetap dipakai untuk fallback akhir
        invalidate_ip_cache(ip_address)

    lookup_start = now
    _record_metric('mac_lookup_total')
    try:
        api = _get_api_from_pool()
        if api is None:
            if grace_entry and (now - grace_entry[1] <= grace_seconds):
                return True, grace_entry[0], 'Grace Cache (offline)'
            return False, None, 'Tidak dapat terhubung ke MikroTik'

        def cache_and_return(mac: str, source: str, ttl: int) -> Tuple[bool, str, str]:
            res: Tuple[bool, str, str] = (True, mac, source)
            cache_mac_by_ip(ip_address, *res, ttl=ttl)
            with _last_positive_mac_lock:
                _last_positive_mac[ip_address] = (mac, time.time())
                _enforce_grace_cap()
            return res

        positive_ttl = int(_safe_cfg('MAC_LOOKUP_CACHE_TTL', 300))
        # Adaptive grace reduction: jika IP sering force_refresh,
        if force_refresh:
            force_window = int(_safe_cfg('MAC_GRACE_FORCE_WINDOW_SECONDS', 300))
            adapt_decay = int(_safe_cfg('MAC_GRACE_ADAPT_DECAY', 5))
            min_grace = int(_safe_cfg('MAC_GRACE_MIN_SECONDS', 15))
            with _last_positive_mac_lock:
                ts_list = _adaptive_force_counts[ip_address]
                ts_list.append(now)
                # prune
                _adaptive_force_counts[ip_address] = [t for t in ts_list if now - t <= force_window]
                force_count = len(_adaptive_force_counts[ip_address])
            # Set dynamic grace: base - (force_count * decay) not below min
            dynamic_grace = max(min_grace, grace_seconds - force_count * adapt_decay)
            grace_seconds = dynamic_grace

        # 3. Host table
        parallel_enabled = bool(_safe_cfg('MIKROTIK_LOOKUP_PARALLEL', False))
        lookup_funcs: List[Tuple[str, Callable[[], Optional[str]], int]] = []

        def host_lookup() -> Optional[str]:
            try:
                hosts = api.get_resource('/ip/hotspot/host').get(address=ip_address)
                if hosts and (mac := hosts[0].get('mac-address')):
                    cache_and_return(mac, 'Host Table', positive_ttl)
                    return mac
            except Exception:
                return None
            return None

        def dhcp_lookup() -> Optional[str]:
            try:
                leases = api.get_resource('/ip/dhcp-server/lease').get(address=ip_address)
                for lease in leases:
                    mac = lease.get('mac-address'); status = lease.get('status', '')
                    if mac and status in ('bound', 'waiting'):
                        cache_and_return(mac, 'DHCP Lease', positive_ttl)
                        return mac
            except Exception:
                return None
            return None

        def arp_lookup() -> Optional[str]:
            try:
                arp_entries = api.get_resource('/ip/arp').get(address=ip_address)
                for entry in arp_entries:
                    mac = entry.get('mac-address')
                    if mac and mac != '00:00:00:00:00:00':
                        cache_and_return(mac, 'ARP Table', int(_safe_cfg('MAC_ARP_TTL', 180)))
                        return mac
            except Exception:
                return None
            return None

        # Async mode wrapper (thread pool) jika diaktifkan – membungkus sequential logic; parallel logic tetap prioritas.
        async_mode = bool(_safe_cfg('MIKROTIK_ASYNC_MODE', False))
        if parallel_enabled:
            # Jalankan paralel (thread ringan) dan race untuk pertama yang berhasil
            result_holder: Dict[str, Optional[str]] = {'mac': None}
            done_event = threading.Event()
            def runner(fn: Callable[[], Optional[str]]):
                if done_event.is_set():
                    return
                r = fn()
                if r and not done_event.is_set():
                    result_holder['mac'] = r
                    done_event.set()
            threads = [threading.Thread(target=runner, args=(f,), daemon=True) for f in (host_lookup, dhcp_lookup, arp_lookup)]
            for t in threads: t.start()
            done_event.wait(timeout=float(_safe_cfg('MIKROTIK_READ_TIMEOUT_SECONDS', 5)))
            # join dengan timeout kecil agar tidak block lama
            for t in threads: t.join(timeout=0.05)
            if result_holder['mac']:
                # cache sudah dilakukan di masing-masing lookup
                return True, result_holder['mac'], 'Parallel'
        elif async_mode:
            # Offload sequential chain ke thread pool
            from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
            with ThreadPoolExecutor(max_workers=3) as executor:
                futs = [executor.submit(fn) for fn in (host_lookup, dhcp_lookup, arp_lookup)]
                done, pending = wait(futs, timeout=float(_safe_cfg('MIKROTIK_READ_TIMEOUT_SECONDS', 5)), return_when=FIRST_COMPLETED)
                for d in done:
                    mac = d.result()
                    if mac:
                        # cache sudah terjadi di lookup
                        # cancel others
                        for p in pending:
                            p.cancel()
                        return True, mac, 'Async'
                # If none succeeded within timeout, allow remaining to finish quickly
                for p in pending:
                    try:
                        p.result(timeout=0.05)
                    except Exception:
                        pass
                # Fallback sequential check (maybe completed without returning)
                for d in futs:
                    try:
                        mac = d.result(timeout=0.01)
                        if mac:
                            return True, mac, 'Async'
                    except Exception:
                        pass
        else:
            # Sequential fallback (host -> dhcp -> arp)
            if host_lookup():
                return True, _last_positive_mac[ip_address][0], 'Host Table'
            if dhcp_lookup():
                return True, _last_positive_mac[ip_address][0], 'DHCP Lease'
            if arp_lookup():
                return True, _last_positive_mac[ip_address][0], 'ARP Table'

        elapsed_ms = round((time.time() - lookup_start) * 1000, 2)
        _record_metric('mac_lookup_duration_ms_sum', elapsed_ms)
        _record_histogram(elapsed_ms)
        # Negative cache pendek agar percobaan berikutnya bisa cepat recover
        cache_mac_by_ip(ip_address, True, None, f'Not found ({elapsed_ms}ms)', ttl=int(_safe_cfg('MAC_NEGATIVE_TTL', 20)))

        # Fallback terakhir: grace positif yang masih valid walau lookup gagal
        if grace_entry and (now - grace_entry[1] <= grace_seconds):
            return True, grace_entry[0], 'Grace Cache (stale)'
        return True, None, f'Not found ({elapsed_ms}ms)'
    except Exception as e:  # pragma: no cover
        _record_metric('mac_lookup_fail')
        if grace_entry and (now - grace_entry[1] <= grace_seconds):
            return True, grace_entry[0], 'Grace Cache (error)'
        return False, None, f'Error: {e}'

# ---------------------------------------------------------------------------
# Public Exports
# ---------------------------------------------------------------------------
def _enforce_grace_cap():
    """Pastikan _last_positive_mac tidak tumbuh tanpa batas (LRU sederhana)."""
    try:
        max_entries = int(_safe_cfg('MIKROTIK_GRACE_MAX_ENTRIES', 1000))
    except Exception:
        max_entries = 1000
    if max_entries <= 0:
        return
    with _last_positive_mac_lock:
        if len(_last_positive_mac) <= max_entries:
            return
        # sort by timestamp ascending, drop oldest 10% atau setidaknya 1
        items = sorted(_last_positive_mac.items(), key=lambda x: x[1][1])
        to_remove = max(1, int(len(items) * 0.1))
        for k, _ in items[:to_remove]:
            _last_positive_mac.pop(k, None)

__all__ = [
    'find_mac_by_ip_comprehensive', 'disable_ip_binding_by_comment', 'create_or_update_ip_binding',
    'get_ip_binding_details', 'find_and_update_address_list_entry', 'find_and_remove_static_lease_by_mac',
    'create_static_lease', 'purge_user_from_hotspot', 'purge_user_from_hotspot_by_comment',
    'get_host_details_by_ip', 'get_host_details_by_mac', 'get_mac_from_dhcp_lease', 'get_active_session_by_ip',
    'delete_ip_binding_by_comment', 'remove_active_hotspot_user_by_ip', '_get_api_from_pool',
    'set_hotspot_user_profile', 'ensure_ip_binding_status_matches_profile',
    'activate_or_update_hotspot_user', 'add_ip_to_address_list', 'remove_ip_from_address_list',
    'get_mikrotik_connection', 'delete_hotspot_user', 'format_to_local_phone'
]

# ---------------------------------------------------------------------------
# Additional functions required by tasks / routes (ported from legacy)
# ---------------------------------------------------------------------------

def activate_or_update_hotspot_user(user_mikrotik_username: str, mikrotik_profile_name: str,
                                    hotspot_password: Optional[str], **kwargs) -> Tuple[bool, str]:
    """Create or update hotspot user (simple version).

    Args:
        user_mikrotik_username: Nama user hotspot.
        mikrotik_profile_name: Profil target (aktif/fup/habis/blokir dst.)
        hotspot_password: Password baru (wajib jika user belum ada)
        kwargs: server, comment
    """
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        user_res = api.get_resource('/ip/hotspot/user')
        existing = user_res.get(name=user_mikrotik_username)
        server = kwargs.get('server', 'all')
        comment = kwargs.get('comment', '')
        if existing:
            uid = _get_item_id(existing[0])
            if not uid:
                return False, 'User tanpa ID'
            data = {'.id': uid, 'profile': mikrotik_profile_name, 'server': server, 'comment': comment, 'disabled': 'no'}
            if hotspot_password:
                data['password'] = hotspot_password
            user_res.set(**data)
            return True, 'User diperbarui'
        if not hotspot_password:
            return False, 'Password wajib untuk membuat user baru'
        user_res.add(name=user_mikrotik_username, password=hotspot_password, profile=mikrotik_profile_name,
                     server=server, comment=comment)
        return True, 'User dibuat'
    except Exception as e:
        logger.error(f"[USER] activate/update error: {e}")
        return False, str(e)


def set_hotspot_user_profile(username: str, new_profile_name: str) -> Tuple[bool, str]:
    """Update hanya profile user hotspot jika ada."""
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource('/ip/hotspot/user')
        users = res.get(name=username)
        if not users:
            return False, 'User tidak ditemukan'
        uid = _get_item_id(users[0])
        if not uid:
            return False, 'User tanpa ID'
        res.set(id=uid, profile=new_profile_name)
        return True, 'Profil diperbarui'
    except Exception as e:
        return False, str(e)


def ensure_ip_binding_status_matches_profile(username: str, profile_name: str) -> Tuple[bool, str]:
    """Ensure binding disabled flag reflects profile (blokir -> disabled)."""
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, "API tidak tersedia."
        res = api.get_resource('/ip/hotspot/ip-binding')
        bindings = res.get(comment=username)
        if not bindings:
            return True, 'Tidak ada binding'
        b = bindings[0]
        bid = _get_item_id(b)
        if not bid:
            return False, 'Binding tanpa ID'
        should_disable = 'yes' if profile_name == current_app.config.get('MIKROTIK_PROFILE_BLOKIR') else 'no'
        if b.get('disabled') != should_disable:
            res.set(id=bid, disabled=should_disable)
            return True, f"Binding diset disabled={should_disable}"
        return True, 'Binding sudah konsisten'
    except Exception as e:
        return False, str(e)


def add_ip_to_address_list(list_name: str, address: str, comment: str = '') -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, 'API tidak tersedia.'
        res = api.get_resource('/ip/firewall/address-list')
        if not res.get(address=address, list=list_name):
            res.add(address=address, list=list_name, comment=comment)
            return True, 'Ditambahkan'
        return True, 'Sudah ada'
    except Exception as e:
        return False, str(e)


def remove_ip_from_address_list(list_name: str, address: str) -> Tuple[bool, str]:
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, 'API tidak tersedia.'
        res = api.get_resource('/ip/firewall/address-list')
        entries = res.get(address=address, list=list_name)
        removed = 0
        for entry in entries:
            if eid := _get_item_id(entry):
                res.remove(id=eid)
                removed += 1
        return True, f'Removed {removed}' if removed else 'Tidak ada'
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Legacy helpers referenced by CLI commands
# ---------------------------------------------------------------------------
from contextlib import contextmanager
import re as _re

@contextmanager
def get_mikrotik_connection():  # yields low-level API for manual batch ops
    api = None
    try:
        api = _get_api_from_pool()
        yield api
    finally:  # no explicit close because pool reused; placeholder for future
        api = None  # noqa: F841


def delete_hotspot_user(api: Any, username: str) -> Tuple[bool, str]:
    try:
        if not api:
            return False, 'API tidak tersedia'
        res = api.get_resource('/ip/hotspot/user')
        users = res.get(name=username)
        if not users:
            return True, 'User tidak ada'
        if uid := _get_item_id(users[0]):
            res.remove(id=uid)
            return True, 'User dihapus'
        return False, 'User tanpa ID'
    except Exception as e:
        return False, str(e)


_PHONE_LOCAL_RE = _re.compile(r'^(\+62|62|0)')
def format_to_local_phone(phone: str) -> Optional[str]:
    if not phone:
        return None
    # Normalisasi ke format 08xxxxxxxx
    p = phone.strip()
    p = _PHONE_LOCAL_RE.sub('0', p)
    # Basic validation
    return p if p.startswith('08') else None
