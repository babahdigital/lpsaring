# backend/app/services/walled_garden_service.py
import json
import logging
from typing import List, Dict
from urllib.parse import urlparse

from flask import current_app

from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, sync_walled_garden_rules

logger = logging.getLogger(__name__)


def _get_list_setting(key: str) -> List[str]:
    value = settings_service.get_setting(key, "[]")
    if not value:
        return []
    if isinstance(value, str):
        val = value.strip()
        if val.startswith('[') and val.endswith(']'):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                val = val.strip('[]')
        if not val:
            return []
        return [item.strip().strip('"').strip("'") for item in val.split(',') if item.strip()]
    return []


def sync_walled_garden() -> Dict[str, str]:
    enabled = settings_service.get_setting('WALLED_GARDEN_ENABLED', 'False') == 'True'
    if not enabled:
        return {"status": "disabled"}

    allowed_hosts = _get_list_setting('WALLED_GARDEN_ALLOWED_HOSTS')
    allowed_ips = _get_list_setting('WALLED_GARDEN_ALLOWED_IPS')
    comment_prefix = settings_service.get_setting('WALLED_GARDEN_MANAGED_COMMENT_PREFIX', 'lpsaring')

    # Jika enabled tapi list host belum diset, isi default minimal agar captive portal bisa diakses.
    if not allowed_hosts:
        candidates: List[str] = []
        try:
            candidates.extend([
                str(current_app.config.get('APP_PUBLIC_BASE_URL') or ''),
                str(current_app.config.get('FRONTEND_URL') or ''),
                str(current_app.config.get('APP_LINK_USER') or ''),
            ])
        except Exception:
            candidates = []

        derived_hosts: List[str] = []
        for raw in candidates:
            value = (raw or '').strip()
            if not value:
                continue
            parsed = urlparse(value)
            host = (parsed.hostname or '').strip()
            if host:
                derived_hosts.append(host)

        # De-dup + urut stabil
        if derived_hosts:
            allowed_hosts = sorted({h for h in derived_hosts if h})

    with get_mikrotik_connection() as api:
        if not api:
            return {"status": "error", "message": "Koneksi MikroTik gagal"}
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
