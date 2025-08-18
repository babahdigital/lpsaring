# backend/app/infrastructure/gateways/mikrotik_client_core.py
"""Core implementation extracted from former mikrotik_client.py to avoid
package/file name collision that caused `cannot import name 'mikrotik_client'` errors
when the package directory (with __init__.py) and module co-existed.

Only the functions referenced by the lazy wrapper and other modules are kept.
Heavy comments and legacy blocks trimmed for brevity. (Original file ~1200 LOC)

NOTE: If new functions are added that must be exposed via the public wrapper,
import and re‑export them in `mikrotik_client/__init__.py` (lazy wrapper).
"""
from __future__ import annotations
import logging, time, threading
from typing import Optional, Any, Tuple, List, Dict
from functools import lru_cache

from flask import current_app
from routeros_api.api import RouterOsApi  # type: ignore
from routeros_api.exceptions import RouterOsApiError  # type: ignore
from .mikrotik_cache import get_cached_mac_by_ip, cache_mac_by_ip, invalidate_ip_cache

logger = logging.getLogger(__name__)

_connection_pool_lock = threading.RLock()
_global_connection_pool = None
_last_connection_time = 0
_connection_error_count = 0
_MAX_ERROR_COUNT = 5
_CONNECTION_COOLDOWN = 60

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_connection_config():
    try:
        import os
        from config import config_options  # type: ignore
        flask_env = os.environ.get('FLASK_ENV', 'development')
        app_config = config_options[flask_env]
        return {
            'host': os.environ.get('MIKROTIK_HOST', app_config.MIKROTIK_HOST),
            'username': os.environ.get('MIKROTIK_USERNAME', app_config.MIKROTIK_USERNAME),
            'password': os.environ.get('MIKROTIK_PASSWORD', app_config.MIKROTIK_PASSWORD),
            'port': int(os.environ.get('MIKROTIK_PORT', app_config.MIKROTIK_PORT)),
            'use_ssl': os.environ.get('MIKROTIK_USE_SSL', str(getattr(app_config, 'MIKROTIK_USE_SSL', 'false'))).lower() == 'true',
            'plaintext_login': True,
        }
    except Exception as e:  # pragma: no cover
        logger.error(f"Error getting connection config: {e}")
        return {'host':'172.16.0.1','username':'hotspot','password':'','port':8728,'use_ssl':False,'plaintext_login':True}


def _create_connection_pool():
    global _global_connection_pool, _last_connection_time, _connection_error_count
    import routeros_api  # type: ignore
    cfg = _get_connection_config()
    logger.info(f"Creating MikroTik pool to {cfg['host']}:{cfg['port']}")
    try:
        pool = routeros_api.RouterOsApiPool(
            host=cfg['host'], username=cfg['username'], password=cfg['password'],
            use_ssl=cfg['use_ssl'], port=cfg['port'], plaintext_login=cfg['plaintext_login'])
        if pool.get_api():
            _last_connection_time = time.time()
            _connection_error_count = 0
            return pool
    except Exception as e:
        _connection_error_count += 1
        logger.error(f"Failed to create MikroTik pool: {e}")
    return None


def _get_api_from_pool(pool_name=None) -> Optional[RouterOsApi]:  # noqa: D401
    global _global_connection_pool, _last_connection_time, _connection_error_count
    try:
        from flask import current_app as _ca
        pool = getattr(_ca, 'mikrotik_api_pool', None)
        if pool:
            try:
                return pool.get_api()
            except Exception as e:
                logger.warning(f"App context pool error: {e}")
    except Exception:
        pass
    if (_connection_error_count >= _MAX_ERROR_COUNT and time.time() - _last_connection_time < _CONNECTION_COOLDOWN):
        return None
    with _connection_pool_lock:
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
    return None

# ---------------------------------------------------------------------------
# Utility helpers referenced externally
# ---------------------------------------------------------------------------

def _get_item_id(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    return item.get('.id') or item.get('id')

# ---------------------------------------------------------------------------
# Core public functions (subset retained)
# ---------------------------------------------------------------------------

def get_active_session_by_ip(ip_address: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not ip_address: return False, None, "IP Address tidak boleh kosong."
    try:
        api = _get_api_from_pool()
        if api is None: return False, None, "Tidak dapat terhubung ke MikroTik"
        sessions = api.get_resource('/ip/hotspot/active').get(address=ip_address)
        return True, sessions[0] if sessions else None, "Sukses"
    except Exception as e:
        logger.error(f"Error get_active_session_by_ip {ip_address}: {e}")
        return False, None, str(e)

# Minimal subset of earlier detection chain for emergency fallback use
# (Full advanced chain lives in original file; kept simplified here.)

def find_mac_by_ip_comprehensive(ip_address: str, force_refresh: bool = False) -> Tuple[bool, Optional[str], str]:
    if not ip_address:
        return False, None, "IP Address tidak boleh kosong."
    if force_refresh:
        invalidate_ip_cache(ip_address)
    cached = get_cached_mac_by_ip(ip_address)
    if cached and not force_refresh:
        return cached
    start = time.time()
    try:
        api = _get_api_from_pool()
        if api is None:
            return False, None, "Tidak dapat terhubung ke MikroTik"
        # Host table
        try:
            hosts = api.get_resource('/ip/hotspot/host').get(address=ip_address)
            if hosts:
                mac = hosts[0].get('mac-address')
                if mac:
                    res = (True, mac, 'Host Table')
                    cache_mac_by_ip(ip_address, *res, ttl=300)
                    return res
        except Exception:
            pass
        # DHCP
        try:
            leases = api.get_resource('/ip/dhcp-server/lease').get(address=ip_address)
            for lease in leases:
                mac = lease.get('mac-address')
                if mac and lease.get('status') in ['bound','waiting']:
                    res = (True, mac, 'DHCP Lease')
                    cache_mac_by_ip(ip_address, *res, ttl=300)
                    return res
        except Exception:
            pass
        # ARP
        try:
            arp = api.get_resource('/ip/arp').get(address=ip_address)
            for entry in arp:
                mac = entry.get('mac-address')
                if mac and mac != '00:00:00:00:00:00':
                    res = (True, mac, 'ARP Table')
                    cache_mac_by_ip(ip_address, *res, ttl=180)
                    return res
        except Exception:
            pass
        elapsed = round((time.time()-start)*1000,2)
        res = (True, None, f"Not found ({elapsed}ms)")
        cache_mac_by_ip(ip_address, *res, ttl=30)
        return res
    except Exception as e:
        return False, None, f"Error: {e}"

# Expose helper for enhancement module
__all__ = [
    'find_mac_by_ip_comprehensive', 'get_active_session_by_ip',
    '_get_api_from_pool'
]
