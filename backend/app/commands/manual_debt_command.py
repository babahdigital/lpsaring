# backend/app/commands/manual_debt_command.py

from __future__ import annotations

import math
from datetime import date
from datetime import timedelta
from typing import Optional
from uuid import UUID

import click
import sqlalchemy as sa
from flask.cli import with_appcontext
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import Package, QuotaMutationLedger, Transaction, TransactionStatus, User, UserQuotaDebt, UserRole
from app.infrastructure.http.transactions.helpers import _get_debt_order_prefixes
from app.services import settings_service
from app.services.manual_debt_report_service import build_user_manual_debt_report_context, estimate_amount_rp_for_mb
from app.services.notification_service import generate_temp_debt_report_token
from app.services.user_management.helpers import _send_whatsapp_notification
from app.services.user_management import user_debt as debt_service
from app.utils.formatters import format_app_date_display, format_mb_to_gb, get_phone_number_variations, normalize_to_e164


UNDERPAYMENT_NOTE_PREFIX = "Koreksi kekurangan pembayaran debt online"


def _format_currency_idr(value: int | float | None) -> str:
    amount = int(float(value or 0))
    return f"Rp {amount:,}".replace(",", ".")


def _resolve_public_base_url() -> str:
    return (
        settings_service.get_setting("APP_PUBLIC_BASE_URL")
        or settings_service.get_setting("FRONTEND_URL")
        or settings_service.get_setting("APP_LINK_USER")
        or ""
    )


def _build_debt_report_url(user: User) -> str:
    base_url = _resolve_public_base_url()
    if not base_url:
        return "-"
    token = generate_temp_debt_report_token(str(user.id))
    return f"{base_url.rstrip('/')}/api/admin/users/debts/temp/{token}.pdf"


def _iter_successful_debt_transactions(
    *,
    phone: Optional[str],
    order_id: Optional[str],
    limit: int,
) -> list[Transaction]:
    debt_prefixes = _get_debt_order_prefixes()
    debt_filters = [Transaction.midtrans_order_id.like(f"{prefix}-%") for prefix in debt_prefixes]
    stmt = (
        sa.select(Transaction)
        .options(selectinload(Transaction.user))
        .where(Transaction.status == TransactionStatus.SUCCESS)
        .where(sa.or_(*debt_filters))
        .order_by(sa.func.coalesce(Transaction.payment_time, Transaction.created_at).desc())
        .limit(max(1, int(limit or 50)))
    )

    if order_id:
        stmt = stmt.where(Transaction.midtrans_order_id == str(order_id).strip())

    if phone:
        normalized = normalize_to_e164(phone)
        if not normalized:
            raise click.ClickException("Nomor telepon filter tidak valid.")
        phone_variations = get_phone_number_variations(normalized)
        stmt = stmt.join(User, User.id == Transaction.user_id).where(User.phone_number.in_(phone_variations))

    return list(db.session.scalars(stmt).all())


def _get_settlement_mutation(transaction: Transaction) -> QuotaMutationLedger | None:
    return db.session.scalar(
        sa.select(QuotaMutationLedger)
        .where(QuotaMutationLedger.source == "transactions.debt_settlement_success")
        .where(QuotaMutationLedger.idempotency_key == str(getattr(transaction, "midtrans_order_id", "") or ""))
        .order_by(QuotaMutationLedger.created_at.desc())
        .limit(1)
    )


def _matches_settlement_window(paid_at, settled_at) -> bool:
    if paid_at is None or settled_at is None:
        return False
    try:
        diff_seconds = abs((paid_at - settled_at).total_seconds())
    except Exception:
        return False
    return diff_seconds <= 35 or 3500 <= diff_seconds <= 3705


def _find_matched_paid_debts(user_id, settled_at) -> list[UserQuotaDebt]:
    debts = db.session.scalars(
        sa.select(UserQuotaDebt)
        .where(UserQuotaDebt.user_id == user_id)
        .where(UserQuotaDebt.is_paid.is_(True))
        .where(UserQuotaDebt.paid_at.is_not(None))
        .order_by(UserQuotaDebt.paid_at.desc(), UserQuotaDebt.created_at.desc())
    ).all()
    return [debt for debt in debts if _matches_settlement_window(getattr(debt, "paid_at", None), settled_at)]


def _estimate_expected_transaction_rp(matched_debts: list[UserQuotaDebt]) -> int:
    total_expected_rp = 0
    for debt in matched_debts:
        explicit_price_rp = getattr(debt, "price_rp", None)
        if explicit_price_rp is not None and int(explicit_price_rp) > 0:
            total_expected_rp += int(explicit_price_rp)
            continue
        try:
            amount_mb = int(getattr(debt, "amount_mb", 0) or 0)
        except Exception:
            amount_mb = 0
        if amount_mb > 0:
            total_expected_rp += int(estimate_amount_rp_for_mb(amount_mb) or 0)
    return int(total_expected_rp)


def _build_underpayment_note(transaction: Transaction, paid_rp: int, expected_rp: int) -> str:
    return (
        f"{UNDERPAYMENT_NOTE_PREFIX} {transaction.midtrans_order_id} | "
        f"dibayar {_format_currency_idr(paid_rp)} dari seharusnya {_format_currency_idr(expected_rp)}"
    )


def _find_existing_correction_debt(user_id, order_id: str) -> UserQuotaDebt | None:
    return db.session.scalar(
        sa.select(UserQuotaDebt)
        .where(UserQuotaDebt.user_id == user_id)
        .where(UserQuotaDebt.note.ilike(f"%{UNDERPAYMENT_NOTE_PREFIX}%"))
        .where(UserQuotaDebt.note.ilike(f"%{str(order_id).strip()}%"))
        .order_by(UserQuotaDebt.created_at.desc())
        .limit(1)
    )


def _compute_shortage_mb(shortage_rp: int, expected_rp: int, paid_manual_mb: int) -> int:
    if shortage_rp <= 0:
        return 0
    if expected_rp > 0 and paid_manual_mb > 0:
        proportional_mb = math.ceil((int(shortage_rp) * int(paid_manual_mb)) / int(expected_rp))
        return max(1, int(proportional_mb))
    return 1


def _build_underpayment_rows(
    *,
    phone: Optional[str],
    order_id: Optional[str],
    limit: int,
) -> list[dict]:
    rows: list[dict] = []
    for transaction in _iter_successful_debt_transactions(phone=phone, order_id=order_id, limit=limit):
        mutation = _get_settlement_mutation(transaction)
        if mutation is None:
            continue
        user = getattr(transaction, "user", None)
        if user is None:
            continue
        details = dict(getattr(mutation, "event_details", None) or {})
        paid_manual_mb = int(details.get("paid_manual_mb") or 0)
        if paid_manual_mb <= 0:
            continue
        settled_at = getattr(transaction, "payment_time", None) or getattr(mutation, "created_at", None) or getattr(transaction, "created_at", None)
        matched_debts = _find_matched_paid_debts(user.id, settled_at)
        expected_rp = _estimate_expected_transaction_rp(matched_debts)
        paid_rp = int(getattr(transaction, "amount", 0) or 0)
        shortage_rp = max(0, int(expected_rp) - int(paid_rp))
        correction_debt = _find_existing_correction_debt(user.id, transaction.midtrans_order_id)
        rows.append(
            {
                "transaction": transaction,
                "user": user,
                "mutation": mutation,
                "paid_rp": paid_rp,
                "expected_rp": int(expected_rp),
                "shortage_rp": int(shortage_rp),
                "paid_manual_mb": int(paid_manual_mb),
                "matched_debts": matched_debts,
                "settled_at": settled_at,
                "existing_correction_debt": correction_debt,
            }
        )
    return rows


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
@click.option("--due-date", default=None, help="Tanggal jatuh tempo (YYYY-MM-DD). Digunakan untuk reminder notifikasi.")
@click.option("--note", default=None, help="Catatan (opsional).")
@click.option("--admin-id", default=None, help="UUID admin actor (opsional; untuk created_by_id).")
@click.option("--apply/--dry-run", default=False, show_default=True, help="Apply perubahan ke DB atau hanya simulasi.")
@with_appcontext
def add_manual_debt_command(
    phone: str,
    package_id: Optional[str],
    amount_mb: int,
    debt_date: Optional[str],
    due_date: Optional[str],
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
    due_date_val = _parse_date(due_date)

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
        due_date=due_date_val,
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


@click.command("audit-debt-settlement-underpayments")
@click.option("--phone", default=None, help="Filter nomor telepon user (08... / +62...).")
@click.option("--order-id", default=None, help="Filter satu order ID transaksi debt.")
@click.option("--limit", type=int, default=50, show_default=True, help="Maksimum transaksi debt sukses yang diperiksa.")
@click.option("--due-days", type=int, default=7, show_default=True, help="Jatuh tempo debt koreksi dihitung dari tanggal settle + N hari.")
@click.option("--send-wa/--no-send-wa", default=False, show_default=True, help="Kirim WhatsApp koreksi setelah debt dibuat (hanya saat --apply).")
@click.option("--apply/--dry-run", default=False, show_default=True, help="Apply debt koreksi atau hanya audit tanpa perubahan.")
@with_appcontext
def audit_debt_settlement_underpayments_command(
    phone: Optional[str],
    order_id: Optional[str],
    limit: int,
    due_days: int,
    send_wa: bool,
    apply: bool,
) -> None:
    """Audit pembayaran debt online yang kurang dari nilai ledger, lalu opsional buat debt koreksi."""
    if send_wa and not apply:
        raise click.ClickException("Gunakan --apply jika ingin mengirim WhatsApp koreksi.")

    due_days = max(0, int(due_days or 0))
    rows = _build_underpayment_rows(phone=phone, order_id=order_id, limit=limit)
    if not rows:
        click.echo("Tidak ada transaksi debt online sukses yang cocok dengan filter.")
        return

    found_shortages = 0
    created_count = 0
    sent_wa_count = 0
    skipped_existing = 0

    for row in rows:
        transaction = row["transaction"]
        user = row["user"]
        shortage_rp = int(row["shortage_rp"] or 0)
        expected_rp = int(row["expected_rp"] or 0)
        paid_rp = int(row["paid_rp"] or 0)
        paid_manual_mb = int(row["paid_manual_mb"] or 0)
        matched_debts = row["matched_debts"]
        existing_correction_debt = row["existing_correction_debt"]

        click.echo(
            f"order={transaction.midtrans_order_id} phone={getattr(user, 'phone_number', '-') or '-'} "
            f"user={getattr(user, 'full_name', '-') or '-'} paid={_format_currency_idr(paid_rp)} "
            f"expected={_format_currency_idr(expected_rp)} shortage={_format_currency_idr(shortage_rp)} "
            f"matched_items={len(matched_debts)} existing_correction={'yes' if existing_correction_debt else 'no'}"
        )

        if shortage_rp <= 0:
            continue
        found_shortages += 1

        if existing_correction_debt is not None:
            skipped_existing += 1
            continue

        shortage_mb = _compute_shortage_mb(shortage_rp, expected_rp, paid_manual_mb)
        settled_at = row["settled_at"]
        debt_date = settled_at.date() if settled_at is not None else date.today()
        due_date_value = debt_date + timedelta(days=due_days)
        note = _build_underpayment_note(transaction, paid_rp, expected_rp)

        if not apply:
            click.echo(
                f"  DRY-RUN correction amount_mb={shortage_mb} price_rp={shortage_rp} due_date={due_date_value.isoformat()}"
            )
            continue

        ok, message, entry = debt_service.add_manual_debt(
            user=user,
            admin_actor=None,
            amount_mb=shortage_mb,
            debt_date=debt_date,
            due_date=due_date_value,
            note=note,
            price_rp=shortage_rp,
        )
        if not ok or entry is None:
            db.session.rollback()
            raise click.ClickException(f"Gagal membuat debt koreksi untuk {transaction.midtrans_order_id}: {message}")

        created_count += 1
        click.echo(
            click.style(
                f"  APPLY entry_id={entry.id} amount_mb={shortage_mb} price_rp={shortage_rp}",
                fg="green",
            )
        )

        if send_wa and getattr(user, "phone_number", None):
            report_context = build_user_manual_debt_report_context(user)
            debt_pdf_url = _build_debt_report_url(user)
            sent = _send_whatsapp_notification(
                user.phone_number,
                "user_debt_underpayment_correction",
                {
                    "full_name": user.full_name,
                    "order_id": transaction.midtrans_order_id,
                    "paid_amount_display": _format_currency_idr(paid_rp),
                    "expected_amount_display": _format_currency_idr(expected_rp),
                    "shortage_amount_display": _format_currency_idr(shortage_rp),
                    "shortage_debt_gb": format_mb_to_gb(shortage_mb),
                    "due_date": format_app_date_display(due_date_value, fallback=due_date_value.isoformat()),
                    "debt_pdf_url": debt_pdf_url,
                    "total_manual_debt_gb": format_mb_to_gb(report_context.get("debt_manual_mb") or 0),
                    "total_manual_debt_amount_display": _format_currency_idr(report_context.get("debt_manual_estimated_rp") or 0),
                },
            )
            if sent:
                sent_wa_count += 1

    if apply:
        db.session.commit()
        click.echo(
            click.style(
                f"SUKSES: shortage_found={found_shortages} created={created_count} skipped_existing={skipped_existing} wa_sent={sent_wa_count}",
                fg="green",
            )
        )
    else:
        db.session.rollback()
        click.echo(
            click.style(
                f"DRY-RUN selesai: shortage_found={found_shortages} skipped_existing={skipped_existing}",
                fg="yellow",
            )
        )
