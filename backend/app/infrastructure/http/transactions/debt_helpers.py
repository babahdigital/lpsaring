from __future__ import annotations

from typing import Any

from app.extensions import db
from app.infrastructure.db.models import Package, Transaction, User, UserQuotaDebt
from app.services.quota_mutation_ledger_service import (
    append_quota_mutation_event,
    lock_user_quota_row,
    snapshot_user_quota_state,
)
from app.services.user_management import user_debt as user_debt_service
from app.utils.block_reasons import is_debt_block_reason

from .helpers import _extract_manual_debt_id_from_order_id


def estimate_user_debt_rp(user: User) -> int:
    try:
        debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
    except Exception:
        debt_total_mb = 0.0
    if debt_total_mb <= 0:
        return 0

    try:
        debt_gb = float(debt_total_mb) / 1024.0

        base_q = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
        )

        ref_pkg = (
            base_q.filter(Package.data_quota_gb >= debt_gb)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .first()
        )
        if ref_pkg is None:
            ref_pkg = base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).first()

        if not ref_pkg or ref_pkg.price is None or ref_pkg.data_quota_gb is None:
            return 0

        from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package

        estimate = estimate_debt_rp_from_cheapest_package(
            debt_mb=float(debt_total_mb),
            cheapest_package_price_rp=int(ref_pkg.price),
            cheapest_package_quota_gb=float(ref_pkg.data_quota_gb),
            cheapest_package_name=str(getattr(ref_pkg, "name", "") or "") or None,
        )
        return int(estimate.estimated_rp_rounded or 0)
    except Exception:
        return 0


def estimate_debt_rp_for_mb(debt_mb: float) -> int:
    try:
        mb = float(debt_mb or 0)
    except Exception:
        mb = 0.0
    if mb <= 0:
        return 0

    try:
        debt_gb = float(mb) / 1024.0

        base_q = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
        )

        ref_pkg = (
            base_q.filter(Package.data_quota_gb >= debt_gb)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .first()
        )
        if ref_pkg is None:
            ref_pkg = base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).first()

        if not ref_pkg or ref_pkg.price is None or ref_pkg.data_quota_gb is None:
            return 0

        from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package

        estimate = estimate_debt_rp_from_cheapest_package(
            debt_mb=float(mb),
            cheapest_package_price_rp=int(ref_pkg.price),
            cheapest_package_quota_gb=float(ref_pkg.data_quota_gb),
            cheapest_package_name=str(getattr(ref_pkg, "name", "") or "") or None,
        )
        return int(estimate.estimated_rp_rounded or 0)
    except Exception:
        return 0


def apply_debt_settlement_on_success(*, session, transaction: Transaction) -> dict[str, Any]:
    user = getattr(transaction, "user", None)
    if user is None:
        raise ValueError("Transaksi pelunasan tunggakan tidak memiliki user.")

    lock_user_quota_row(user)
    before_state = snapshot_user_quota_state(user)

    manual_debt_id = _extract_manual_debt_id_from_order_id(getattr(transaction, "midtrans_order_id", None))

    debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
    if debt_total_mb <= 0:
        return {"paid_auto_mb": 0, "paid_manual_mb": 0, "paid_total_mb": 0, "unblocked": False}

    debt_auto_before = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
    debt_manual_before = int(getattr(user, "quota_debt_manual_mb", 0) or 0)
    was_blocked = bool(getattr(user, "is_blocked", False))
    blocked_reason = str(getattr(user, "blocked_reason", "") or "")

    if manual_debt_id is not None:
        debt_item = (
            session.query(UserQuotaDebt)
            .filter(UserQuotaDebt.id == manual_debt_id)
            .filter(UserQuotaDebt.user_id == user.id)
            .with_for_update()
            .first()
        )
        paid_auto_mb = 0
        paid_manual_mb = int(
            user_debt_service.settle_manual_debt_item_to_zero(
                user=user,
                admin_actor=None,
                debt=debt_item,
                source="user_debt_settlement_payment_manual_item",
            )
        )
    else:
        paid_auto_mb, paid_manual_mb = user_debt_service.clear_all_debts_to_zero(
            user=user,
            admin_actor=None,
            source="user_debt_settlement_payment",
        )

    unblocked = False
    if was_blocked and is_debt_block_reason(blocked_reason):
        if float(getattr(user, "quota_debt_total_mb", 0) or 0) <= 0:
            user.is_blocked = False
            user.blocked_reason = None
            user.blocked_at = None
            user.blocked_by_id = None
            unblocked = True

    append_quota_mutation_event(
        user=user,
        source="transactions.debt_settlement_success",
        before_state=before_state,
        after_state=snapshot_user_quota_state(user),
        idempotency_key=str(getattr(transaction, "midtrans_order_id", "") or "")[:128] or None,
        event_details={
            "transaction_id": str(getattr(transaction, "id", "") or ""),
            "order_id": str(getattr(transaction, "midtrans_order_id", "") or ""),
            "paid_auto_mb": int(paid_auto_mb),
            "paid_manual_mb": int(paid_manual_mb),
            "unblocked": bool(unblocked),
        },
    )

    return {
        "paid_auto_mb": int(paid_auto_mb),
        "paid_manual_mb": int(paid_manual_mb),
        "paid_total_mb": int(paid_auto_mb) + int(paid_manual_mb),
        "debt_auto_before": float(debt_auto_before),
        "debt_manual_before": int(debt_manual_before),
        "unblocked": bool(unblocked),
    }
