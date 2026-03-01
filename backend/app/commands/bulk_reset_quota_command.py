# backend/app/commands/bulk_reset_quota_command.py

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserRole
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    get_hotspot_host_usage_map,
    get_mikrotik_connection,
    set_hotspot_user_profile,
)
from app.services import settings_service
from app.services.hotspot_sync_service import (
    REDIS_LAST_BYTES_PREFIX,
    _calculate_remaining,
    _sync_address_list_status,
)
from app.utils.formatters import format_to_local_phone, get_app_local_datetime

logger = logging.getLogger(__name__)


@dataclass
class ResetCounters:
    scope_users: int = 0
    eligible_reset: int = 0
    expired_skip: int = 0
    updated_db: int = 0
    updated_devices_baseline: int = 0
    mikrotik_profile_updated: int = 0
    mikrotik_profile_failed: int = 0
    mikrotik_user_updated: int = 0
    mikrotik_user_failed: int = 0


def _end_of_month_utc(now_utc: datetime) -> datetime:
    now_local = get_app_local_datetime(now_utc)
    last_day = calendar.monthrange(now_local.year, now_local.month)[1]
    end_local = now_local.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
    return end_local.astimezone(dt_timezone.utc)


def _is_user_expired(user: User, now_utc: datetime) -> bool:
    if not user.quota_expiry_date:
        return False
    now_local = get_app_local_datetime(now_utc)
    expiry_local = get_app_local_datetime(user.quota_expiry_date)
    return bool(expiry_local < now_local)


@click.command("bulk-reset-quota")
@click.option(
    "--quota-mb", type=int, default=10240, show_default=True, help="Set total_quota_purchased_mb (MB). 10240=10GB"
)
@click.option(
    "--expiry",
    type=click.Choice(["end-of-month", "keep"], case_sensitive=False),
    default="end-of-month",
    show_default=True,
    help="Set quota_expiry_date for eligible users.",
)
@click.option("--apply-mikrotik/--no-mikrotik", default=True, show_default=True)
@click.option("--dry-run/--apply", default=True, show_default=True)
@click.option(
    "--limit", type=int, default=0, show_default=True, help="Limit number of eligible users processed (0 = all)."
)
@click.option(
    "--server-name",
    type=str,
    default=None,
    help="Batasi ke User dengan mikrotik_server_name tertentu (contoh: srv-user).",
)
@click.option(
    "--enforce-expired-profile/--skip-expired-profile",
    default=True,
    show_default=True,
    help="Saat apply-mikrotik: paksa profile expired untuk user expired.",
)
@with_appcontext
def bulk_reset_quota_command(
    quota_mb: int,
    expiry: str,
    apply_mikrotik: bool,
    dry_run: bool,
    limit: int,
    server_name: Optional[str],
    enforce_expired_profile: bool,
) -> None:
    """Bulk reset kuota untuk semua USER aktif+approved.

    - Eligible (TIDAK expired):
      - total_quota_purchased_mb = quota_mb
      - total_quota_used_mb = 0
      - quota_expiry_date = end-of-month (atau keep)
      - reset baseline bytes per-device (DB + Redis) supaya pemakaian tidak loncat
      - sinkron profile + address-list ke MikroTik

    - Expired (quota_expiry_date < now):
      - tidak diberi kuota
      - set profile MikroTik ke expired (jika memungkinkan)

    Catatan: hanya role USER, tidak menyentuh KOMANDAN.
    """

    if quota_mb < 0:
        raise click.ClickException("quota-mb tidak boleh negatif")

    now_utc = datetime.now(dt_timezone.utc)
    expiry_target_utc: Optional[datetime] = None
    if expiry.lower() == "end-of-month":
        expiry_target_utc = _end_of_month_utc(now_utc)

    filters: list[Any] = [
        User.is_active,
        User.role == UserRole.USER,
        User.approval_status == ApprovalStatus.APPROVED,
    ]
    if server_name:
        filters.append(User.mikrotik_server_name == server_name)

    users_query = select(User).where(*filters).options(selectinload(User.devices)).order_by(User.created_at.asc())
    users = list(db.session.scalars(users_query).all())

    counters = ResetCounters(scope_users=len(users))

    eligible_users: list[User] = []
    expired_users: list[User] = []
    for user in users:
        if _is_user_expired(user, now_utc):
            counters.expired_skip += 1
            expired_users.append(user)
        else:
            counters.eligible_reset += 1
            eligible_users.append(user)

    if limit and limit > 0:
        eligible_users = eligible_users[:limit]

    click.echo(
        f"SCOPE users={counters.scope_users} eligible_reset={counters.eligible_reset} expired_skip={counters.expired_skip} limit={limit or 'ALL'}"
    )
    click.echo(
        f"PARAM quota_mb={quota_mb} expiry={expiry} expiry_target_utc={expiry_target_utc.isoformat() if expiry_target_utc else 'KEEP'} mikrotik={apply_mikrotik} mode={'DRY_RUN' if dry_run else 'APPLY'}"
    )
    click.echo(
        f"FILTER server_name={server_name or 'ALL'} enforce_expired_profile={enforce_expired_profile}"
    )

    if dry_run:
        sample_e = eligible_users[:5]
        sample_x = expired_users[:5]
        click.echo("SAMPLE eligible_reset (max 5)")
        for i, u in enumerate(sample_e, 1):
            click.echo(
                f"  {i}. {u.phone_number} | {u.full_name} | expiry={u.quota_expiry_date.isoformat() if u.quota_expiry_date else '-'}"
            )
        click.echo("SAMPLE expired_skip (max 5)")
        for i, u in enumerate(sample_x, 1):
            click.echo(
                f"  {i}. {u.phone_number} | {u.full_name} | expiry={u.quota_expiry_date.isoformat() if u.quota_expiry_date else '-'}"
            )
        return

    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        try:
            from app.services.hotspot_sync_service import _get_redis_client

            redis_client = _get_redis_client()
        except Exception:
            redis_client = None

    expired_profile = settings_service.get_setting("MIKROTIK_EXPIRED_PROFILE", "expired") or "expired"

    with get_mikrotik_connection() as api:
        host_usage_map: dict[str, dict[str, Any]] = {}
        if apply_mikrotik:
            if not api:
                raise click.ClickException("Gagal konek MikroTik (apply-mikrotik=True)")
            ok_host, host_usage_map, msg = get_hotspot_host_usage_map(api)
            if not ok_host:
                raise click.ClickException(f"Gagal ambil hotspot host usage map: {msg}")

        for user in eligible_users:
            # DB reset
            user.total_quota_purchased_mb = int(quota_mb)
            user.total_quota_used_mb = 0
            user.is_unlimited_user = False
            if expiry_target_utc is not None:
                user.quota_expiry_date = expiry_target_utc

            # Reset baseline usage per-device
            for device in list(user.devices or []):
                mac = (device.mac_address or "").upper()
                if not mac:
                    continue

                # Baseline to current bytes_total if available; else clear so next sync sets baseline.
                host = host_usage_map.get(mac) if host_usage_map else None
                if host:
                    bytes_total = int(host.get("bytes_in", 0)) + int(host.get("bytes_out", 0))
                    device.last_bytes_total = bytes_total
                    device.last_bytes_updated_at = now_utc
                    counters.updated_devices_baseline += 1
                    if redis_client is not None:
                        try:
                            redis_client.set(f"{REDIS_LAST_BYTES_PREFIX}{mac}", bytes_total)
                        except Exception:
                            pass
                else:
                    device.last_bytes_total = None
                    device.last_bytes_updated_at = None
                    if redis_client is not None:
                        try:
                            redis_client.delete(f"{REDIS_LAST_BYTES_PREFIX}{mac}")
                        except Exception:
                            pass

            counters.updated_db += 1

            if not apply_mikrotik:
                continue

            username_08 = format_to_local_phone(user.phone_number)
            if not username_08:
                continue

            remaining_mb, remaining_percent = _calculate_remaining(user)
            now_local = get_app_local_datetime(now_utc)
            expiry_local = get_app_local_datetime(user.quota_expiry_date) if user.quota_expiry_date else None
            is_expired = bool(expiry_local and expiry_local < now_local)

            # Profile update (safe)
            target_profile = user.mikrotik_profile_name
            if is_expired:
                target_profile = expired_profile
            if target_profile:
                ok, _msg = set_hotspot_user_profile(
                    api_connection=api, username_or_id=username_08, new_profile_name=target_profile
                )
                if ok:
                    user.mikrotik_profile_name = target_profile
                    counters.mikrotik_profile_updated += 1
                else:
                    counters.mikrotik_profile_failed += 1

            # Ensure hotspot user exists & set limit-bytes-total (requires password)
            if user.mikrotik_password:
                ok_user, _msg = activate_or_update_hotspot_user(
                    api_connection=api,
                    user_mikrotik_username=username_08,
                    mikrotik_profile_name=user.mikrotik_profile_name or target_profile or expired_profile,
                    hotspot_password=user.mikrotik_password,
                    comment=f"bulk-reset-quota {now_utc.isoformat()}",
                    limit_bytes_total=(int(quota_mb) * 1024 * 1024) if not is_expired else 1,
                    server=user.mikrotik_server_name or "all",
                )
                if ok_user:
                    counters.mikrotik_user_updated += 1
                else:
                    counters.mikrotik_user_failed += 1

            # Address-list sync
            try:
                _sync_address_list_status(api, user, username_08, remaining_mb, remaining_percent, is_expired)
            except Exception:
                pass

        # expired users: optional Mikrotik profile enforcement
        if apply_mikrotik and api and enforce_expired_profile:
            for user in expired_users:
                username_08 = format_to_local_phone(user.phone_number)
                if not username_08:
                    continue
                ok, _msg = set_hotspot_user_profile(
                    api_connection=api, username_or_id=username_08, new_profile_name=expired_profile
                )
                if ok:
                    user.mikrotik_profile_name = expired_profile
                    counters.mikrotik_profile_updated += 1
                else:
                    counters.mikrotik_profile_failed += 1

    db.session.commit()

    click.echo(
        "RESULT "
        f"updated_db={counters.updated_db} "
        f"updated_devices_baseline={counters.updated_devices_baseline} "
        f"mikrotik_profile_ok={counters.mikrotik_profile_updated} mikrotik_profile_fail={counters.mikrotik_profile_failed} "
        f"mikrotik_user_ok={counters.mikrotik_user_updated} mikrotik_user_fail={counters.mikrotik_user_failed}"
    )
