# backend/app/services/device_management_service.py
import logging
import ipaddress
from urllib.parse import unquote
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import Optional, Tuple, Dict, Any

from flask import current_app
from app.utils.formatters import get_app_date_time_strings, format_to_local_phone
import sqlalchemy as sa

from app.extensions import db
from app.services import settings_service
from app.infrastructure.db.models import User, UserDevice
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_mac_by_ip,
    get_hotspot_user_ip,
    get_ip_by_mac,
    upsert_ip_binding,
    remove_ip_binding,
    upsert_dhcp_static_lease,
    remove_dhcp_lease,
    upsert_address_list_entry,
    remove_address_list_entry,
)
from app.services.access_policy_service import resolve_allowed_binding_type_for_user

logger = logging.getLogger(__name__)


def _is_mikrotik_operations_enabled() -> bool:
    try:
        raw = settings_service.get_setting('ENABLE_MIKROTIK_OPERATIONS', 'True')
        return str(raw or '').strip().lower() in {'true', '1', 't', 'yes'}
    except Exception:
        # fail-open: kalau settings service bermasalah jangan diam-diam mematikan MikroTik
        return True


def _get_settings() -> Dict[str, Any]:
    return {
        'ip_binding_enabled': settings_service.get_setting('IP_BINDING_ENABLED', 'True') == 'True',
        'ip_binding_type_allowed': settings_service.get_ip_binding_type_setting('IP_BINDING_TYPE_ALLOWED', 'regular'),
        'ip_binding_type_blocked': settings_service.get_ip_binding_type_setting('IP_BINDING_TYPE_BLOCKED', 'blocked'),
        'ip_binding_fail_open': settings_service.get_setting('IP_BINDING_FAIL_OPEN', 'False') == 'True',
        'dhcp_static_lease_enabled': settings_service.get_setting('MIKROTIK_DHCP_STATIC_LEASE_ENABLED', 'False') == 'True',
        'dhcp_lease_server_name': (settings_service.get_setting('MIKROTIK_DHCP_LEASE_SERVER_NAME', '') or '').strip(),
        'device_auto_replace_enabled': settings_service.get_setting('DEVICE_AUTO_REPLACE_ENABLED', 'False') == 'True',
        'max_devices': settings_service.get_setting_as_int('MAX_DEVICES_PER_USER', 3),
        'require_explicit': settings_service.get_setting('REQUIRE_EXPLICIT_DEVICE_AUTH', 'False') == 'True',
        'device_stale_days': settings_service.get_setting_as_int('DEVICE_STALE_DAYS', 30),
        'mikrotik_server_default': settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'all'),
    }


def _remove_managed_address_lists(ip_address: Optional[str]) -> None:
    """Hapus IP dari semua address-list yang dikelola aplikasi.

    Ini mengurangi kasus "stale list" saat IP device berubah (DHCP renew/roaming)
    tapi firewall masih memutus koneksi karena IP lama masih tercatat di list tertentu.
    """
    if not ip_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip managed address-list cleanup")
        return

    keys = [
        ('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked'),
        ('MIKROTIK_ADDRESS_LIST_ACTIVE', 'active'),
        ('MIKROTIK_ADDRESS_LIST_FUP', 'fup'),
        ('MIKROTIK_ADDRESS_LIST_HABIS', 'habis'),
        ('MIKROTIK_ADDRESS_LIST_EXPIRED', 'expired'),
        ('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive'),
    ]
    list_names = [settings_service.get_setting(k, d) or d for k, d in keys]
    list_names = [str(x).strip() for x in list_names if str(x or '').strip()]

    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk cleanup address-list")
            return
        for list_name in list_names:
            try:
                remove_address_list_entry(api_connection=api, address=ip_address, list_name=list_name)
            except Exception:
                logger.info("Gagal remove address-list: ip=%s list=%s", ip_address, list_name)


def _ensure_static_dhcp_lease(
    mac_address: Optional[str],
    ip_address: Optional[str],
    comment: str,
    server: Optional[str],
) -> None:
    if not mac_address or not ip_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip DHCP static lease")
        return
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk DHCP static lease")
            return
        ok, msg = upsert_dhcp_static_lease(
            api_connection=api,
            mac_address=mac_address,
            address=ip_address,
            comment=comment,
            server=server,
        )
        if not ok:
            logger.warning("Gagal upsert DHCP static lease: mac=%s ip=%s msg=%s", mac_address, ip_address, msg)


def _remove_dhcp_lease(mac_address: Optional[str], server: Optional[str]) -> None:
    if not mac_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip DHCP lease remove")
        return
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk remove DHCP lease")
            return
        ok, msg = remove_dhcp_lease(api_connection=api, mac_address=mac_address, server=server)
        if not ok:
            logger.warning("Gagal remove DHCP lease: mac=%s msg=%s", mac_address, msg)


def _normalize_mac(mac: str) -> str:
    value = mac.strip()
    if '%3A' in value or '%3a' in value or '%25' in value:
        value = unquote(value)
        if '%3A' in value or '%3a' in value:
            value = unquote(value)
    return value.replace('-', ':').upper()


def normalize_mac(mac: Optional[str]) -> Optional[str]:
    if not mac:
        return None
    return _normalize_mac(mac)


def _ensure_ip_binding(
    mac_address: str,
    ip_address: Optional[str],
    binding_type: str,
    comment: str,
    server: Optional[str]
) -> None:
    if not mac_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip ip-binding upsert")
        return
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk ip-binding")
            return
        upsert_ip_binding(
            api_connection=api,
            mac_address=mac_address,
            address=ip_address,
            server=server,
            binding_type=binding_type,
            comment=comment,
        )


def _ensure_blocked_address_list(ip_address: Optional[str], comment: str) -> None:
    if not ip_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip address-list blocked upsert")
        return
    list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk address-list blocked")
            return
        upsert_address_list_entry(api_connection=api, address=ip_address, list_name=list_blocked, comment=comment)


def _remove_blocked_address_list(ip_address: Optional[str]) -> None:
    if not ip_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip address-list blocked remove")
        return
    list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk remove address-list blocked")
            return
        remove_address_list_entry(api_connection=api, address=ip_address, list_name=list_blocked)


def _remove_ip_binding(mac_address: str, server: Optional[str]) -> None:
    if not mac_address:
        return
    if not _is_mikrotik_operations_enabled():
        logger.info("MikroTik ops disabled: skip ip-binding remove")
        return
    with get_mikrotik_connection() as api:
        if not api:
            logger.warning("Tidak bisa konek MikroTik untuk remove ip-binding")
            return
        remove_ip_binding(api_connection=api, mac_address=mac_address, server=server)


def resolve_client_mac(client_ip: Optional[str]) -> Tuple[bool, Optional[str], str]:
    if not client_ip:
        return False, None, "IP klien tidak ditemukan"
    if not _is_mikrotik_operations_enabled():
        return False, None, "MikroTik operations disabled"
    with get_mikrotik_connection() as api:
        if not api:
            return False, None, "Koneksi MikroTik gagal"
        ok, mac, msg = get_mac_by_ip(api_connection=api, ip_address=client_ip)
        if not ok:
            return False, None, msg
        if mac:
            return True, _normalize_mac(mac), "Sukses"
        return True, None, msg


def _is_client_ip_allowed(client_ip: Optional[str]) -> bool:
    if not client_ip:
        return False
    cidrs = []
    if current_app:
        cidrs = current_app.config.get('HOTSPOT_CLIENT_IP_CIDRS', [])
    if not cidrs:
        return True
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if ip_obj in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _resolve_binding_ip(user: User, client_ip: Optional[str]) -> Tuple[Optional[str], str, str]:
    if client_ip and _is_client_ip_allowed(client_ip):
        return client_ip, "client_ip", "IP klien valid"

    if not _is_mikrotik_operations_enabled():
        return None, "none", "MikroTik operations disabled"

    username_08 = format_to_local_phone(user.phone_number)
    with get_mikrotik_connection() as api:
        if not api:
            return None, "none", "Koneksi MikroTik gagal"

        if username_08:
            ok, hotspot_ip, msg = get_hotspot_user_ip(api, username_08)
            if ok and hotspot_ip:
                if _is_client_ip_allowed(hotspot_ip):
                    return hotspot_ip, "hotspot_user", "IP dari hotspot user"
                return None, "none", "IP hotspot berada di luar CIDR klien"

        device_mac = db.session.scalar(sa.select(UserDevice.mac_address).where(
            UserDevice.user_id == user.id,
            UserDevice.is_authorized.is_(True),
        ).order_by(UserDevice.last_seen_at.desc()).limit(1))
        if device_mac:
            ok, ip_from_mac, msg = get_ip_by_mac(api, device_mac)
            if ok and ip_from_mac:
                if _is_client_ip_allowed(ip_from_mac):
                    return ip_from_mac, "device_mac", "IP dari MAC device"
                return None, "none", "IP device berada di luar CIDR klien"

    return None, "none", "IP klien tidak valid dan tidak ditemukan di MikroTik"


def resolve_binding_context(
    user: User,
    client_ip: Optional[str],
    client_mac: Optional[str],
) -> Dict[str, Optional[str]]:
    resolved_ip, ip_source, ip_message = _resolve_binding_ip(user, client_ip)

    mac_source = None
    mac_message = None
    resolved_mac = None
    if client_mac:
        resolved_mac = _normalize_mac(client_mac)
        mac_source = "client_mac"
        mac_message = "MAC dari client"
    elif resolved_ip:
        ok, mac, msg = resolve_client_mac(resolved_ip)
        mac_message = msg
        if ok and mac:
            resolved_mac = mac
            mac_source = "mikrotik"
        elif ok:
            mac_source = "none"
        else:
            mac_source = "error"

    return {
        "input_ip": client_ip,
        "input_mac": client_mac,
        "resolved_ip": resolved_ip,
        "ip_source": ip_source,
        "ip_message": ip_message,
        "resolved_mac": resolved_mac,
        "mac_source": mac_source,
        "mac_message": mac_message,
    }


def register_or_update_device(
    user: User,
    client_ip: Optional[str],
    user_agent: Optional[str],
    client_mac: Optional[str] = None,
    allow_replace: bool = False,
) -> Tuple[bool, str, Optional[UserDevice]]:
    settings = _get_settings()
    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)
    mac_address: Optional[str] = None
    if client_mac:
        mac_address = _normalize_mac(client_mac)
    else:
        ok, resolved_mac, msg = resolve_client_mac(client_ip)
        if not ok:
            if settings['ip_binding_fail_open']:
                logger.warning(f"Skip IP binding karena MikroTik tidak tersedia: {msg}")
                return True, "Skip IP binding", None
            return False, msg, None
        if resolved_mac:
            mac_address = resolved_mac
        else:
            if settings['ip_binding_fail_open']:
                logger.warning("MAC tidak ditemukan; skip IP binding karena fail-open aktif.")
                return True, "Skip IP binding", None
            return False, "MAC tidak ditemukan", None

    if (not client_ip or not _is_client_ip_allowed(client_ip)) and mac_address:
        with get_mikrotik_connection() as api:
            if api:
                ok, ip_from_mac, msg = get_ip_by_mac(api, mac_address)
                if ok and ip_from_mac and _is_client_ip_allowed(ip_from_mac):
                    client_ip = ip_from_mac
                    if current_app and current_app.config.get('LOG_BINDING_DEBUG', False):
                        logger.info(
                            "Fallback IP from MAC: user=%s mac=%s ip=%s",
                            user.id,
                            mac_address,
                            client_ip,
                        )

    device = db.session.scalar(sa.select(UserDevice).where(
        UserDevice.user_id == user.id,
        UserDevice.mac_address == mac_address
    ))

    if device:
        old_ip = device.ip_address
        device.last_seen_at = now
        device.ip_address = client_ip
        device.user_agent = (user_agent or device.user_agent)
        db.session.flush()

        if old_ip and client_ip and str(old_ip).strip() != str(client_ip).strip():
            _remove_managed_address_lists(str(old_ip))

        return True, "Device ditemukan", device

    total_devices = db.session.scalar(sa.select(sa.func.count(UserDevice.id)).where(UserDevice.user_id == user.id)) or 0
    if total_devices >= settings['max_devices'] and settings['device_stale_days'] > 0:
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=settings['device_stale_days'])
        stale_devices = db.session.scalars(sa.select(UserDevice).where(
            UserDevice.user_id == user.id,
            UserDevice.last_seen_at.isnot(None),
            UserDevice.last_seen_at < cutoff
        )).all()
        for stale in stale_devices:
            try:
                if settings['ip_binding_enabled']:
                    _remove_ip_binding(stale.mac_address, user.mikrotik_server_name or settings['mikrotik_server_default'])
                _remove_managed_address_lists(stale.ip_address)
            except Exception:
                logger.warning(f"Gagal cleanup stale device {stale.id}")
            db.session.delete(stale)
        db.session.flush()
        total_devices = db.session.scalar(sa.select(sa.func.count(UserDevice.id)).where(UserDevice.user_id == user.id)) or 0
    if total_devices >= settings['max_devices']:
        if allow_replace and settings.get('device_auto_replace_enabled'):
            devices = db.session.scalars(sa.select(UserDevice).where(UserDevice.user_id == user.id)).all()
            candidates = [d for d in devices if (d.mac_address or '').upper() != (mac_address or '').upper()]
            if candidates:
                candidates.sort(
                    key=lambda d: (
                        bool(d.is_authorized),
                        d.last_seen_at or d.first_seen_at or datetime.min.replace(tzinfo=dt_timezone.utc),
                    )
                )
                evicted = candidates[0]

                try:
                    if settings['ip_binding_enabled'] and evicted.mac_address:
                        _remove_ip_binding(evicted.mac_address, user.mikrotik_server_name or settings['mikrotik_server_default'])
                    _remove_managed_address_lists(evicted.ip_address)
                    if settings.get('dhcp_static_lease_enabled') and evicted.mac_address:
                        _remove_dhcp_lease(evicted.mac_address, server=None)
                except Exception:
                    logger.warning("Gagal cleanup device yang di-evict: user=%s device=%s", user.id, evicted.id)

                db.session.delete(evicted)
                db.session.flush()

                total_devices = db.session.scalar(sa.select(sa.func.count(UserDevice.id)).where(UserDevice.user_id == user.id)) or 0

        if total_devices >= settings['max_devices']:
            username_08 = format_to_local_phone(user.phone_number) or ""
            if settings['ip_binding_enabled']:
                _ensure_ip_binding(
                    mac_address=mac_address,
                    ip_address=client_ip,
                    binding_type=settings['ip_binding_type_blocked'],
                    comment=(
                        f"limit-exceeded|user={username_08}|uid={user.id}|role={user.role.value}"
                        f"|date={date_str}|time={time_str}"
                    ),
                    server=user.mikrotik_server_name or settings['mikrotik_server_default'],
                )
            _ensure_blocked_address_list(client_ip, f"limit-exceeded|user={username_08}|date={date_str}|time={time_str}")
            return False, "Limit perangkat tercapai", None

    is_authorized = not settings['require_explicit']
    device = UserDevice()
    device.user_id = user.id
    device.mac_address = mac_address
    device.ip_address = client_ip
    device.user_agent = (user_agent[:255] if user_agent else None)
    device.is_authorized = is_authorized
    device.authorized_at = now if is_authorized else None
    db.session.add(device)
    db.session.flush()
    return True, "Device terdaftar", device


def apply_device_binding_for_login(
    user: User,
    client_ip: Optional[str],
    user_agent: Optional[str],
    client_mac: Optional[str] = None,
    bypass_explicit_auth: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    settings = _get_settings()
    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)

    original_ip = client_ip
    resolved_ip, ip_source, ip_msg = _resolve_binding_ip(user, client_ip)
    if not resolved_ip:
        if client_mac:
            logger.warning(f"Binding tanpa IP karena IP klien tidak valid: {ip_msg}")
            client_ip = None
        elif settings['ip_binding_fail_open']:
            logger.warning(f"Skip IP binding karena IP klien tidak valid: {ip_msg}")
            return True, "Skip IP binding", None
        else:
            return False, ip_msg, None
    else:
        client_ip = resolved_ip

    if current_app and current_app.config.get('LOG_BINDING_DEBUG', False):
        mac_only = (not original_ip) and bool(client_mac) and ip_source == "device_mac"
        logger.info(
            "Binding debug: user=%s input_ip=%s input_mac=%s resolved_ip=%s ip_source=%s mac_only=%s msg=%s",
            user.id,
            original_ip,
            client_mac,
            resolved_ip,
            ip_source,
            mac_only,
            ip_msg,
        )
    ok, msg, device = register_or_update_device(
        user,
        client_ip,
        user_agent,
        client_mac,
        allow_replace=bypass_explicit_auth,
    )
    if not ok:
        return False, msg, None

    if device is None and msg == "Skip IP binding":
        return True, msg, None

    if not device:
        return False, "Device tidak valid", None

    if not device.is_authorized and settings['require_explicit'] and not bypass_explicit_auth:
        username_08 = format_to_local_phone(user.phone_number) or ""
        if settings['ip_binding_enabled']:
            _ensure_ip_binding(
                mac_address=device.mac_address,
                ip_address=device.ip_address,
                binding_type=settings['ip_binding_type_blocked'],
                comment=(
                    f"pending-auth|user={username_08}|uid={user.id}|role={user.role.value}"
                    f"|date={date_str}|time={time_str}"
                ),
                server=user.mikrotik_server_name or settings['mikrotik_server_default'],
            )
        _ensure_blocked_address_list(device.ip_address, f"pending-auth|user={username_08}|date={date_str}|time={time_str}")
        return False, "Perangkat belum diotorisasi", client_ip

    if not device.is_authorized and settings['require_explicit'] and bypass_explicit_auth:
        logger.info(
            "Bypass explicit device auth setelah OTP berhasil: user=%s mac=%s ip=%s",
            user.id,
            device.mac_address,
            device.ip_address,
        )

    if settings['ip_binding_enabled']:
        username_08 = format_to_local_phone(user.phone_number) or ""
        allowed_binding_type = resolve_allowed_binding_type_for_user(user)
        _ensure_ip_binding(
            mac_address=device.mac_address,
            ip_address=device.ip_address,
            binding_type=allowed_binding_type,
            comment=(
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|date={date_str}|time={time_str}"
            ),
            server=user.mikrotik_server_name or settings['mikrotik_server_default'],
        )
    _remove_blocked_address_list(device.ip_address)

    if settings.get('dhcp_static_lease_enabled'):
        username_08 = format_to_local_phone(user.phone_number) or ""
        dhcp_server_name = settings.get('dhcp_lease_server_name') or None
        _ensure_static_dhcp_lease(
            mac_address=device.mac_address,
            ip_address=device.ip_address,
            comment=(
                f"lpsaring|static-dhcp|user={username_08}|uid={user.id}"
                f"|date={date_str}|time={time_str}"
            ),
            server=dhcp_server_name,
        )

    device.is_authorized = True
    if not device.authorized_at:
        device.authorized_at = datetime.now(dt_timezone.utc)
    db.session.flush()
    return True, "Perangkat terotorisasi", client_ip


def revoke_device(user: User, device: UserDevice) -> None:
    settings = _get_settings()
    device.is_authorized = False
    device.deauthorized_at = datetime.now(dt_timezone.utc)
    if settings['ip_binding_enabled']:
        _remove_ip_binding(device.mac_address, user.mikrotik_server_name or settings['mikrotik_server_default'])
    _remove_managed_address_lists(device.ip_address)
    db.session.flush()
