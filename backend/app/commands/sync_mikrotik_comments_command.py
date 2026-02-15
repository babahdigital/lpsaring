import logging
import re
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Optional, Tuple

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.infrastructure.db.models import User, UserDevice
from app.infrastructure.gateways.mikrotik_client import (
    _extract_user_id_from_comment,
    get_mikrotik_connection,
    upsert_address_list_entry,
    upsert_ip_binding,
)
from app.services.device_management_service import normalize_mac
from app.services import settings_service
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings

logger = logging.getLogger(__name__)


def _load_device_maps() -> Tuple[Dict[str, User], Dict[str, User]]:
    mac_to_user: Dict[str, User] = {}
    ip_to_user: Dict[str, User] = {}

    rows = db.session.query(UserDevice, User).join(User, UserDevice.user_id == User.id).all()
    for device, user in rows:
        if not user or not user.phone_number:
            continue
        if device.mac_address:
            normalized = normalize_mac(device.mac_address)
            if normalized:
                mac_to_user[normalized] = user
        if device.ip_address:
            ip_to_user[str(device.ip_address)] = user
    return mac_to_user, ip_to_user


def _build_ip_binding_comment(prefix: str, user: User, now: datetime) -> str:
    username_08 = format_to_local_phone(user.phone_number) or ""
    date_str, time_str = get_app_date_time_strings(now)
    base = prefix.strip() or "synced"
    return f"{base}|user={username_08}|uid={user.id}|role={user.role.value}|date={date_str}|time={time_str}"


def _build_address_list_comment(status_value: str, user: User, ip: Optional[str], now: datetime) -> str:
    username_08 = format_to_local_phone(user.phone_number) or ""
    date_str, time_str = get_app_date_time_strings(now)
    parts = [
        f"lpsaring|status={status_value}",
        f"|user={username_08}",
        f"|role={user.role.value}",
    ]
    if ip:
        parts.append(f"|ip={ip}")
    parts.append(f"|date={date_str}|time={time_str}")
    return "".join(parts)


def _find_user_for_address_list_entry(address: str, old_comment: str, ip_to_user: Dict[str, User]) -> Optional[User]:
    if address:
        user = ip_to_user.get(str(address))
        if user is not None:
            return user

    candidate = _extract_user_id_from_comment(old_comment)
    if candidate:
        try:
            user = db.session.get(User, candidate)
        except Exception:
            user = None
        if user is not None:
            return user

    match = re.search(r'(?:^|[|\s])phone=([^|\s]+)', str(old_comment or ''))
    if match:
        phone_raw = match.group(1).strip()
        phone_08 = format_to_local_phone(phone_raw) or phone_raw
        variations = {phone_raw, phone_08}
        variations.update({phone_raw.replace(' ', ''), phone_08.replace(' ', '')})
        return db.session.query(User).filter(User.phone_number.in_(list(variations))).first()

    return None


@click.command('sync-mikrotik-comments')
@click.option('--apply', 'apply_changes', is_flag=True, help='Terapkan perubahan (tanpa flag ini hanya dry-run).')
@click.option('--ip-binding/--no-ip-binding', 'do_ip_binding', default=True, show_default=True)
@click.option('--host/--no-host', 'do_host', default=False, show_default=True)
@click.option('--address-list/--no-address-list', 'do_address_list', default=True, show_default=True)
@with_appcontext
def sync_mikrotik_comments_command(apply_changes: bool, do_ip_binding: bool, do_host: bool, do_address_list: bool):
    """Sinkronkan komentar MikroTik agar searchable dengan nomor telepon.

    - ip-binding: comment -> user=<08..>|uid=<uuid>|...
    - hotspot host: comment -> user=<08..>|uid=<uuid>|...
    - firewall address-list: comment -> lpsaring|status=...|user=<08..>|... (tanpa UUID)
    """
    mac_to_user, ip_to_user = _load_device_maps()
    now = datetime.now(dt_timezone.utc)

    list_active = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_ACTIVE', 'active') or 'active'
    list_fup = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_FUP', 'fup') or 'fup'
    list_inactive = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_INACTIVE', 'inactive') or 'inactive'
    list_expired = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_EXPIRED', 'expired') or 'expired'
    list_habis = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_HABIS', 'habis') or 'habis'
    list_blocked = settings_service.get_setting('MIKROTIK_ADDRESS_LIST_BLOCKED', 'blocked') or 'blocked'

    list_to_status = {
        list_active: 'active',
        list_fup: 'fup',
        list_inactive: 'inactive',
        list_expired: 'expired',
        list_habis: 'habis',
        list_blocked: 'blocked',
    }

    updated = {'ip_binding': 0, 'host': 0, 'address_list': 0, 'skipped': 0}

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException('Gagal konek MikroTik')

        if do_ip_binding:
            resource = api.get_resource('/ip/hotspot/ip-binding')
            bindings = resource.get()
            for entry in bindings:
                entry_id = entry.get('id') or entry.get('.id')
                mac = entry.get('mac-address')
                if not entry_id or not mac:
                    updated['skipped'] += 1
                    continue
                comment = entry.get('comment') or ''
                user_id = _extract_user_id_from_comment(comment)
                if not user_id:
                    updated['skipped'] += 1
                    continue
                user = db.session.get(User, user_id)
                if not user:
                    updated['skipped'] += 1
                    continue

                prefix = (comment.split('|', 1)[0] if '|' in comment else (comment.strip() or 'synced'))
                new_comment = _build_ip_binding_comment(prefix, user, now)
                if comment == new_comment:
                    continue
                if not apply_changes:
                    logger.info('DRY-RUN ip-binding mac=%s old=%s new=%s', mac, comment, new_comment)
                else:
                    ok, msg = upsert_ip_binding(
                        api_connection=api,
                        mac_address=str(mac),
                        address=entry.get('address'),
                        server=entry.get('server'),
                        binding_type=entry.get('type') or 'regular',
                        comment=new_comment,
                    )
                    if not ok:
                        logger.warning('Gagal update ip-binding mac=%s: %s', mac, msg)
                        updated['skipped'] += 1
                        continue
                updated['ip_binding'] += 1

        if do_host:
            logger.warning(
                "Host comment sync is disabled by default because many RouterOS versions expose /ip/hotspot/host as read-only (no set command). "
                "Skip updating hotspot host comments."
            )

        if do_address_list:
            address_resource = api.get_resource('/ip/firewall/address-list')
            entries = address_resource.get()
            for entry in entries:
                entry_id = entry.get('id') or entry.get('.id')
                list_name = entry.get('list')
                address = entry.get('address')
                if not entry_id or not list_name or not address:
                    updated['skipped'] += 1
                    continue
                status_value = list_to_status.get(str(list_name))
                if not status_value:
                    continue

                old_comment = entry.get('comment') or ''
                user = _find_user_for_address_list_entry(str(address), str(old_comment), ip_to_user)
                if not user:
                    updated['skipped'] += 1
                    continue

                new_comment = _build_address_list_comment(status_value, user, str(address), now)
                if old_comment == new_comment:
                    continue

                if not apply_changes:
                    logger.info('DRY-RUN address-list ip=%s list=%s old=%s new=%s', address, list_name, old_comment, new_comment)
                else:
                    ok, msg = upsert_address_list_entry(
                        api_connection=api,
                        address=str(address),
                        list_name=str(list_name),
                        comment=new_comment,
                    )
                    if not ok:
                        logger.warning('Gagal update address-list ip=%s list=%s: %s', address, list_name, msg)
                        updated['skipped'] += 1
                        continue
                updated['address_list'] += 1

    click.echo(f"Done. apply={apply_changes} updated={updated}")
