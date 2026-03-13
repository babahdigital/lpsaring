# backend/app/commands/sync_unauthorized_hosts_command.py

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from app.infrastructure.gateways.mikrotik_client import (
    get_firewall_address_list_entries,
    get_hotspot_hosts,
    get_mikrotik_connection,
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


def _collect_dhcp_lease_snapshot(api) -> Tuple[set[str], set[Tuple[str, str]], set[str], set[str]]:
    """Kumpulkan snapshot DHCP lease yang usable (bukan waiting).

    Returns:
    - mac_set: semua MAC dari lease aktif
    - mac_ip_pairs: pasangan (MAC, IP) dari lease aktif
    - ip_set: semua IP dari lease aktif
    - lpsaring_macs: MAC dari lease yang dikelola aplikasi (comment 'lpsaring|static-dhcp').
      Ini adalah MAC yang sudah pernah di-login OTP — dilindungi dari unauthorized list
      meskipun ip-binding sementara tidak ada (e.g. MAC randomization, ip-binding reset).
    """
    mac_set: set[str] = set()
    mac_ip_pairs: set[Tuple[str, str]] = set()
    ip_set: set[str] = set()
    lpsaring_macs: set[str] = set()

    try:
        rows = api.get_resource("/ip/dhcp-server/lease").get() or []
    except Exception:
        return mac_set, mac_ip_pairs, ip_set, lpsaring_macs

    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "waiting":
            continue

        mac = str(row.get("mac-address") or "").strip().upper()
        ip_text = _normalize_ip_for_compare(row.get("address") or "")
        comment = str(row.get("comment") or "").strip()

        if mac:
            mac_set.add(mac)
            if "lpsaring|static-dhcp" in comment:
                lpsaring_macs.add(mac)
        if ip_text:
            ip_set.add(ip_text)
        if mac and ip_text:
            mac_ip_pairs.add((mac, ip_text))

    return mac_set, mac_ip_pairs, ip_set, lpsaring_macs


def _resolve_critical_overlap_keep_list(
    present_lists: set[str],
    *,
    list_active: str,
    list_fup: str,
    list_blocked: str,
) -> Optional[str]:
    normalized = {name for name in present_lists if name}
    if not normalized:
        return None

    # Priority policy: blocked > fup > active.
    if list_blocked and list_blocked in normalized:
        return list_blocked
    if list_fup and list_fup in normalized:
        return list_fup
    if list_active and list_active in normalized:
        return list_active

    return sorted(normalized)[0]


def _plan_critical_status_overlap_removals(
    *,
    ip_to_lists: Dict[str, set[str]],
    list_active: str,
    list_fup: str,
    list_blocked: str,
) -> List[Tuple[str, str, str]]:
    known_lists = {name for name in (list_active, list_fup, list_blocked) if name}
    plans: List[Tuple[str, str, str]] = []

    for ip_raw in sorted(ip_to_lists.keys()):
        ip_text = _normalize_ip_for_compare(ip_raw)
        if not ip_text:
            continue

        present_lists = {name for name in ip_to_lists.get(ip_raw, set()) if name in known_lists}
        if len(present_lists) <= 1:
            continue

        keep_list = _resolve_critical_overlap_keep_list(
            present_lists,
            list_active=list_active,
            list_fup=list_fup,
            list_blocked=list_blocked,
        )
        if not keep_list:
            continue

        for list_name in sorted(present_lists):
            if list_name == keep_list:
                continue
            plans.append((ip_text, list_name, keep_list))

    return plans


@dataclass
class UnauthorizedSyncDbState:
    resolved_list: str
    resolved_timeout: str
    resolved_min_uptime: int
    status_list_names: set[str]
    list_active: str
    list_fup: str
    list_blocked: str
    authorized_device_ips: set[str]
    authorized_device_macs: set[str]


def _load_unauthorized_sync_db_state(
    *,
    list_name: Optional[str],
    timeout: Optional[str],
    min_uptime_minutes: Optional[int],
) -> UnauthorizedSyncDbState:
    try:
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

        list_active = str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active").strip()
        list_fup = str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup").strip()
        list_inactive = str(
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive"
        ).strip()
        list_expired = str(
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired"
        ).strip()
        list_habis = str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis").strip()
        list_blocked = str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked").strip()

        status_list_names = {
            name
            for name in {list_active, list_fup, list_inactive, list_expired, list_habis, list_blocked}
            if name and name != resolved_list
        }

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

        return UnauthorizedSyncDbState(
            resolved_list=resolved_list,
            resolved_timeout=resolved_timeout,
            resolved_min_uptime=resolved_min_uptime,
            status_list_names=status_list_names,
            list_active=list_active,
            list_fup=list_fup,
            list_blocked=list_blocked,
            authorized_device_ips=authorized_device_ips,
            authorized_device_macs=authorized_device_macs,
        )
    finally:
        # Lepas sesi lebih awal agar task Celery tidak menahan transaksi idle
        # selama operasi RouterOS yang bisa berlangsung puluhan detik.
        db.session.remove()


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

    db_state = _load_unauthorized_sync_db_state(
        list_name=list_name,
        timeout=timeout,
        min_uptime_minutes=min_uptime_minutes,
    )
    resolved_list = db_state.resolved_list
    resolved_timeout = db_state.resolved_timeout
    resolved_min_uptime = db_state.resolved_min_uptime
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

    authorized_device_ips = db_state.authorized_device_ips
    authorized_device_macs = db_state.authorized_device_macs

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
    forced_status_overlap_remove = 0
    forced_critical_status_overlap_remove = 0
    hotspot_host_cleanup_removed = 0
    failed_add_or_refresh = 0
    failed_remove = 0
    failed_forced_exempt_remove = 0
    failed_forced_authorized_remove = 0
    failed_forced_binding_dhcp_remove = 0
    failed_forced_status_overlap_remove = 0
    failed_forced_critical_status_overlap_remove = 0
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
        dhcp_macs, dhcp_pairs, dhcp_ips, dhcp_lpsaring_macs = _collect_dhcp_lease_snapshot(api)
        if not trust_binding_and_dhcp:
            dhcp_lpsaring_macs = set()

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
                continue

            if mac and mac in authorized_device_macs:
                skipped_authorized_device_mac += 1
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
                    continue

            # Guard MAC randomization: jika MAC tercatat di DHCP lease yang dikelola aplikasi
            # (pernah login OTP sebelumnya), percayai host ini meskipun ip-binding belum/tidak ada.
            if trust_binding_and_dhcp and mac and mac in dhcp_lpsaring_macs:
                skipped_binding_dhcp_trusted += 1
                if ip_text:
                    trusted_binding_dhcp_ips.add(ip_text)
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

        # Set semua IP yang sekarang ada di unauthorized list (managed maupun tidak).
        # Digunakan untuk menghindari API call no-op pada safety guard loops di bawah.
        existing_unauthorized_ips: set[str] = {
            _normalize_ip_for_compare(e.get("address") or "")
            for e in existing
            if _normalize_ip_for_compare(e.get("address") or "")
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
            if normalized_exempt_ip not in existing_unauthorized_ips:
                continue  # Tidak ada di unauthorized list, skip API call no-op.
            forced_exempt_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, normalized_exempt_ip, resolved_list)
                if not ok_remove:
                    failed_forced_exempt_remove += 1

        # Final safety guard: IP device yang sudah authorized di DB tidak boleh bertahan di unauthorized list.
        for authorized_ip in sorted(authorized_device_ips):
            if not authorized_ip:
                continue
            if authorized_ip not in existing_unauthorized_ips:
                continue  # Tidak ada di unauthorized list, skip API call no-op.
            forced_authorized_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, authorized_ip, resolved_list)
                if not ok_remove:
                    failed_forced_authorized_remove += 1

        # Final safety guard: trusted ip-binding + dhcp lease juga tidak boleh bertahan di unauthorized list.
        for trusted_ip in sorted(trusted_binding_dhcp_ips):
            if not trusted_ip:
                continue
            if trusted_ip not in existing_unauthorized_ips:
                continue  # Tidak ada di unauthorized list, skip API call no-op.
            forced_binding_dhcp_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, trusted_ip, resolved_list)
                if not ok_remove:
                    failed_forced_binding_dhcp_remove += 1

        # Final safety guard: IP yang sudah terdaftar di list status manapun
        # (aktif/fup/inactive/expired/habis/blocked) tidak boleh overlap di unauthorized.
        status_list_names = db_state.status_list_names

        protected_status_ips: set[str] = set()
        for status_list_name in sorted(status_list_names):
            ok_status_list, status_entries, _status_msg = get_firewall_address_list_entries(api, status_list_name)
            if not ok_status_list:
                continue
            for status_entry in status_entries:
                status_ip = _normalize_ip_for_compare(status_entry.get("address") or "")
                if status_ip:
                    protected_status_ips.add(status_ip)

        for status_ip in sorted(protected_status_ips):
            if not status_ip:
                continue
            if status_ip not in existing_unauthorized_ips:
                continue  # Tidak ada di unauthorized list, skip API call no-op.
            forced_status_overlap_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, status_ip, resolved_list)
                if not ok_remove:
                    failed_forced_status_overlap_remove += 1

        # Final safety guard: list status kritikal tidak boleh overlap untuk IP yang sama.
        # Prioritas yang dipertahankan: blocked > fup > active.
        list_active = db_state.list_active
        list_fup = db_state.list_fup
        list_blocked = db_state.list_blocked

        critical_lists = sorted({name for name in (list_active, list_fup, list_blocked) if name})
        critical_ip_to_lists: Dict[str, set[str]] = {}
        for critical_list_name in critical_lists:
            ok_status_list, status_entries, _status_msg = get_firewall_address_list_entries(api, critical_list_name)
            if not ok_status_list:
                continue
            for status_entry in status_entries:
                status_ip = _normalize_ip_for_compare(status_entry.get("address") or "")
                if not status_ip:
                    continue
                critical_ip_to_lists.setdefault(status_ip, set()).add(critical_list_name)

        critical_overlap_plans = _plan_critical_status_overlap_removals(
            ip_to_lists=critical_ip_to_lists,
            list_active=list_active,
            list_fup=list_fup,
            list_blocked=list_blocked,
        )

        for status_ip, remove_list_name, _keep_list_name in critical_overlap_plans:
            forced_critical_status_overlap_remove += 1
            if apply:
                ok_remove, _remove_msg = remove_address_list_entry(api, status_ip, remove_list_name)
                if not ok_remove:
                    failed_forced_critical_status_overlap_remove += 1

    click.echo(
        f"processed_hosts={processed} desired_block_ips={len(desired)} "
        f"would_add_or_refresh={to_add} would_remove={to_remove} apply={apply} "
        f"forced_exempt_remove={forced_exempt_remove} forced_authorized_remove={forced_authorized_remove} "
        f"forced_binding_dhcp_remove={forced_binding_dhcp_remove} "
        f"forced_status_overlap_remove={forced_status_overlap_remove} "
        f"forced_critical_status_overlap_remove={forced_critical_status_overlap_remove} "
        f"hotspot_host_cleanup_removed={hotspot_host_cleanup_removed} "
        f"failed_add_or_refresh={failed_add_or_refresh} failed_remove={failed_remove} "
        f"failed_forced_exempt_remove={failed_forced_exempt_remove} "
        f"failed_forced_authorized_remove={failed_forced_authorized_remove} "
        f"failed_forced_binding_dhcp_remove={failed_forced_binding_dhcp_remove} "
        f"failed_forced_status_overlap_remove={failed_forced_status_overlap_remove} "
        f"failed_forced_critical_status_overlap_remove={failed_forced_critical_status_overlap_remove} "
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
        or failed_forced_status_overlap_remove > 0
        or failed_forced_critical_status_overlap_remove > 0
    ):
        raise click.ClickException(
            "Sinkronisasi unauthorized selesai dengan kegagalan operasi router: "
            f"failed_add_or_refresh={failed_add_or_refresh}, failed_remove={failed_remove}, "
            f"failed_forced_exempt_remove={failed_forced_exempt_remove}, "
            f"failed_forced_authorized_remove={failed_forced_authorized_remove}, "
            f"failed_forced_binding_dhcp_remove={failed_forced_binding_dhcp_remove}, "
            f"failed_forced_status_overlap_remove={failed_forced_status_overlap_remove}, "
            f"failed_forced_critical_status_overlap_remove={failed_forced_critical_status_overlap_remove}"
        )
