from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Set, Tuple

import click
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserDevice
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, remove_address_list_entry
from app.services import settings_service
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.utils.formatters import format_to_local_phone, get_phone_number_variations

UID_RE = re.compile(r"(?:^|[|\s])uid=([^|\s]+)")
USER_RE = re.compile(r"(?:^|[|\s])user=([^|\s]+)")


def _normalize_binding_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "regular"


def _extract_uid(comment: Any) -> str:
    text = str(comment or "")
    match = UID_RE.search(text)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _extract_user_token(comment: Any) -> str:
    text = str(comment or "")
    match = USER_RE.search(text)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _resolve_managed_lists() -> Dict[str, str]:
    return {
        "active": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active").strip(),
        "fup": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup").strip(),
        "inactive": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive").strip(),
        "expired": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired").strip(),
        "habis": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis").strip(),
        "blocked": str(settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked").strip(),
        "unauthorized": str(
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_UNAUTHORIZED", "unauthorized") or "unauthorized"
        ).strip(),
    }


def _build_user_indexes() -> Tuple[Dict[str, User], Dict[str, str], Dict[str, Set[str]]]:
    users = db.session.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
        )
    ).all()

    users_by_uid: Dict[str, User] = {}
    uid_by_phone_variant: Dict[str, str] = {}

    for user in users:
        uid = str(user.id)
        users_by_uid[uid] = user

        raw_phone = str(getattr(user, "phone_number", "") or "").strip()
        phone_tokens = set()
        phone_08 = format_to_local_phone(raw_phone)
        if phone_08:
            phone_tokens.add(phone_08)

        try:
            for value in get_phone_number_variations(raw_phone):
                if value:
                    phone_tokens.add(str(value).strip())
        except Exception:
            pass

        for token in phone_tokens:
            if token:
                uid_by_phone_variant[token] = uid

    authorized_macs_by_uid: Dict[str, Set[str]] = defaultdict(set)
    rows = db.session.execute(
        select(UserDevice.user_id, UserDevice.mac_address).where(UserDevice.is_authorized.is_(True))
    ).all()
    for user_id, mac in rows:
        uid = str(user_id)
        mac_norm = str(mac or "").strip().upper()
        if mac_norm:
            authorized_macs_by_uid[uid].add(mac_norm)

    return users_by_uid, uid_by_phone_variant, authorized_macs_by_uid


def _build_binding_indexes(
    ip_binding_rows: list[dict[str, Any]],
) -> Dict[str, Set[str]]:
    token_any: Set[str] = set()
    token_nonblocked: Set[str] = set()
    token_blocked: Set[str] = set()
    mac_any: Set[str] = set()
    mac_nonblocked: Set[str] = set()
    mac_blocked: Set[str] = set()
    ip_any: Set[str] = set()
    ip_nonblocked: Set[str] = set()
    ip_blocked: Set[str] = set()

    for row in ip_binding_rows:
        binding_type = _normalize_binding_type(row.get("type"))
        is_blocked = binding_type == "blocked"

        uid = _extract_uid(row.get("comment"))
        user_token = _extract_user_token(row.get("comment"))
        mac = str(row.get("mac-address") or "").strip().upper()
        ip_address = str(row.get("address") or "").strip()

        for token in [uid, user_token]:
            if not token:
                continue
            token_any.add(token)
            if is_blocked:
                token_blocked.add(token)
            else:
                token_nonblocked.add(token)

        if mac:
            mac_any.add(mac)
            if is_blocked:
                mac_blocked.add(mac)
            else:
                mac_nonblocked.add(mac)

        if ip_address and ip_address != "0.0.0.0":
            ip_any.add(ip_address)
            if is_blocked:
                ip_blocked.add(ip_address)
            else:
                ip_nonblocked.add(ip_address)

    return {
        "token_any": token_any,
        "token_nonblocked": token_nonblocked,
        "token_blocked": token_blocked,
        "mac_any": mac_any,
        "mac_nonblocked": mac_nonblocked,
        "mac_blocked": mac_blocked,
        "ip_any": ip_any,
        "ip_nonblocked": ip_nonblocked,
        "ip_blocked": ip_blocked,
    }


def _resolve_user_uid(
    uid_token: str,
    user_token: str,
    users_by_uid: Dict[str, User],
    uid_by_phone_variant: Dict[str, str],
) -> str:
    if uid_token and uid_token in users_by_uid:
        return uid_token
    if user_token and user_token in uid_by_phone_variant:
        return uid_by_phone_variant[user_token]
    return ""


def _has_binding_for_row(
    *,
    address: str,
    list_name: str,
    uid_token: str,
    user_token: str,
    resolved_uid: str,
    mac_hint: str,
    binding_indexes: Dict[str, Set[str]],
    authorized_macs_by_uid: Dict[str, Set[str]],
    blocked_list_name: str,
) -> bool:
    require_blocked = bool(blocked_list_name and list_name == blocked_list_name)

    if require_blocked:
        token_set = binding_indexes["token_blocked"]
        mac_set = binding_indexes["mac_blocked"]
        ip_set = binding_indexes["ip_blocked"]
    else:
        token_set = binding_indexes["token_nonblocked"]
        mac_set = binding_indexes["mac_nonblocked"]
        ip_set = binding_indexes["ip_nonblocked"]

    if uid_token and uid_token in token_set:
        return True
    if user_token and user_token in token_set:
        return True

    if mac_hint and mac_hint in mac_set:
        return True

    if resolved_uid:
        for mac in authorized_macs_by_uid.get(resolved_uid, set()):
            if mac in mac_set:
                return True

    if address and address in ip_set:
        return True

    return False


@click.command("prune-hotspot-status-without-binding")
@click.option("--apply/--dry-run", default=False, show_default=True)
@click.option("--overlap-unauthorized-only/--all-candidates", default=False, show_default=True)
@click.option("--resync-users/--no-resync-users", default=True, show_default=True)
@click.option("--managed-only/--include-all", default=True, show_default=True)
@with_appcontext
def prune_hotspot_status_without_binding_command(
    apply: bool,
    overlap_unauthorized_only: bool,
    resync_users: bool,
    managed_only: bool,
) -> None:
    """Prune entry status-list managed yang tidak punya ip-binding policy-compatible.

    Rules:
    - entry non-unauthorized tanpa binding dihapus (opsional overlap-only dulu)
    - unauthorized list tidak disentuh oleh command ini
    """

    list_names = _resolve_managed_lists()
    unauthorized_list = list_names["unauthorized"]
    blocked_list = list_names["blocked"]

    managed_status_lists = {
        list_names["active"],
        list_names["fup"],
        list_names["inactive"],
        list_names["expired"],
        list_names["habis"],
        list_names["blocked"],
    }
    managed_status_lists = {name for name in managed_status_lists if name and name != unauthorized_list}

    users_by_uid, uid_by_phone_variant, authorized_macs_by_uid = _build_user_indexes()

    scanned = 0
    managed_rows = 0
    with_binding = 0
    without_binding = 0
    overlap_without_binding = 0
    candidates = 0
    removed = 0
    remove_failed = 0
    affected_user_uids: Set[str] = set()

    with get_mikrotik_connection() as api:
        if not api:
            raise click.ClickException("Gagal konek MikroTik")

        all_rows = api.get_resource("/ip/firewall/address-list").get() or []
        ip_binding_rows = api.get_resource("/ip/hotspot/ip-binding").get() or []
        binding_indexes = _build_binding_indexes(ip_binding_rows)

        unauthorized_ips = {
            str(row.get("address") or "").strip()
            for row in all_rows
            if str(row.get("list") or "").strip() == unauthorized_list
        }

        for row in all_rows:
            scanned += 1
            list_name = str(row.get("list") or "").strip()
            if list_name not in managed_status_lists:
                continue

            comment = str(row.get("comment") or "")
            if managed_only and "lpsaring|status=" not in comment:
                continue

            managed_rows += 1

            address = str(row.get("address") or "").strip()
            uid_token = _extract_uid(comment)
            user_token = _extract_user_token(comment)
            mac_hint = str(row.get("mac-address") or "").strip().upper()
            resolved_uid = _resolve_user_uid(uid_token, user_token, users_by_uid, uid_by_phone_variant)

            has_binding = _has_binding_for_row(
                address=address,
                list_name=list_name,
                uid_token=uid_token,
                user_token=user_token,
                resolved_uid=resolved_uid,
                mac_hint=mac_hint,
                binding_indexes=binding_indexes,
                authorized_macs_by_uid=authorized_macs_by_uid,
                blocked_list_name=blocked_list,
            )

            if has_binding:
                with_binding += 1
                continue

            without_binding += 1
            is_overlap_unauthorized = bool(address and address in unauthorized_ips)
            if is_overlap_unauthorized:
                overlap_without_binding += 1

            if overlap_unauthorized_only and not is_overlap_unauthorized:
                continue

            candidates += 1
            if resolved_uid:
                affected_user_uids.add(resolved_uid)

            if not apply:
                click.echo(
                    f"DRY-RUN remove list={list_name} ip={address} uid={uid_token or '-'} user={user_token or '-'}"
                )
                continue

            ok_remove, _msg = remove_address_list_entry(api_connection=api, address=address, list_name=list_name)
            if ok_remove:
                removed += 1
            else:
                remove_failed += 1

    resynced_ok = 0
    resynced_failed = 0
    resync_user_not_found = 0

    if apply and resync_users and affected_user_uids:
        for uid in sorted(affected_user_uids):
            user = users_by_uid.get(uid)
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
                f"overlap_unauthorized_only={overlap_unauthorized_only}",
                f"scanned={scanned}",
                f"managed_rows={managed_rows}",
                f"with_binding={with_binding}",
                f"without_binding={without_binding}",
                f"overlap_without_binding={overlap_without_binding}",
                f"candidates={candidates}",
                f"removed={removed}",
                f"remove_failed={remove_failed}",
                f"affected_users={len(affected_user_uids)}",
                f"resynced_ok={resynced_ok}",
                f"resynced_failed={resynced_failed}",
                f"resync_user_not_found={resync_user_not_found}",
            ]
        )
    )

    if apply and remove_failed > 0:
        raise click.ClickException(f"Prune selesai dengan remove_failed={remove_failed}")
