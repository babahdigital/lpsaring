import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.infrastructure.db.models import User, UserDevice
from app.infrastructure.gateways.mikrotik_client import (
    get_hotspot_host_usage_map,
    get_mikrotik_connection,
    upsert_ip_binding,
)
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.device_management_service import normalize_mac
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings, get_phone_number_variations

logger = logging.getLogger(__name__)


def _find_user_by_phone(phone: str) -> Optional[User]:
    if not phone:
        return None
    variations = get_phone_number_variations(phone)
    return db.session.query(User).filter(User.phone_number.in_(list(variations))).first()


def _find_user_for_ip(ip_address: str, mac_address: Optional[str], hotspot_user: Optional[str]) -> Optional[User]:
    if mac_address:
        normalized_mac = normalize_mac(mac_address)
        if normalized_mac:
            device = (
                db.session.query(UserDevice)
                .filter(UserDevice.mac_address == normalized_mac)
                .order_by(UserDevice.last_seen_at.desc())
                .first()
            )
            if device and device.user:
                return device.user

    if ip_address:
        device = (
            db.session.query(UserDevice)
            .filter(UserDevice.ip_address == ip_address)
            .order_by(UserDevice.last_seen_at.desc())
            .first()
        )
        if device and device.user:
            return device.user

    if hotspot_user:
        # RouterOS "user" biasanya username hotspot (08.. / +62..). Kita normalize ke 08.. lalu cari variasi.
        candidate_08 = format_to_local_phone(hotspot_user) or hotspot_user
        user = _find_user_by_phone(candidate_08)
        if user:
            return user

    return None


@click.command('sync-mikrotik-access')
@click.option('--ip', 'ip_address', required=True, help='IP lokal klien hotspot (contoh: 172.16.2.113).')
@click.option('--apply', 'apply_changes', is_flag=True, help='Terapkan perubahan (tanpa flag ini hanya diagnosis).')
@click.option('--update-ip-binding/--no-update-ip-binding', default=True, show_default=True)
@with_appcontext
def sync_mikrotik_access_command(ip_address: str, apply_changes: bool, update_ip_binding: bool) -> None:
    """Paksa sinkronisasi akses MikroTik berdasarkan IP.

    Dipakai saat OTP sukses tapi akses belum kebuka karena backend tidak mendapat IP lokal/MAC.

    Yang dilakukan:
    - Diagnosis: cari MAC & hotspot host state untuk IP.
    - Jika user ketemu: sync address-list untuk user dengan IP tersebut.
    - Opsional: upsert ip-binding untuk MAC (binding type mengikuti access policy).
    """

    ip_address = (ip_address or '').strip()
    if not ip_address:
        raise click.ClickException('IP tidak valid')

    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException('Gagal konek MikroTik')

        ok_host, host_usage_map, host_msg = get_hotspot_host_usage_map(api)
        if not ok_host:
            raise click.ClickException(f'Gagal ambil hotspot host: {host_msg}')

        found_mac: Optional[str] = None
        found_host: Optional[dict] = None
        for mac, entry in host_usage_map.items():
            if str(entry.get('address') or '').strip() == ip_address:
                found_mac = str(mac).upper()
                found_host = entry
                break

        if found_mac:
            bypassed = (found_host or {}).get('bypassed')
            authorized = (found_host or {}).get('authorized')
            click.echo(f"Host ditemukan: ip={ip_address} mac={found_mac} bypassed={bypassed} authorized={authorized}")
        else:
            click.echo(f"Host TIDAK ditemukan untuk ip={ip_address}. (Kemungkinan IP sudah ganti / host table belum ada)")

        # Coba ambil field 'user' dari /ip/hotspot/host langsung, karena helper map tidak menyertakan.
        hotspot_user: Optional[str] = None
        try:
            host_rows = api.get_resource('/ip/hotspot/host').get(address=ip_address)
            if host_rows:
                hotspot_user = host_rows[0].get('user')
        except Exception:
            hotspot_user = None

        if hotspot_user:
            click.echo(f"Hotspot user di host: {hotspot_user}")

        user = _find_user_for_ip(ip_address, found_mac, hotspot_user)
        if not user:
            raise click.ClickException(f"User tidak ketemu untuk ip={ip_address}. Cek apakah device pernah tersimpan di DB atau host belum punya user.")

        username_08 = format_to_local_phone(user.phone_number) or user.phone_number
        click.echo(f"Target user: id={user.id} phone={username_08} role={user.role.value}")

        # 1) Sync address-list
        if not apply_changes:
            click.echo("DRY-RUN: akan sync address-list untuk user (berdasarkan DB quota/status) dengan client_ip di atas")
        else:
            ok = sync_address_list_for_single_user(user, client_ip=ip_address)
            click.echo(f"APPLY: sync address-list => {ok}")

        # 2) Sync ip-binding (kalau MAC ketemu)
        if update_ip_binding and found_mac:
            binding_type = resolve_allowed_binding_type_for_user(user)
            comment = (
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source=sync-ip|date={date_str}|time={time_str}"
            )
            if not apply_changes:
                click.echo(f"DRY-RUN: akan upsert ip-binding mac={found_mac} ip={ip_address} type={binding_type} comment={comment}")
            else:
                ok, msg = upsert_ip_binding(
                    api_connection=api,
                    mac_address=found_mac,
                    address=ip_address,
                    server=getattr(user, 'mikrotik_server_name', None),
                    binding_type=binding_type,
                    comment=comment,
                )
                if not ok:
                    raise click.ClickException(f"Gagal upsert ip-binding: {msg}")
                click.echo(f"APPLY: upsert ip-binding => ok ({msg})")

    logger.info("sync-mikrotik-access done ip=%s apply=%s", ip_address, apply_changes)
