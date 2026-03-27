# backend/app/commands/cleanup_inactive_command.py
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select, func as sa_func
from datetime import datetime, timezone as dt_timezone
import logging

from app.extensions import db
from app.infrastructure.db.models import (
    User, UserRole, DailyUsageLog, QuotaMutationLedger, UserDevice,
    AdminActionLog,
)
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, delete_hotspot_user

logger = logging.getLogger(__name__)

_PROTECTED_ROLES = {UserRole.SUPER_ADMIN}

_ABSOLUTE_DELETE_LIMIT = 20

_CLEANUP_TARGET_ROLES = [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN]


def _compute_last_real_activity_cli(user: User) -> datetime | None:
    """Hitung waktu aktivitas terakhir dari multi sinyal (versi CLI).

    Sama dengan _compute_last_real_activity di hotspot_sync_service; logika
    dipisah agar command tidak bergantung pada import service besar.
    """
    candidates: list[datetime] = []
    if user.last_login_at:
        candidates.append(user.last_login_at)

    latest_usage_date = db.session.scalar(
        select(sa_func.max(DailyUsageLog.log_date)).where(DailyUsageLog.user_id == user.id)
    )
    if latest_usage_date is not None:
        candidates.append(
            datetime.combine(latest_usage_date, datetime.min.time(), tzinfo=dt_timezone.utc)
        )

    latest_mutation_at = db.session.scalar(
        select(sa_func.max(QuotaMutationLedger.created_at)).where(QuotaMutationLedger.user_id == user.id)
    )
    if latest_mutation_at is not None:
        candidates.append(latest_mutation_at if latest_mutation_at.tzinfo else latest_mutation_at.replace(tzinfo=dt_timezone.utc))

    latest_device_at = db.session.scalar(
        select(sa_func.max(UserDevice.last_seen_at)).where(UserDevice.user_id == user.id)
    )
    if latest_device_at is not None:
        candidates.append(latest_device_at if latest_device_at.tzinfo else latest_device_at.replace(tzinfo=dt_timezone.utc))

    # Khusus ADMIN: cek aksi admin terakhir (approve user, inject quota, dll)
    if user.role == UserRole.ADMIN:
        latest_admin_action_at = db.session.scalar(
            select(sa_func.max(AdminActionLog.created_at)).where(AdminActionLog.admin_id == user.id)
        )
        if latest_admin_action_at is not None:
            candidates.append(
                latest_admin_action_at if latest_admin_action_at.tzinfo
                else latest_admin_action_at.replace(tzinfo=dt_timezone.utc)
            )

    if candidates:
        return max(candidates)
    return user.created_at if user.created_at else None


@click.command("cleanup-inactive")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Tampilkan user yang akan dihapus tanpa melakukan penghapusan sesungguhnya.",
)
@with_appcontext
def cleanup_inactive_command(dry_run: bool):
    """
    Hapus pengguna yang sudah sangat lama tidak aktif berdasarkan multi sinyal aktivitas.

    Kriteria \"tidak aktif\" ditentukan dari:
    - last_login_at (login portal/OTP terakhir)
    - DailyUsageLog (pemakaian bandwidth terakhir — penting untuk sistem IP-binding)
    - QuotaMutationLedger (aktivitas kuota terakhir)
    - UserDevice (perubahan device binding terakhir)

    Role target: USER, KOMANDAN, dan ADMIN.
    SUPER_ADMIN tidak akan pernah dihapus oleh perintah ini.

    Threshold diambil dari config INACTIVE_DELETE_DAYS (default 90 hari).
    Gunakan --dry-run terlebih dahulu untuk melihat siapa saja yang akan dihapus.
    """
    delete_days = int(current_app.config.get("INACTIVE_DELETE_DAYS", 90))
    now_utc = datetime.now(dt_timezone.utc)

    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(
        f"{prefix}Memulai cleanup user tidak aktif. "
        f"Threshold: {delete_days} hari (multi sinyal aktivitas)"
    )

    all_candidates = db.session.scalars(
        select(User).where(
            User.role.in_(_CLEANUP_TARGET_ROLES),
            User.role.notin_(_PROTECTED_ROLES),
        )
    ).all()

    users_to_delete: list[tuple[User, int]] = []
    for user in all_candidates:
        last_activity = _compute_last_real_activity_cli(user)
        if not last_activity:
            continue
        days_inactive = (now_utc - last_activity).days
        if days_inactive < delete_days:
            continue
        has_active_quota = (
            user.quota_expiry_date is not None
            and user.quota_expiry_date > now_utc
        )
        if has_active_quota:
            continue
        users_to_delete.append((user, days_inactive))

    if not users_to_delete:
        logger.info(f"{prefix}Tidak ada user tidak aktif yang memenuhi kriteria penghapusan.")
        return

    if len(users_to_delete) > _ABSOLUTE_DELETE_LIMIT:
        logger.error(
            "SAFETY GUARD: Kandidat penghapusan (%d) melebihi batas keamanan (%d). "
            "Proses dibatalkan untuk mencegah penghapusan massal.",
            len(users_to_delete), _ABSOLUTE_DELETE_LIMIT,
        )
        return

    logger.info(f"{prefix}Ditemukan {len(users_to_delete)} user kandidat penghapusan.")

    if dry_run:
        logger.info("[DRY RUN] Daftar user yang AKAN dihapus (belum benar-benar dihapus):")
        for user, days in users_to_delete:
            last_act = _compute_last_real_activity_cli(user)
            logger.info(
                f"  [DRY RUN] {user.full_name} | {user.phone_number} | "
                f"role={user.role.value} | inactive={days} hari | "
                f"last_activity={last_act} | quota_expiry={user.quota_expiry_date}"
            )
        logger.info(f"[DRY RUN] Jalankan tanpa --dry-run untuk menghapus {len(users_to_delete)} user.")
        return

    success_count = 0
    fail_count = 0
    skip_count = 0

    with get_mikrotik_connection() as api:
        if not api:
            logger.error("Gagal mendapatkan koneksi MikroTik. Proses dibatalkan.")
            return

        for user, days in users_to_delete:
            user_label = f"{user.full_name} ({user.phone_number})"
            logger.info(f"Memproses: {user_label} | inactive={days} hari")

            if user.role in _PROTECTED_ROLES:
                logger.warning(f"  SKIP: {user_label} punya role terlindungi ({user.role.value}), tidak dihapus.")
                skip_count += 1
                continue

            if getattr(user, "mikrotik_user_exists", False):
                mt_success, mt_msg = delete_hotspot_user(api, user.phone_number)
                if not mt_success:
                    logger.error(f"  GAGAL hapus MikroTik: {user_label} — {mt_msg}")
                    fail_count += 1
                    continue
                logger.debug(f"  MikroTik OK: {user_label}")
            else:
                logger.debug(f"  MikroTik skip (user belum di MikroTik): {user_label}")

            try:
                target_user_id = user.id
                db.session.delete(user)
                db.session.flush()
                deleted_count = db.session.execute(
                    select(db.func.count()).select_from(User).where(User.id == target_user_id)
                ).scalar()
                if deleted_count != 0:
                    db.session.rollback()
                    logger.error(f"  SAFETY: flush delete tidak efektif untuk {user_label}, rollback.")
                    fail_count += 1
                    continue
                db.session.commit()
                logger.info(f"  BERHASIL dihapus: {user_label}")
                success_count += 1
            except Exception as e:
                logger.error(f"  GAGAL hapus DB: {user_label} — {e}")
                db.session.rollback()
                fail_count += 1

    logger.info(
        f"Cleanup selesai. "
        f"Berhasil={success_count}, Gagal={fail_count}, Dilewati={skip_count}, "
        f"Total kandidat={len(users_to_delete)}"
    )
