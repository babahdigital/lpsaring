# backend/app/commands/sync_unauthorized_hosts_command.py

from __future__ import annotations

import ipaddress
from typing import Dict, Iterable, List, Optional, Tuple

import click
from flask import current_app
from flask.cli import with_appcontext

from app.infrastructure.gateways.mikrotik_client import (
    get_firewall_address_list_entries,
    get_hotspot_hosts,
    get_mikrotik_connection,
    remove_address_list_entry,
    upsert_address_list_entry,
)
from app.services import settings_service
from app.utils.ip_ranges import expand_ip_tokens
from app.utils.mikrotik_duration import parse_routeros_duration_to_seconds


def _resolve_networks(cidrs: Iterable[str]) -> List[ipaddress._BaseNetwork]:
    networks: List[ipaddress._BaseNetwork] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(str(cidr), strict=False))
        except Exception:
            continue
    return networks


def _ip_allowed(ip_text: str, networks: List[ipaddress._BaseNetwork]) -> bool:
    if not ip_text:
        return False
    if not networks:
        return True
    try:
        ip_obj = ipaddress.ip_address(str(ip_text))
    except Exception:
        return False
    return any(ip_obj in net for net in networks)


@click.command("sync-unauthorized-hosts")
@click.option(
    "--list-name",
    default=None,
    help="Nama address-list untuk blok unauthorized (default dari setting MIKROTIK_ADDRESS_LIST_UNAUTHORIZED atau 'unauthorized').",
)
@click.option(
    "--timeout",
    default=None,
    help="Timeout address-list (contoh: 1h, 30m). Default dari setting MIKROTIK_ADDRESS_LIST_UNAUTHORIZED_TIMEOUT atau '1h'.",
)
@click.option(
    "--min-uptime-minutes",
    type=int,
    default=None,
    help="Minimal uptime host (menit) sebelum dianggap unauthorized dan diblok. Default dari setting MIKROTIK_UNAUTHORIZED_MIN_UPTIME_MINUTES atau 10.",
)
@click.option(
    "--cidr",
    "cidrs",
    multiple=True,
    help=(
        "Batasi IP yang di-scan/ditulis hanya untuk CIDR ini. Bisa diulang. "
        "Jika kosong, pakai MIKROTIK_UNAUTHORIZED_CIDRS dari config (fallback HOTSPOT_CLIENT_IP_CIDRS)."
    ),
)
@click.option(
    "--exempt-ip",
    "exempt_ips",
    multiple=True,
    help=(
        "Daftar IP/range yang dikecualikan dari blok unauthorized. Bisa diulang. "
        "Format: 172.16.2.3 atau 172.16.2.3-7 atau 172.16.2.3-172.16.2.7. "
        "Jika kosong, pakai MIKROTIK_UNAUTHORIZED_EXEMPT_IPS dari config."
    ),
)
@click.option("--limit", type=int, default=0, show_default=True, help="Batasi jumlah host diproses (0 = semua).")
@click.option("--apply/--dry-run", default=False, show_default=True)
@with_appcontext
def sync_unauthorized_hosts_command(
    list_name: Optional[str],
    timeout: Optional[str],
    min_uptime_minutes: Optional[int],
    cidrs: Tuple[str, ...],
    exempt_ips: Tuple[str, ...],
    limit: int,
    apply: bool,
) -> None:
    """Scan /ip/hotspot/host lalu kelola address-list unauthorized berbasis IP.

    Tujuan:
    - Mengurangi akses internet gratis dari device yang belum authorized.

    Kebijakan:
    - Hanya host dengan authorized=false dan uptime >= threshold yang dimasukkan ke address-list.
    - Entri dihapus jika sudah authorized atau host sudah tidak muncul.
    - Hanya menghapus entri yang dikelola aplikasi (comment prefix: 'lpsaring:unauthorized').
    """

    resolved_list = (
        list_name
        or settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized")
        or "unauthorized"
    )
    resolved_timeout = (
        timeout or settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED_TIMEOUT", "1h") or "1h"
    )
    resolved_min_uptime = int(
        min_uptime_minutes
        if min_uptime_minutes is not None
        else settings_service.get_setting_as_int("MIKROTIK_UNAUTHORIZED_MIN_UPTIME_MINUTES", 10)
    )
    min_uptime_seconds = max(0, resolved_min_uptime) * 60

    if cidrs:
        cidr_list = list(cidrs)
    else:
        cidr_list = list(current_app.config.get("MIKROTIK_UNAUTHORIZED_CIDRS", []) or [])
        if not cidr_list:
            cidr_list = list(current_app.config.get("HOTSPOT_CLIENT_IP_CIDRS", []) or [])

    networks = _resolve_networks(cidr_list)
    if not networks:
        raise click.ClickException(
            "CIDR kosong/tidak valid. Set MIKROTIK_UNAUTHORIZED_CIDRS atau jalankan dengan --cidr 172.16.2.0/23"
        )

    exempt_tokens = (
        list(exempt_ips) if exempt_ips else list(current_app.config.get("MIKROTIK_UNAUTHORIZED_EXEMPT_IPS", []) or [])
    )
    exempt_set = expand_ip_tokens(exempt_tokens)

    prefix = "lpsaring:unauthorized"
    desired: Dict[str, str] = {}

    processed = 0
    skipped_no_ip = 0
    skipped_not_allowed = 0
    skipped_low_uptime = 0
    skipped_authorized = 0
    skipped_exempt = 0
    to_add = 0
    to_remove = 0

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException("Gagal konek MikroTik")

        ok, hosts, msg = get_hotspot_hosts(api)
        if not ok:
            raise click.ClickException(f"Gagal ambil hotspot host: {msg}")

        if limit and limit > 0:
            hosts = hosts[:limit]

        for host in hosts:
            processed += 1

            ip_text = str(host.get("address") or "").strip()
            if not ip_text:
                skipped_no_ip += 1
                continue

            if not _ip_allowed(ip_text, networks):
                skipped_not_allowed += 1
                continue

            if ip_text in exempt_set:
                skipped_exempt += 1
                continue

            authorized = str(host.get("authorized", "false")).lower() == "true"
            bypassed = str(host.get("bypassed", "false")).lower() == "true"
            if authorized or bypassed:
                skipped_authorized += 1
                continue

            uptime_text = str(host.get("uptime") or "").strip()
            uptime_seconds = parse_routeros_duration_to_seconds(uptime_text)
            if uptime_seconds < min_uptime_seconds:
                skipped_low_uptime += 1
                continue

            mac = str(host.get("mac-address") or "").strip().upper()
            desired[ip_text] = f"{prefix} mac={mac} uptime={uptime_text}".strip()

        # Reconcile: remove managed entries no longer desired
        ok, existing, msg = get_firewall_address_list_entries(api, resolved_list)
        if not ok:
            raise click.ClickException(f"Gagal ambil address-list '{resolved_list}': {msg}")

        existing_managed = {
            str(e.get("address") or "").strip(): str(e.get("comment") or "")
            for e in existing
            if str(e.get("comment") or "").startswith(prefix)
        }

        # Remove entries that are managed but no longer desired.
        for addr in list(existing_managed.keys()):
            if addr and addr not in desired:
                to_remove += 1
                if apply:
                    remove_address_list_entry(api, addr, resolved_list)

        # Upsert desired entries.
        for addr, comment in desired.items():
            to_add += 1
            if apply:
                upsert_address_list_entry(api, addr, resolved_list, comment=comment, timeout=resolved_timeout)

    click.echo(
        f"processed_hosts={processed} desired_block_ips={len(desired)} "
        f"would_add_or_refresh={to_add} would_remove={to_remove} apply={apply} "
        f"skipped_no_ip={skipped_no_ip} skipped_not_allowed={skipped_not_allowed} "
        f"skipped_exempt={skipped_exempt} "
        f"skipped_low_uptime={skipped_low_uptime} skipped_authorized_or_bypassed={skipped_authorized}"
    )
