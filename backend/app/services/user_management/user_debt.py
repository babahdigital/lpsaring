from __future__ import annotations

import math
from datetime import date, datetime, timezone as dt_timezone
from typing import Optional, Tuple

import sqlalchemy as sa

from app.extensions import db
from app.infrastructure.db.models import User, UserQuotaDebt
from app.utils.quota_debt import compute_debt_mb


def _ceil_mb(value_mb: float) -> int:
    try:
        value = float(value_mb or 0.0)
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return 0
    return int(math.ceil(value))


def get_auto_debt_mb(user: User) -> float:
    purchased_mb = float(getattr(user, "total_quota_purchased_mb", 0) or 0.0)
    used_mb = float(getattr(user, "total_quota_used_mb", 0) or 0.0)
    return float(compute_debt_mb(purchased_mb, used_mb))


def settle_auto_debt_to_zero(user: User) -> int:
    """Settle automatic debt by increasing purchased MB until used <= purchased.

    Returns amount of MB added to purchased (>=0).
    """
    debt_mb = get_auto_debt_mb(user)
    pay_mb = _ceil_mb(debt_mb)
    if pay_mb <= 0:
        return 0
    user.total_quota_purchased_mb = int(user.total_quota_purchased_mb or 0) + int(pay_mb)
    return int(pay_mb)


def add_manual_debt(
    *,
    user: User,
    admin_actor: Optional[User],
    amount_mb: int,
    debt_date: Optional[date] = None,
    note: Optional[str] = None,
) -> Tuple[bool, str, Optional[UserQuotaDebt]]:
    try:
        amount_int = int(amount_mb)
    except (TypeError, ValueError):
        return False, "Jumlah debt (MB) tidak valid.", None
    if amount_int <= 0:
        return False, "Jumlah debt (MB) harus > 0.", None

    entry = UserQuotaDebt()
    entry.user_id = user.id
    entry.created_by_id = getattr(admin_actor, "id", None)
    entry.debt_date = debt_date
    entry.amount_mb = amount_int
    entry.paid_mb = 0
    entry.is_paid = False
    entry.note = (note.strip() if isinstance(note, str) and note.strip() else None)
    db.session.add(entry)

    user.manual_debt_mb = int(getattr(user, "manual_debt_mb", 0) or 0) + amount_int
    user.manual_debt_updated_at = datetime.now(dt_timezone.utc)
    return True, "Debt berhasil ditambahkan.", entry


def apply_manual_debt_payment(
    *,
    user: User,
    admin_actor: Optional[User],
    pay_mb: int,
    source: str,
) -> int:
    """Apply payment (MB) to open manual debt entries, oldest-first.

    Returns actual MB paid (0..pay_mb).
    """
    try:
        remaining_payment = int(pay_mb)
    except (TypeError, ValueError):
        return 0
    if remaining_payment <= 0:
        return 0

    # Fast guard: if cached manual debt is 0, skip queries.
    cached = int(getattr(user, "manual_debt_mb", 0) or 0)
    if cached <= 0:
        return 0

    query = (
        sa.select(UserQuotaDebt)
        .where(UserQuotaDebt.user_id == user.id, UserQuotaDebt.is_paid.is_(False))
        .order_by(UserQuotaDebt.debt_date.asc().nulls_last(), UserQuotaDebt.created_at.asc())
    )

    paid_total = 0
    now = datetime.now(dt_timezone.utc)
    for debt in db.session.scalars(query).all():
        if remaining_payment <= 0:
            break

        try:
            amount = int(debt.amount_mb or 0)
            already_paid = int(debt.paid_mb or 0)
        except (TypeError, ValueError):
            continue

        remaining = max(0, amount - already_paid)
        if remaining <= 0:
            debt.is_paid = True
            continue

        pay_now = min(remaining, remaining_payment)
        if pay_now <= 0:
            continue

        debt.paid_mb = already_paid + pay_now
        debt.last_paid_by_id = getattr(admin_actor, "id", None)
        debt.last_paid_source = (str(source)[:50] if source else None)
        if debt.paid_mb >= amount:
            debt.is_paid = True
            debt.paid_at = now

        paid_total += pay_now
        remaining_payment -= pay_now

    if paid_total > 0:
        user.manual_debt_mb = max(0, cached - paid_total)
        user.manual_debt_updated_at = now

    return int(paid_total)


def clear_all_debts_to_zero(
    *,
    user: User,
    admin_actor: Optional[User],
    source: str,
) -> Tuple[int, int]:
    """Clear (auto + manual) debt to 0.

    Returns (paid_auto_mb, paid_manual_mb).
    """
    paid_auto_mb = settle_auto_debt_to_zero(user)
    manual_balance = int(getattr(user, "manual_debt_mb", 0) or 0)
    paid_manual_mb = apply_manual_debt_payment(
        user=user,
        admin_actor=admin_actor,
        pay_mb=manual_balance,
        source=source,
    )
    return int(paid_auto_mb), int(paid_manual_mb)


def consume_injected_mb_for_debt(
    *,
    user: User,
    admin_actor: Optional[User],
    injected_mb: int,
    source: str,
) -> Tuple[int, int, int]:
    """Use injected MB to pay debts first.

    Allocation order: auto-debt first (settled by increasing purchased), then manual debt.
    Returns (paid_auto_mb, paid_manual_mb, remaining_injected_mb).
    """
    try:
        injected = int(injected_mb)
    except (TypeError, ValueError):
        return 0, 0, 0
    if injected <= 0:
        return 0, 0, 0

    auto_debt = get_auto_debt_mb(user)
    auto_need_mb = _ceil_mb(auto_debt)
    paid_auto = min(injected, auto_need_mb)
    if paid_auto > 0:
        user.total_quota_purchased_mb = int(user.total_quota_purchased_mb or 0) + int(paid_auto)
        injected -= paid_auto

    manual_balance = int(getattr(user, "manual_debt_mb", 0) or 0)
    paid_manual = 0
    if injected > 0 and manual_balance > 0:
        paid_manual = apply_manual_debt_payment(
            user=user,
            admin_actor=admin_actor,
            pay_mb=min(injected, manual_balance),
            source=source,
        )
        injected -= paid_manual

    return int(paid_auto), int(paid_manual), int(max(0, injected))


def mb_to_gb_str(value_mb: int) -> str:
    try:
        mb = float(value_mb or 0)
    except (TypeError, ValueError):
        return str(value_mb)
    return f"{(mb / 1024.0):.2f}"
