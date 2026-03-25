from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import Package, User, UserQuotaDebt
from app.infrastructure.http.schemas.user_schemas import UserQuotaDebtItemResponseSchema
from app.services import settings_service
from app.utils.formatters import (
    format_app_date_display,
    format_app_datetime_display,
    format_mb_to_gb,
    format_to_local_phone,
)
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package


def format_currency_idr(value: int | float | None) -> str:
    amount = int(float(value or 0))
    return f"Rp {amount:,}".replace(",", ".")


def _pick_ref_pkg_for_debt_mb(value_mb: float) -> Package | None:
    try:
        mb = float(value_mb or 0)
    except Exception:
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


def estimate_debt_rp_for_mb(value_mb: float):
    pkg = _pick_ref_pkg_for_debt_mb(value_mb)
    return estimate_debt_rp_from_cheapest_package(
        debt_mb=float(value_mb or 0),
        cheapest_package_price_rp=int(pkg.price) if pkg and pkg.price is not None else None,
        cheapest_package_quota_gb=float(pkg.data_quota_gb) if pkg and pkg.data_quota_gb is not None else None,
        cheapest_package_name=str(pkg.name) if pkg and pkg.name else None,
    )


def estimate_amount_rp_for_mb(value_mb: float) -> int:
    estimate = estimate_debt_rp_for_mb(value_mb)
    return int(estimate.estimated_rp_rounded or 0)


def _estimate_remaining_item_rp(item: UserQuotaDebt, remaining_mb: int, amount_mb: int) -> int:
    if remaining_mb <= 0:
        return 0

    explicit_price_rp = getattr(item, "price_rp", None)
    if explicit_price_rp is not None and amount_mb > 0:
        try:
            prorated = round(int(explicit_price_rp) * (remaining_mb / float(amount_mb)))
            return max(0, int(prorated))
        except Exception:
            pass

    return estimate_amount_rp_for_mb(remaining_mb)


def _sum_open_item_totals(items: list[dict[str, Any]]) -> tuple[int, int]:
    open_items = [item for item in items if not bool(item.get("is_paid"))]
    total_mb = sum(int(item.get("remaining_mb") or 0) for item in open_items)
    total_rp = sum(int(item.get("remaining_rp") or 0) for item in open_items)
    return total_mb, total_rp


def build_user_manual_debt_report_context(user: User) -> dict[str, Any]:
    debts = db.session.scalars(
        select(UserQuotaDebt)
        .where(UserQuotaDebt.user_id == user.id)
        .order_by(
            UserQuotaDebt.debt_date.desc().nulls_last(),
            UserQuotaDebt.created_at.desc(),
        )
    ).all()

    items: list[dict[str, Any]] = []
    for debt in debts:
        amount_mb = int(getattr(debt, "amount_mb", 0) or 0)
        paid_mb = int(getattr(debt, "paid_mb", 0) or 0)
        remaining_mb = max(0, amount_mb - paid_mb)
        is_paid = bool(getattr(debt, "is_paid", False)) or remaining_mb <= 0
        note_text = str(getattr(debt, "note", "") or "").lower()
        is_unlimited_debt = amount_mb <= 1 and "unlimited" in note_text
        payload = UserQuotaDebtItemResponseSchema.from_orm(debt).model_dump()
        payload["is_unlimited_debt"] = is_unlimited_debt
        payload["debt_date_display"] = format_app_date_display(payload.get("debt_date"), fallback="-")
        payload["due_date_display"] = format_app_date_display(getattr(debt, "due_date", None), fallback="-")
        payload["created_at_display"] = format_app_datetime_display(payload.get("created_at"), fallback="-")
        payload["updated_at_display"] = format_app_datetime_display(payload.get("updated_at"), fallback="-")
        payload["paid_at_display"] = format_app_datetime_display(payload.get("paid_at"), fallback="-")
        payload["remaining_mb"] = remaining_mb
        payload["remaining_gb"] = format_mb_to_gb(remaining_mb)
        payload["remaining_rp"] = _estimate_remaining_item_rp(debt, remaining_mb, amount_mb)
        payload["remaining_amount_display"] = format_currency_idr(payload["remaining_rp"])
        payload["is_paid"] = is_paid
        payload["paid_mb"] = paid_mb
        payload["amount_mb"] = amount_mb
        items.append(payload)

    open_items = [item for item in items if not bool(item.get("is_paid"))]
    open_manual_mb, open_manual_rp = _sum_open_item_totals(items)

    debt_auto_mb = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
    cached_manual_mb = float(getattr(user, "quota_debt_manual_mb", 0) or 0)
    debt_manual_mb = float(open_manual_mb if open_items else cached_manual_mb)
    debt_total_mb = float(debt_auto_mb + debt_manual_mb)

    est_auto = estimate_debt_rp_for_mb(debt_auto_mb)
    est_manual = estimate_debt_rp_for_mb(debt_manual_mb)

    debt_manual_estimated_rp = int(open_manual_rp) if open_items else int(est_manual.estimated_rp_rounded or 0)
    debt_total_estimated_rp = int(est_auto.estimated_rp_rounded or 0) + debt_manual_estimated_rp

    return {
        "user": user,
        "user_phone_display": format_to_local_phone(getattr(user, "phone_number", "") or "")
        or (getattr(user, "phone_number", "") or ""),
        "generated_at": format_app_datetime_display(datetime.now(dt_timezone.utc), include_seconds=False),
        "items": items,
        "open_items": open_items,
        "debt_auto_mb": debt_auto_mb,
        "debt_manual_mb": debt_manual_mb,
        "debt_total_mb": debt_total_mb,
        "debt_auto_estimated_rp": est_auto.estimated_rp_rounded or 0,
        "debt_manual_estimated_rp": debt_manual_estimated_rp,
        "debt_total_estimated_rp": debt_total_estimated_rp,
        "estimate_base_package_name": est_manual.package_name or est_auto.package_name,
    }


def build_user_debt_detail_lines(report_context: dict[str, Any], *, max_items: int = 8) -> list[str]:
    open_items = list(report_context.get("open_items") or [])
    detail_lines: list[str] = []
    for index, item in enumerate(open_items[:max_items], start=1):
        due_text = item.get("due_date_display") or item.get("debt_date_display") or "-"
        is_unl = bool(item.get("is_unlimited_debt"))
        amount_text = "Unlimited" if is_unl else (item.get("remaining_gb") or format_mb_to_gb(item.get("remaining_mb") or item.get("amount_mb") or 0))
        price_text = item.get("remaining_amount_display") or format_currency_idr(item.get("remaining_rp") or 0)
        package_text = str(item.get("note") or "Tunggakan manual").strip()
        detail_lines.append(f"{index}. {due_text} — {amount_text} | {price_text} | {package_text}")

    if len(open_items) > max_items:
        detail_lines.append(f"... dan {len(open_items) - max_items} item lainnya. Lihat PDF terlampir untuk rincian lengkap.")
    if not detail_lines:
        detail_lines.append("Tidak ada item tunggakan manual yang masih terbuka.")
    return detail_lines


def build_user_debt_whatsapp_context(user: User, report_context: dict[str, Any], pdf_url: str) -> dict[str, Any]:
    detail_lines = build_user_debt_detail_lines(report_context)
    open_items = list(report_context.get("open_items") or [])
    has_unlimited = any(bool(item.get("is_unlimited_debt")) for item in open_items)
    return {
        "full_name": user.full_name,
        "total_manual_debt_gb": "Unlimited" if has_unlimited else format_mb_to_gb(report_context.get("debt_manual_mb") or 0),
        "total_manual_debt_amount_display": format_currency_idr(report_context.get("debt_manual_estimated_rp") or 0),
        "open_items": len(open_items),
        "debt_detail_lines": "\n".join(detail_lines),
        "debt_pdf_url": pdf_url,
        "debt_invoice_url": pdf_url,
    }


def build_due_debt_reminder_context(user: User, report_context: dict[str, Any], debt: UserQuotaDebt, pdf_url: str) -> dict[str, Any]:
    item_payload = next((item for item in report_context.get("items", []) if str(item.get("id")) == str(debt.id)), None)

    amount_mb = int(getattr(debt, "amount_mb", 0) or 0)
    paid_mb = int(getattr(debt, "paid_mb", 0) or 0)
    remaining_mb = max(0, amount_mb - paid_mb)
    debt_note = str(getattr(debt, "note", "") or "").lower()
    is_unlimited_debt = amount_mb <= 1 and "unlimited" in debt_note
    debt_amount_display = (
        item_payload.get("remaining_amount_display")
        if item_payload
        else format_currency_idr(_estimate_remaining_item_rp(debt, remaining_mb, amount_mb))
    )
    due_date_display = (
        item_payload.get("due_date_display")
        if item_payload
        else format_app_date_display(getattr(debt, "due_date", None), fallback="-")
    )
    detail_lines = build_user_debt_detail_lines(report_context)
    open_items = list(report_context.get("open_items") or [])

    return {
        "full_name": user.full_name,
        "debt_gb": "Unlimited" if is_unlimited_debt else format_mb_to_gb(remaining_mb),
        "debt_amount_display": debt_amount_display,
        "due_date": due_date_display,
        "total_manual_debt_gb": format_mb_to_gb(report_context.get("debt_manual_mb") or 0),
        "total_manual_debt_amount_display": format_currency_idr(report_context.get("debt_manual_estimated_rp") or 0),
        "open_items": len(open_items),
        "debt_detail_lines": "\n".join(detail_lines),
        "debt_pdf_url": pdf_url,
        "debt_invoice_url": pdf_url,
    }


def resolve_public_base_url() -> str:
    return (
        settings_service.get_setting("APP_PUBLIC_BASE_URL")
        or settings_service.get_setting("FRONTEND_URL")
        or settings_service.get_setting("APP_LINK_USER")
        or ""
    )


def build_user_manual_debt_pdf_filename(user: User) -> str:
    safe_phone = (getattr(user, "phone_number", "") or str(user.id)).replace("+", "")
    return f"debt-{safe_phone}-ledger.pdf"