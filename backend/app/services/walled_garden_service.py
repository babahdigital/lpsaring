# backend/app/services/walled_garden_service.py
import json
import logging
import socket
import ipaddress
from typing import List, Dict, Iterable
from urllib.parse import urlparse

from flask import current_app

from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, sync_walled_garden_rules

logger = logging.getLogger(__name__)

MIDTRANS_PRODUCTION_HOSTS = {"app.midtrans.com", "api.midtrans.com"}
MIDTRANS_SANDBOX_HOSTS = {"app.sandbox.midtrans.com", "api.sandbox.midtrans.com"}


def _get_list_setting(key: str) -> List[str]:
    value = settings_service.get_setting(key, "[]")
    if not value:
        return []
    if isinstance(value, str):
        val = value.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                val = val.strip("[]")
        if not val:
            return []
        return [item.strip().strip('"').strip("'") for item in val.split(",") if item.strip()]
    return []


def _get_bool_setting(key: str, default: bool) -> bool:
    raw = settings_service.get_setting(key, "True" if default else "False")
    if isinstance(raw, bool):
        return raw
    value = str(raw or "").strip().lower()
    if value in {"true", "1", "yes", "y", "on", "t"}:
        return True
    if value in {"false", "0", "no", "n", "off", "f"}:
        return False
    return default


def _extract_host(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").strip().lower()
    if not host and parsed.path:
        host = str(parsed.path).split("/")[0].strip().lower()
    return host


def _normalize_hosts(hosts: Iterable[str]) -> List[str]:
    normalized = {_extract_host(item) for item in (hosts or [])}
    return sorted(host for host in normalized if host)


def _derive_portal_hosts() -> List[str]:
    candidates: List[str] = []
    try:
        candidates.extend(
            [
                str(current_app.config.get("APP_PUBLIC_BASE_URL") or ""),
                str(current_app.config.get("FRONTEND_URL") or ""),
                str(current_app.config.get("APP_LINK_USER") or ""),
                str(current_app.config.get("APP_LINK_ADMIN") or ""),
                str(current_app.config.get("APP_LINK_ADMIN_CHANGE_PASSWORD") or ""),
                str(current_app.config.get("APP_LINK_MIKROTIK") or ""),
            ]
        )
    except Exception:
        return []
    return _normalize_hosts(candidates)


def _derive_external_hosts() -> List[str]:
    hosts: set[str] = set()

    if _get_bool_setting("WALLED_GARDEN_AUTO_INCLUDE_PORTAL_HOSTS", True):
        hosts.update(_derive_portal_hosts())

    if _get_bool_setting("WALLED_GARDEN_INCLUDE_MESSAGING_HOSTS", True):
        hosts.update(
            _normalize_hosts(
                [
                    settings_service.get_setting("WHATSAPP_API_URL", "") or "",
                    settings_service.get_setting("WHATSAPP_VALIDATE_URL", "") or "",
                    settings_service.get_setting("TELEGRAM_API_BASE_URL", "") or "",
                ]
            )
        )

    if _get_bool_setting("WALLED_GARDEN_INCLUDE_MIDTRANS_HOSTS", True):
        midtrans_is_prod = bool(current_app.config.get("MIDTRANS_IS_PRODUCTION", False))
        hosts.update(MIDTRANS_PRODUCTION_HOSTS if midtrans_is_prod else MIDTRANS_SANDBOX_HOSTS)

    hosts.update(_normalize_hosts(_get_list_setting("WALLED_GARDEN_EXTRA_EXTERNAL_URLS")))
    return sorted(hosts)


def _derive_private_ips_from_hosts(hosts: List[str]) -> List[str]:
    """Resolve hosts and return private (RFC1918) IPs only.

    Rationale: MikroTik walled-garden 'dst-host' can be unreliable for HTTPS depending
    on router configuration/versions, but 'dst-address' works reliably.
    We only auto-add PRIVATE IPs to avoid whitelisting large/variable public CDN ranges.
    """
    ips: set[str] = set()
    for host in hosts or []:
        h = str(host or "").strip()
        if not h:
            continue
        try:
            infos = socket.getaddrinfo(h, None)
        except Exception:
            continue
        for info in infos:
            try:
                addr = info[4][0]
                ip_obj = ipaddress.ip_address(str(addr))
                if ip_obj.is_private:
                    ips.add(str(ip_obj))
            except Exception:
                continue
    return sorted(ips)


def sync_walled_garden() -> Dict[str, str]:
    enabled = settings_service.get_setting("WALLED_GARDEN_ENABLED", "False") == "True"
    if not enabled:
        return {"status": "disabled"}

    allowed_hosts = _get_list_setting("WALLED_GARDEN_ALLOWED_HOSTS")
    allowed_ips = _get_list_setting("WALLED_GARDEN_ALLOWED_IPS")
    comment_prefix = settings_service.get_setting("WALLED_GARDEN_MANAGED_COMMENT_PREFIX", "lpsaring")

    # Tambahkan host eksternal penting secara otomatis agar portal/payment tetap bisa diakses
    # saat user belum login atau kuota sedang habis.
    if _get_bool_setting("WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS", True):
        allowed_hosts = sorted({*allowed_hosts, *_derive_external_hosts()})
    elif not allowed_hosts:
        allowed_hosts = _derive_portal_hosts()

    # Best-effort: if allowed_ips is empty, try to derive private IPs from allowed_hosts.
    # This supports setups where a local DNS entry maps the portal domain to a private IP.
    if not allowed_ips and allowed_hosts:
        try:
            derived_private_ips = _derive_private_ips_from_hosts(allowed_hosts)
            if derived_private_ips:
                allowed_ips = derived_private_ips
        except Exception:
            pass

    with get_mikrotik_connection() as api:
        if not api:
            return {"status": "error", "message": "Koneksi MikroTik gagal"}
        comment_prefix = comment_prefix or ""
        ok, msg = sync_walled_garden_rules(
            api_connection=api,
            allowed_hosts=allowed_hosts,
            allowed_ips=allowed_ips,
            comment_prefix=comment_prefix,
        )
        if not ok:
            logger.error(f"Gagal sync walled-garden: {msg}")
            return {"status": "error", "message": msg}

    return {"status": "success", "message": "Sukses"}
