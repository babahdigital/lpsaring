from __future__ import annotations

import os
import uuid
from typing import Any

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import Package, QuotaMutationLedger, Transaction, User, UserQuotaDebt
from app.utils.formatters import format_app_date_display, format_app_datetime_display, format_mb_to_gb, format_to_local_phone
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package


ONLINE_DEBT_SETTLEMENT_SOURCE = "transactions.debt_settlement_success"
ADMIN_SETTLE_SINGLE_SOURCE = "debt.settle_manual_item:admin_settle_item"
ADMIN_SETTLE_ALL_SOURCE = "debt.clear_all:admin_settle_all"

DEFAULT_RECEIPT_BUSINESS_NAME = "LPSaringNET"
DEFAULT_RECEIPT_BUSINESS_ADDRESS = (
    "Saring Sei Bubu, Kec. Kusan Hilir, Kabupaten Tanah Bumbu, Kalimantan Selatan 72273, Indonesia"
)
DEFAULT_RECEIPT_BUSINESS_PHONE = "+6281346607751"


def format_currency_idr(value: int | float | None) -> str:
    amount = int(float(value or 0))
    return f"Rp {amount:,}".replace(",", ".")


def build_receipt_business_identity_context() -> dict[str, str]:
    business_name = str(
        current_app.config.get("BUSINESS_NAME")
        or os.environ.get("BUSINESS_NAME")
        or DEFAULT_RECEIPT_BUSINESS_NAME
    ).strip() or DEFAULT_RECEIPT_BUSINESS_NAME
    business_address = str(
        current_app.config.get("BUSINESS_ADDRESS")
        or os.environ.get("BUSINESS_ADDRESS")
        or DEFAULT_RECEIPT_BUSINESS_ADDRESS
    ).strip() or DEFAULT_RECEIPT_BUSINESS_ADDRESS
    raw_business_phone = str(
        current_app.config.get("BUSINESS_PHONE")
        or os.environ.get("BUSINESS_PHONE")
        or current_app.config.get("NUXT_PUBLIC_ADMIN_WHATSAPP")
        or os.environ.get("NUXT_PUBLIC_ADMIN_WHATSAPP")
        or DEFAULT_RECEIPT_BUSINESS_PHONE
    ).strip() or DEFAULT_RECEIPT_BUSINESS_PHONE
    business_phone = format_to_local_phone(raw_business_phone) or raw_business_phone or DEFAULT_RECEIPT_BUSINESS_PHONE
    return {
        "business_name": business_name,
        "business_address": business_address,
        "business_phone": business_phone,
    }


def is_debt_settlement_order_id(order_id: str | None) -> bool:
    raw = str(order_id or "").strip().upper()
    return bool(raw and raw.startswith("DEBT-"))


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _pick_reference_package(value_mb: float) -> Package | None:
    try:
        mb = float(value_mb or 0)
    except (TypeError, ValueError):
        mb = 0.0
    if mb <= 0:
        return None
    debt_gb = mb / 1024.0
    base_q = (
        select(Package)
        .where(Package.is_active.is_(True))
        .where(Package.data_quota_gb.is_not(None))
        .where(Package.data_quota_gb > 0)
        .where(Package.price.is_not(None))
        .where(Package.price > 0)
    )
    ref = db.session.execute(
        base_q.where(Package.data_quota_gb >= debt_gb)
        .order_by(Package.data_quota_gb.asc(), Package.price.asc())
        .limit(1)
    ).scalar_one_or_none()
    if ref is None:
        ref = db.session.execute(base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).limit(1)).scalar_one_or_none()
    return ref


def estimate_amount_rp_for_mb(value_mb: float) -> int:
    pkg = _pick_reference_package(value_mb)
    if pkg is None:
        return 0
    estimate = estimate_debt_rp_from_cheapest_package(
        debt_mb=float(value_mb or 0),
        cheapest_package_price_rp=int(pkg.price) if pkg.price is not None else None,
        cheapest_package_quota_gb=float(pkg.data_quota_gb) if pkg.data_quota_gb is not None else None,
        cheapest_package_name=str(pkg.name) if pkg.name else None,
    )
    return int(estimate.estimated_rp_rounded or 0)


def _humanize_payment_method(payment_method: str | None) -> str:
    raw = str(payment_method or "").strip().lower()
    if not raw:
        return "Manual admin"
    if raw == "qris":
        return "QRIS"
    if raw == "gopay":
        return "GoPay"
    if raw == "shopeepay":
        return "ShopeePay"
    if raw.endswith("_va"):
        return f"VA {raw[:-3].upper()}"
    return raw.replace("_", " ").title()


def get_debt_settlement_mutation_for_transaction(transaction: Transaction) -> QuotaMutationLedger | None:
    if transaction is None or getattr(transaction, "user_id", None) is None:
        return None
    return db.session.execute(
        select(QuotaMutationLedger)
        .where(QuotaMutationLedger.user_id == transaction.user_id)
        .where(QuotaMutationLedger.source == ONLINE_DEBT_SETTLEMENT_SOURCE)
        .where(QuotaMutationLedger.idempotency_key == str(getattr(transaction, "midtrans_order_id", "") or ""))
        .order_by(QuotaMutationLedger.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_latest_admin_debt_settlement_mutation(user_id: uuid.UUID, source: str) -> QuotaMutationLedger | None:
    return db.session.execute(
        select(QuotaMutationLedger)
        .where(QuotaMutationLedger.user_id == user_id)
        .where(QuotaMutationLedger.source == source)
        .order_by(QuotaMutationLedger.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _get_manual_debt_item(user_id: uuid.UUID, debt_item_id: str | None) -> UserQuotaDebt | None:
    if not debt_item_id:
        return None
    try:
        debt_uuid = uuid.UUID(str(debt_item_id))
    except (TypeError, ValueError):
        return None
    item = db.session.get(UserQuotaDebt, debt_uuid)
    if item is None or getattr(item, "user_id", None) != user_id:
        return None
    return item


def build_debt_settlement_receipt_context(
    *,
    user: User,
    settlement_entry: QuotaMutationLedger,
    transaction: Transaction | None = None,
) -> dict[str, Any]:
    details = dict(getattr(settlement_entry, "event_details", None) or {})
    paid_auto_mb = _safe_int(details.get("paid_auto_mb"))
    paid_manual_mb = _safe_int(details.get("paid_manual_mb"))
    paid_total_mb = paid_auto_mb + paid_manual_mb
    debt_item = _get_manual_debt_item(user.id, details.get("debt_item_id"))

    # Detect unlimited manual debt item (sentinel amount_mb=1, note contains "unlimited")
    is_unlimited_manual = False
    if debt_item is not None:
        item_amount = int(getattr(debt_item, "amount_mb", 0) or 0)
        item_note = str(getattr(debt_item, "note", "") or "").lower()
        is_unlimited_manual = item_amount <= 1 and "unlimited" in item_note

    paid_manual_amount_rp = 0
    if debt_item is not None and getattr(debt_item, "price_rp", None):
        paid_manual_amount_rp = _safe_int(getattr(debt_item, "price_rp", 0))
    elif debt_item is None and paid_manual_mb > 0:
        # settle-all: no single debt_item_id — sum price_rp from all recently settled items
        settled_items = db.session.scalars(
            select(UserQuotaDebt)
            .where(UserQuotaDebt.user_id == user.id, UserQuotaDebt.is_paid.is_(True))
            .where(UserQuotaDebt.paid_at.is_not(None))
            .order_by(UserQuotaDebt.paid_at.desc())
            .limit(50)
        ).all()
        # Filter to items settled around the same time as the settlement entry
        entry_created = getattr(settlement_entry, "created_at", None)
        sum_price_rp = 0
        has_unlimited_item = False
        for si in settled_items:
            si_paid_at = getattr(si, "paid_at", None)
            if entry_created and si_paid_at:
                diff = abs((entry_created - si_paid_at).total_seconds())
                if diff > 10:
                    continue
            si_price = getattr(si, "price_rp", None)
            if si_price and si_price > 0:
                sum_price_rp += int(si_price)
            si_note = str(getattr(si, "note", "") or "").lower()
            si_amount = int(getattr(si, "amount_mb", 0) or 0)
            if si_amount <= 1 and "unlimited" in si_note:
                has_unlimited_item = True
        if sum_price_rp > 0:
            paid_manual_amount_rp = sum_price_rp
        else:
            paid_manual_amount_rp = estimate_amount_rp_for_mb(paid_manual_mb)
        if has_unlimited_item:
            is_unlimited_manual = True
    elif paid_manual_mb > 0:
        paid_manual_amount_rp = estimate_amount_rp_for_mb(paid_manual_mb)

    paid_auto_amount_rp = estimate_amount_rp_for_mb(paid_auto_mb)
    total_amount_rp = _safe_int(getattr(transaction, "amount", 0)) if transaction is not None else paid_auto_amount_rp + paid_manual_amount_rp

    settlement_lines: list[str] = []
    if paid_auto_mb > 0:
        settlement_lines.append(
            f"Auto debt dibayar {format_mb_to_gb(paid_auto_mb)} ({format_currency_idr(paid_auto_amount_rp)})"
        )
    if paid_manual_mb > 0:
        manual_qty_text = "Unlimited" if is_unlimited_manual else format_mb_to_gb(paid_manual_mb)
        manual_line = f"Manual debt dibayar {manual_qty_text} ({format_currency_idr(paid_manual_amount_rp)})"
        if debt_item is not None:
            due_text = format_app_date_display(getattr(debt_item, "due_date", None), fallback="-")
            debt_date_text = format_app_date_display(getattr(debt_item, "debt_date", None), fallback="-")
            note_text = str(getattr(debt_item, "note", "") or "").strip()
            manual_line = f"{manual_line} | debt {debt_date_text} | jatuh tempo {due_text}"
            if note_text:
                manual_line = f"{manual_line} | {note_text}"
        settlement_lines.append(manual_line)
    if not settlement_lines:
        settlement_lines.append("Detail nominal pelunasan tidak tersedia pada event ini.")

    payment_at = getattr(transaction, "payment_time", None) if transaction is not None else getattr(settlement_entry, "created_at", None)
    receipt_number = str(getattr(transaction, "midtrans_order_id", "") or "").strip() or f"QML-{str(settlement_entry.id)[:8].upper()}"
    channel_label = "Pembayaran online via Midtrans" if transaction is not None else "Pelunasan manual oleh Admin"
    amount_label = "Nilai pembayaran" if transaction is not None else "Nilai referensi pelunasan"

    return {
        "receipt_title": "Invoice Pelunasan Tunggakan" if transaction is not None else "Bukti Pelunasan Tunggakan",
        "receipt_number": receipt_number,
        "user": user,
        "user_phone_display": format_to_local_phone(getattr(user, "phone_number", "") or "") or (getattr(user, "phone_number", "") or "-"),
        "payment_channel_label": channel_label,
        "payment_method_label": _humanize_payment_method(getattr(transaction, "payment_method", None) if transaction is not None else None),
        "payment_at_display": format_app_datetime_display(payment_at, fallback="-"),
        "created_at_display": format_app_datetime_display(getattr(settlement_entry, "created_at", None), fallback="-"),
        "amount_label": amount_label,
        "total_amount_display": format_currency_idr(total_amount_rp),
        "paid_total_gb": "Unlimited" if is_unlimited_manual and paid_auto_mb <= 0 else format_mb_to_gb(paid_total_mb),
        "paid_auto_gb": format_mb_to_gb(paid_auto_mb),
        "paid_manual_gb": "Unlimited" if is_unlimited_manual else format_mb_to_gb(paid_manual_mb),
        "paid_auto_amount_display": format_currency_idr(paid_auto_amount_rp),
        "paid_manual_amount_display": format_currency_idr(paid_manual_amount_rp),
        "paid_total_amount_display": format_currency_idr(total_amount_rp),
        "paid_auto_mb": paid_auto_mb,
        "paid_manual_mb": paid_manual_mb,
        "paid_total_mb": paid_total_mb,
        "was_unblocked": bool(details.get("unblocked") is True),
        "order_id": str(details.get("order_id") or getattr(transaction, "midtrans_order_id", "") or "").strip() or None,
        "transaction": transaction,
        "settlement_entry": settlement_entry,
        "settlement_lines": settlement_lines,
        "manual_debt_item": debt_item,
        "actor_name": getattr(getattr(settlement_entry, "actor", None), "full_name", None) or "System",
        "reference_note": "Nilai manual/admin menggunakan referensi perhitungan debt saat harga item eksplisit tidak tersedia."
        if transaction is None
        else "Invoice ini merepresentasikan pelunasan tunggakan yang berhasil diproses melalui pembayaran online.",
    }