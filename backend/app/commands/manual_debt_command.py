# backend/app/commands/manual_debt_command.py

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

import click
import sqlalchemy as sa
from flask.cli import with_appcontext

from app.extensions import db
from app.infrastructure.db.models import Package, User, UserRole
from app.services.user_management import user_debt as debt_service
from app.utils.formatters import get_phone_number_variations, normalize_to_e164


def _parse_uuid(value: Optional[str], *, label: str) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except Exception as exc:
        raise click.ClickException(f"{label} tidak valid (harus UUID): {value}") from exc


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise click.ClickException(f"debt-date tidak valid (format YYYY-MM-DD): {value}") from exc


@click.command("add-manual-debt")
@click.option("--phone", required=True, help="Nomor telepon user (08... / +62...).")
@click.option("--package-id", default=None, help="UUID paket untuk menentukan besaran debt (ambil data_quota_gb).")
@click.option("--amount-mb", type=int, default=0, help="Besaran debt manual (MB). Contoh: 10240=10GB.")
@click.option("--debt-date", default=None, help="Tanggal debt (YYYY-MM-DD). Default: kosong.")
@click.option("--note", default=None, help="Catatan (opsional).")
@click.option("--admin-id", default=None, help="UUID admin actor (opsional; untuk created_by_id).")
@click.option("--apply/--dry-run", default=False, show_default=True, help="Apply perubahan ke DB atau hanya simulasi.")
@with_appcontext
def add_manual_debt_command(
    phone: str,
    package_id: Optional[str],
    amount_mb: int,
    debt_date: Optional[str],
    note: Optional[str],
    admin_id: Optional[str],
    apply: bool,
) -> None:
    """Tambah 1 item manual debt untuk user.

    Ini hanya perubahan data (ledger + cached manual_debt_mb), bukan perubahan schema.
    """

    normalized = normalize_to_e164(phone)
    if not normalized:
        raise click.ClickException("Nomor telepon tidak valid.")

    user = db.session.scalar(sa.select(User).where(User.phone_number.in_(get_phone_number_variations(normalized))))
    if not user:
        raise click.ClickException(f"User tidak ditemukan untuk nomor: {phone}")

    if getattr(user, "role", None) != UserRole.USER:
        raise click.ClickException("Manual debt hanya berlaku untuk role USER (termasuk tamping).")
    if bool(getattr(user, "is_unlimited_user", False)):
        raise click.ClickException("Manual debt tidak berlaku untuk pengguna unlimited.")

    pkg_uuid = _parse_uuid(package_id, label="package-id")
    admin_uuid = _parse_uuid(admin_id, label="admin-id")
    debt_date_val = _parse_date(debt_date)

    if pkg_uuid and amount_mb and amount_mb > 0:
        raise click.ClickException("Gunakan salah satu: --package-id atau --amount-mb (jangan keduanya).")

    resolved_amount_mb = 0
    resolved_note = note.strip() if isinstance(note, str) and note.strip() else None

    if pkg_uuid:
        pkg = db.session.get(Package, pkg_uuid)
        if not pkg:
            raise click.ClickException("Paket tidak ditemukan.")

        try:
            pkg_quota_gb = float(getattr(pkg, "data_quota_gb", 0) or 0.0)
        except (TypeError, ValueError):
            pkg_quota_gb = 0.0
        if pkg_quota_gb <= 0:
            raise click.ClickException("Paket debt harus memiliki kuota (GB) > 0.")

        resolved_amount_mb = int(round(pkg_quota_gb * 1024))
        pkg_note = (
            f"Paket: {getattr(pkg, 'name', '') or ''} ({pkg_quota_gb:g} GB, Rp {int(getattr(pkg, 'price', 0) or 0):,})"
        )
        resolved_note = pkg_note if not resolved_note else f"{pkg_note} | {resolved_note}"
    else:
        try:
            resolved_amount_mb = int(amount_mb or 0)
        except (TypeError, ValueError):
            resolved_amount_mb = 0

    if resolved_amount_mb <= 0:
        raise click.ClickException("Jumlah debt (MB) harus > 0.")

    admin_actor = db.session.get(User, admin_uuid) if admin_uuid else None

    manual_before = int(getattr(user, "manual_debt_mb", 0) or 0)
    ok, msg, entry = debt_service.add_manual_debt(
        user=user,
        admin_actor=admin_actor,
        amount_mb=resolved_amount_mb,
        debt_date=debt_date_val,
        note=resolved_note,
    )
    if not ok or not entry:
        raise click.ClickException(msg)

    manual_after = int(getattr(user, "manual_debt_mb", 0) or 0)
    click.echo(
        f"user={user.id} name={getattr(user, 'full_name', '')} "
        f"amount_mb={resolved_amount_mb} manual_before_mb={manual_before} manual_after_mb={manual_after} "
        f"entry_id={getattr(entry, 'id', None)} apply={apply}"
    )

    if apply:
        db.session.commit()
        click.echo(click.style("SUKSES: manual debt ditambahkan.", fg="green"))
    else:
        db.session.rollback()
        click.echo(click.style("DRY-RUN: tidak ada perubahan yang disimpan.", fg="yellow"))
