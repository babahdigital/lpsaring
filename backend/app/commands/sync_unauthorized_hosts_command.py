# backend/app/commands/sync_unauthorized_hosts_command.py

from __future__ import annotations

import ipaddress
from typing import Dict, Iterable, List, Optional, Tuple

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from app.infrastructure.gateways.mikrotik_client import (
    get_firewall_address_list_entries,
    get_hotspot_hosts,
    get_mikrotik_connection,
    remove_hotspot_host_entries,
    remove_address_list_entry,
    upsert_address_list_entry,
)
from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserDevice
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


def _normalize_ip_for_compare(ip_text: str) -> str:
    text = str(ip_text or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except Exception:
        return text


def _collect_non_blocked_ip_binding_snapshot(api) -> Tuple[set[str], set[Tuple[str, str]], set[str]]:
    """Kumpulkan snapshot ip-binding non-blocked:

    Returns:
    - mac_set: MAC yang punya binding non-blocked
    - mac_ip_pairs: pasangan (MAC, IP) dari binding non-blocked bila address tersedia
    - ip_set: IP dari binding non-blocked bila address tersedia
    """
    mac_set: set[str] = set()
    mac_ip_pairs: set[Tuple[str, str]] = set()
    ip_set: set[str] = set()

    try:
        rows = api.get_resource("/ip/hotspot/ip-binding").get() or []
    except Exception:
        return mac_set, mac_ip_pairs, ip_set

    for row in rows:
        binding_type = str(row.get("type") or "").strip().lower()
        if binding_type == "blocked":
            continue

        mac = str(row.get("mac-address") or "").strip().upper()
        if not mac:
            continue
        mac_set.add(mac)

        ip_text = _normalize_ip_for_compare(row.get("address") or "")
        if ip_text:
            mac_ip_pairs.add((mac, ip_text))
            ip_set.add(ip_text)

    return mac_set, mac_ip_pairs, ip_set


def _collect_dhcp_lease_snapshot(api) -> Tuple[set[str], set[Tuple[str, str]], set[str]]:
    """Kumpulkan snapshot DHCP lease yang usable (bukan waiting)."""
    mac_set: set[str] = set()
    mac_ip_pairs: set[Tuple[str, str]] = set()
    ip_set: set[str] = set()

    try:
        rows = api.get_resource("/ip/dhcp-server/lease").get() or []
    except Exception:
        return mac_set, mac_ip_pairs, ip_set

    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "waiting":
            continue

        mac = str(row.get("mac-address") or "").strip().upper()
        ip_text = _normalize_ip_for_compare(row.get("address") or "")

        if mac:
            mac_set.add(mac)
        if ip_text:
            ip_set.add(ip_text)
        if mac and ip_text:
            mac_ip_pairs.add((mac, ip_text))

    return mac_set, mac_ip_pairs, ip_set


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
    # Alias tambahan agar operasional bisa pakai istilah BYPASS dari env.
    bypass_tokens = list(current_app.config.get("MIKROTIK_UNAUTHORIZED_BYPASS_IPS", []) or [])
    exempt_tokens.extend(bypass_tokens)
    exempt_set = expand_ip_tokens(exempt_tokens)

    prefix = "lpsaring:unauthorized"
    desired: Dict[str, str] = {}

    authorized_device_ips = {
        _normalize_ip_for_compare(str(ip or ""))
        for ip in db.session.scalars(
            select(UserDevice.ip_address)
            .join(User, User.id == UserDevice.user_id)
            .where(
                UserDevice.ip_address.isnot(None),
                UserDevice.is_authorized.is_(True),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        ).all()
        if _normalize_ip_for_compare(str(ip or ""))
    }

    authorized_device_macs = {
        str(mac).strip().upper()
        for mac in db.session.scalars(
            select(UserDevice.mac_address)
            .join(User, User.id == UserDevice.user_id)
            .where(
                UserDevice.mac_address.isnot(None),
                UserDevice.is_authorized.is_(True),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        ).all()
        if str(mac or "").strip()
    }

    processed = 0
    skipped_no_ip = 0
    skipped_not_allowed = 0
    skipped_low_uptime = 0
    skipped_authorized = 0
    skipped_authorized_device_ip = 0
    skipped_authorized_device_mac = 0
    skipped_binding_dhcp_trusted = 0
    skipped_exempt = 0
    to_add = 0
    to_remove = 0
    forced_exempt_remove = 0
    forced_authorized_remove = 0
    forced_binding_dhcp_remove = 0
    hotspot_host_cleanup_removed = 0
    failed_add_or_refresh = 0
    failed_remove = 0
    failed_forced_exempt_remove = 0
    failed_forced_authorized_remove = 0
    failed_forced_binding_dhcp_remove = 0
    failed_hotspot_host_cleanup = 0

    trusted_binding_dhcp_ips: set[str] = set()

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException("Gagal konek MikroTik")

        ok, hosts, msg = get_hotspot_hosts(api)
        if not ok:
            raise click.ClickException(f"Gagal ambil hotspot host: {msg}")

        if limit and limit > 0:
            hosts = hosts[:limit]

        trust_binding_and_dhcp = bool(current_app.config.get("MIKROTIK_UNAUTHORIZED_TRUST_IP_BINDING_DHCP", True))
        ipb_non_blocked_macs, ipb_non_blocked_pairs, ipb_non_blocked_ips = _collect_non_blocked_ip_binding_snapshot(api)
        dhcp_macs, dhcp_pairs, dhcp_ips = _collect_dhcp_lease_snapshot(api)

        def _cleanup_trusted_hotspot_host(ip_text: str, mac_text: str) -> None:
            nonlocal hotspot_host_cleanup_removed, failed_hotspot_host_cleanup
            if not apply:
                return
            ok_cleanup, _cleanup_msg, removed_count = remove_hotspot_host_entries(
                api,
                mac_address=mac_text or None,
                address=ip_text or None,
            )
            if ok_cleanup:
                hotspot_host_cleanup_removed += int(removed_count or 0)
            else:
                failed_hotspot_host_cleanup += 1

        for host in hosts:
            processed += 1

            ip_text = _normalize_ip_for_compare(host.get("address") or "")
            if not ip_text:
                skipped_no_ip += 1
                continue

            if not _ip_allowed(ip_text, networks):
                skipped_not_allowed += 1
                continue

            mac = str(host.get("mac-address") or "").strip().upper()

            if ip_text in exempt_set:
                skipped_exempt += 1
                continue

            if ip_text in authorized_device_ips:
                skipped_authorized_device_ip += 1
                _cleanup_trusted_hotspot_host(ip_text, mac)
                continue

            if mac and mac in authorized_device_macs:
                skipped_authorized_device_mac += 1
                _cleanup_trusted_hotspot_host(ip_text, mac)
                if ip_text:
                    trusted_binding_dhcp_ips.add(ip_text)
                continue

            # Root-cause guard:
            # Jika host punya non-blocked ip-binding + DHCP lease valid, anggap trusted dan jangan masuk unauthorized.
            # Stale host entry dibersihkan agar tidak terus re-appear tiap scheduler run.
            if trust_binding_and_dhcp:
                has_non_blocked_binding = bool(mac and mac in ipb_non_blocked_macs) or (
                    ip_text in ipb_non_blocked_ips
                )
                has_dhcp_lease = (
                    (bool(mac) and (mac, ip_text) in dhcp_pairs)
                    or (bool(mac) and (mac, ip_text) in ipb_non_blocked_pairs and ip_text in dhcp_ips)
                    or (bool(mac) and mac in dhcp_macs and ip_text in dhcp_ips)
                    or (ip_text in ipb_non_blocked_ips and ip_text in dhcp_ips)
                )
                if has_non_blocked_binding and has_dhcp_lease:
                    skipped_binding_dhcp_trusted += 1
                    if ip_text:
                        trusted_binding_dhcp_ips.add(ip_text)
                    _cleanup_trusted_hotspot_host(ip_text, mac)
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

            desired[ip_text] = f"{prefix} mac={mac} uptime={uptime_text}".strip()

        if exempt_set:
            for exempt_ip in list(exempt_set):
                desired.pop(_normalize_ip_for_compare(exempt_ip), None)

        # Reconcile: remove managed entries no longer desired
        ok, existing, msg = get_firewall_address_list_entries(api, resolved_list)
        if not ok:
            raise click.ClickException(f"Gagal ambil address-list '{resolved_list}': {msg}")

        existing_managed = {
            _normalize_ip_for_compare(e.get("address") or ""): str(e.get("comment") or "")
            for e in existing
            if str(e.get("comment") or "").startswith(prefix)
        }

        # Remove entries that are managed but no longer desired.
        for addr in list(existing_managed.keys()):
            if addr and addr not in desired:
                to_remove += 1
                if apply:
                    ok_remove, _remove_msg = remove_address_list_entry(api, addr, resolved_list)
                    if not ok_remove:
                        failed_remove += 1

        # Upsert desired entries.
        for addr, comment in desired.items():
            to_add += 1
            if apply:
                ok_upsert, _upsert_msg = upsert_address_list_entry(
                    api,
                    addr,
                    resolved_list,
                    comment=comment,
                    timeout=resolved_timeout,
                )
                if not ok_upsert:
                    failed_add_or_refresh += 1

        # Final safety guard: exempt IP must never stay in unauthorized list.
        for exempt_ip in list(exempt_set):
            normalized_exempt_ip = _normalize_ip_for_compare(exempt_ip)
            if not normalized_exempt_ip:
                continue
            forced_exempt_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, normalized_exempt_ip, resolved_list)
                if not ok_remove:
                    failed_forced_exempt_remove += 1

        # Final safety guard: IP device yang sudah authorized di DB tidak boleh bertahan di unauthorized list.
        for authorized_ip in sorted(authorized_device_ips):
            if not authorized_ip:
                continue
            forced_authorized_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, authorized_ip, resolved_list)
                if not ok_remove:
                    failed_forced_authorized_remove += 1

        # Final safety guard: trusted ip-binding + dhcp lease juga tidak boleh bertahan di unauthorized list.
        for trusted_ip in sorted(trusted_binding_dhcp_ips):
            if not trusted_ip:
                continue
            forced_binding_dhcp_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, trusted_ip, resolved_list)
                if not ok_remove:
                    failed_forced_binding_dhcp_remove += 1

    click.echo(
        f"processed_hosts={processed} desired_block_ips={len(desired)} "
        f"would_add_or_refresh={to_add} would_remove={to_remove} apply={apply} "
        f"forced_exempt_remove={forced_exempt_remove} forced_authorized_remove={forced_authorized_remove} "
        f"forced_binding_dhcp_remove={forced_binding_dhcp_remove} "
        f"hotspot_host_cleanup_removed={hotspot_host_cleanup_removed} "
        f"failed_add_or_refresh={failed_add_or_refresh} failed_remove={failed_remove} "
        f"failed_forced_exempt_remove={failed_forced_exempt_remove} "
        f"failed_forced_authorized_remove={failed_forced_authorized_remove} "
        f"failed_forced_binding_dhcp_remove={failed_forced_binding_dhcp_remove} "
        f"failed_hotspot_host_cleanup={failed_hotspot_host_cleanup} "
        f"skipped_no_ip={skipped_no_ip} skipped_not_allowed={skipped_not_allowed} "
        f"skipped_exempt={skipped_exempt} "
        f"skipped_authorized_device_ip={skipped_authorized_device_ip} "
        f"skipped_authorized_device_mac={skipped_authorized_device_mac} "
        f"skipped_binding_dhcp_trusted={skipped_binding_dhcp_trusted} "
        f"skipped_low_uptime={skipped_low_uptime} skipped_authorized_or_bypassed={skipped_authorized}"
    )

    if apply and (
        failed_add_or_refresh > 0
        or failed_remove > 0
        or failed_forced_exempt_remove > 0
        or failed_forced_authorized_remove > 0
        or failed_forced_binding_dhcp_remove > 0
    ):
        raise click.ClickException(
            "Sinkronisasi unauthorized selesai dengan kegagalan operasi router: "
            f"failed_add_or_refresh={failed_add_or_refresh}, failed_remove={failed_remove}, "
            f"failed_forced_exempt_remove={failed_forced_exempt_remove}, "
            f"failed_forced_authorized_remove={failed_forced_authorized_remove}, "
            f"failed_forced_binding_dhcp_remove={failed_forced_binding_dhcp_remove}"
        )
