# backend/app/commands/cleanup_inactive_command.py
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select
from datetime import datetime, timedelta
import logging

from app.extensions import db
from app.infrastructure.db.models import User, UserRole
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, delete_hotspot_user
from app.utils.formatters import format_app_date

logger = logging.getLogger(__name__)

# Role yang TIDAK boleh dihapus oleh cleanup ini (hanya USER biasa yang harusnya cleanup)
_PROTECTED_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.KOMANDAN}


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
    Hapus pengguna USER yang sudah sangat lama tidak aktif berdasarkan quota_expiry_date.

    Threshold diambil dari config INACTIVE_DELETE_DAYS (default 90 hari).
    ADMIN, SUPER_ADMIN, dan KOMANDAN tidak akan pernah dihapus oleh perintah ini.

    Gunakan --dry-run terlebih dahulu untuk melihat siapa saja yang akan dihapus.
    """
    delete_days = int(current_app.config.get("INACTIVE_DELETE_DAYS", 90))
    cutoff_date = datetime.now() - timedelta(days=delete_days)

    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(
        f"{prefix}Memulai cleanup user tidak aktif. "
        f"Threshold: {delete_days} hari (sebelum {format_app_date(cutoff_date)})"
    )

    # Query: hanya USER biasa dengan quota_expiry_date sebelum cutoff dan NOT NULL
    users_to_delete = db.session.scalars(
        select(User).where(
            User.quota_expiry_date.isnot(None),
            User.quota_expiry_date < cutoff_date,
            User.role.notin_(_PROTECTED_ROLES),
        )
    ).all()

    if not users_to_delete:
        logger.info(f"{prefix}Tidak ada user tidak aktif yang memenuhi kriteria penghapusan.")
        return

    logger.info(f"{prefix}Ditemukan {len(users_to_delete)} user kandidat penghapusan.")

    if dry_run:
        logger.info("[DRY RUN] Daftar user yang AKAN dihapus (belum benar-benar dihapus):")
        for user in users_to_delete:
            logger.info(
                f"  [DRY RUN] {user.full_name} | {user.phone_number} | "
                f"role={user.role.value} | quota_expiry={user.quota_expiry_date}"
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

        for user in users_to_delete:
            user_label = f"{user.full_name} ({user.phone_number})"
            logger.info(f"Memproses: {user_label} | kadaluarsa: {user.quota_expiry_date}")

            # Proteksi ganda: skip jika role terlindungi (seharusnya tidak lolos query, tapi defensive)
            if user.role in _PROTECTED_ROLES:
                logger.warning(f"  SKIP: {user_label} punya role terlindungi ({user.role.value}), tidak dihapus.")
                skip_count += 1
                continue

            # 1. Hapus dari MikroTik dulu
            if getattr(user, "mikrotik_user_exists", False):
                mt_success, mt_msg = delete_hotspot_user(api, user.phone_number)
                if not mt_success:
                    logger.error(f"  GAGAL hapus MikroTik: {user_label} — {mt_msg}")
                    fail_count += 1
                    continue  # jangan hapus DB jika MikroTik gagal
                logger.debug(f"  MikroTik OK: {user_label}")
            else:
                logger.debug(f"  MikroTik skip (user belum di MikroTik): {user_label}")

            # 2. Hapus dari DB + commit per-user (bukan batch)
            try:
                db.session.delete(user)
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
