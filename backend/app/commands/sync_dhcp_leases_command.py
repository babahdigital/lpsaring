# backend/app/commands/sync_dhcp_leases_command.py

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional

import click
import sqlalchemy as sa
from flask.cli import with_appcontext

from app.extensions import db
from app.infrastructure.db.models import UserDevice, User
from app.infrastructure.gateways.mikrotik_client import (
    get_mikrotik_connection,
    get_ip_by_mac,
    upsert_dhcp_static_lease,
)
from app.services import settings_service
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings

logger = logging.getLogger(__name__)


@click.command('sync-dhcp-leases')
@click.option('--limit', type=int, default=0, help='Batasi jumlah device yang diproses (0 = semua).')
@click.option('--only-authorized/--all', default=True, help='Sync hanya device authorized atau semua device di DB.')
@with_appcontext
def sync_dhcp_leases_command(limit: int, only_authorized: bool) -> None:
    """Sync DHCP static leases di MikroTik untuk semua device yang tercatat.

    Tujuan:
    - Menstabilkan IP per-MAC supaya address-list (IP-based) tidak mudah stale.

    Strategi:
    - Ambil semua device (default hanya authorized) dari DB.
    - Resolve IP terkini via MikroTik (hotspot host/active/arp/dhcp).
    - Upsert DHCP static lease (make-static bila perlu) dengan comment berisi user & uid.

    Catatan:
    - Jika device sedang tidak terlihat di MikroTik (tidak ada IP), device tersebut di-skip.
    """

    enabled = settings_service.get_setting('MIKROTIK_DHCP_STATIC_LEASE_ENABLED', 'False') == 'True'
    if not enabled:
        click.echo('MIKROTIK_DHCP_STATIC_LEASE_ENABLED=False (fitur tidak aktif). Tetap bisa dijalankan, tapi disarankan aktifkan agar konsisten.')

    where_clause = [UserDevice.mac_address.isnot(None)]
    if only_authorized:
        where_clause.append(UserDevice.is_authorized.is_(True))

    devices = db.session.scalars(
        sa.select(UserDevice).where(*where_clause).order_by(UserDevice.last_seen_at.desc().nullslast())
    ).all()

    if limit and limit > 0:
        devices = devices[:limit]

    click.echo(f"Memproses {len(devices)} device...")

    now = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now)

    processed = 0
    synced = 0
    skipped_no_ip = 0
    skipped_no_user = 0
    failed = 0

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException('Gagal konek MikroTik')

        for device in devices:
            processed += 1
            mac = str(device.mac_address or '').strip().upper()
            if not mac:
                continue

            user: Optional[User] = db.session.get(User, device.user_id)
            if not user:
                skipped_no_user += 1
                continue

            ok, ip_from_mac, _msg = get_ip_by_mac(api, mac)
            if not ok or not ip_from_mac:
                skipped_no_ip += 1
                continue

            username_08 = format_to_local_phone(user.phone_number) or ''
            comment = (
                f"lpsaring|static-dhcp|user={username_08}|uid={user.id}"
                f"|date={date_str}|time={time_str}"
            )

            ok_upsert, msg_upsert = upsert_dhcp_static_lease(
                api_connection=api,
                mac_address=mac,
                address=ip_from_mac,
                comment=comment,
                server=None,
            )
            if ok_upsert:
                synced += 1
            else:
                failed += 1
                logger.warning(
                    "Gagal sync DHCP lease: user=%s mac=%s ip=%s msg=%s",
                    user.id,
                    mac,
                    ip_from_mac,
                    msg_upsert,
                )

    click.echo(
        f"Selesai. processed={processed} synced={synced} skipped_no_ip={skipped_no_ip} skipped_no_user={skipped_no_user} failed={failed}"
    )
