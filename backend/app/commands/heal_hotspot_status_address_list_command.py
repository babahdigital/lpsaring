from __future__ import annotations

import ipaddress
import re
from typing import Iterable, List, Optional, Set

import click
from flask import current_app
from flask.cli import with_appcontext

from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, remove_address_list_entry
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.utils.formatters import get_phone_number_variations


def _resolve_networks(cidrs: Iterable[str]) -> List[ipaddress._BaseNetwork]:
    networks: List[ipaddress._BaseNetwork] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(str(cidr), strict=False))
        except Exception:
            continue
    return networks


def _is_ip_allowed(ip_text: str, networks: List[ipaddress._BaseNetwork]) -> bool:
    text = str(ip_text or "").strip()
    if not text:
        return False

    if not networks:
        return True

    try:
        ip_obj = ipaddress.ip_address(text)
    except Exception:
        return False

    return any(ip_obj in net for net in networks)


def _extract_user_phone(comment: str) -> Optional[str]:
    match = re.search(r"(?:^|\|)user=([^|]+)", str(comment or ""))
    if not match:
        return None
    candidate = str(match.group(1) or "").strip()
    return candidate or None


def _find_user_by_phone(phone: str) -> Optional[User]:
    variants = set(get_phone_number_variations(str(phone)) or [])
    variants.add(str(phone).strip())
    variants = {value for value in variants if value}

    if not variants:
        return None

    return (
        db.session.query(User)
        .filter(
            User.phone_number.in_(list(variants)),
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
        )
        .first()
    )


@click.command("heal-hotspot-status-address-list")
@click.option("--apply/--dry-run", default=False, show_default=True)
@click.option("--resync-users/--no-resync-users", default=True, show_default=True)
@with_appcontext
def heal_hotspot_status_address_list_command(apply: bool, resync_users: bool) -> None:
    """Bersihkan entry address-list status lpsaring di luar CIDR hotspot.

    Tujuan:
    - Menghapus entry stale out-of-CIDR (mis. 10.x, 172.16.8.x) dari list status managed.
    - Opsional re-sync user terdampak agar entry valid hotspot CIDR ditulis ulang.
    """

    cidrs = current_app.config.get("MIKROTIK_UNAUTHORIZED_CIDRS") or current_app.config.get("HOTSPOT_CLIENT_IP_CIDRS") or []
    networks = _resolve_networks(cidrs)
    if not networks:
        raise click.ClickException("CIDR hotspot kosong/tidak valid. Set MIKROTIK_UNAUTHORIZED_CIDRS atau HOTSPOT_CLIENT_IP_CIDRS.")

    target_lists = {
        current_app.config.get("MIKROTIK_ADDRESS_LIST_ACTIVE", "active"),
        current_app.config.get("MIKROTIK_ADDRESS_LIST_FUP", "fup"),
        current_app.config.get("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive"),
        current_app.config.get("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired"),
        current_app.config.get("MIKROTIK_ADDRESS_LIST_HABIS", "habis"),
        current_app.config.get("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked"),
    }

    scanned = 0
    managed = 0
    out_of_cidr = 0
    removed = 0
    remove_failed = 0
    affected_users: Set[str] = set()

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException("Gagal konek MikroTik")

        rows = api.get_resource("/ip/firewall/address-list").get() or []
        for row in rows:
            scanned += 1
            list_name = str(row.get("list") or "").strip()
            address = str(row.get("address") or "").strip()
            comment = str(row.get("comment") or "")

            if list_name not in target_lists:
                continue
            if "lpsaring|status=" not in comment:
                continue

            managed += 1
            if _is_ip_allowed(address, networks):
                continue

            out_of_cidr += 1
            phone = _extract_user_phone(comment)
            if phone:
                affected_users.add(phone)

            if not apply:
                click.echo(f"DRY-RUN remove list={list_name} ip={address} comment={comment}")
                continue

            ok_remove, _msg = remove_address_list_entry(api_connection=api, address=address, list_name=list_name)
            if ok_remove:
                removed += 1
            else:
                remove_failed += 1

    resynced_ok = 0
    resynced_failed = 0
    resync_user_not_found = 0

    if apply and resync_users and affected_users:
        for phone in sorted(affected_users):
            user = _find_user_by_phone(phone)
            if user is None:
                resync_user_not_found += 1
                continue

            if sync_address_list_for_single_user(user):
                resynced_ok += 1
            else:
                resynced_failed += 1

    click.echo(
        " ".join(
            [
                f"apply={apply}",
                f"allowed_cidrs={cidrs}",
                f"scanned={scanned}",
                f"managed={managed}",
                f"out_of_cidr={out_of_cidr}",
                f"removed={removed}",
                f"remove_failed={remove_failed}",
                f"affected_users={len(affected_users)}",
                f"resynced_ok={resynced_ok}",
                f"resynced_failed={resynced_failed}",
                f"resync_user_not_found={resync_user_not_found}",
            ]
        )
    )

    if apply and remove_failed > 0:
        raise click.ClickException(f"Heal selesai dengan remove_failed={remove_failed}")
