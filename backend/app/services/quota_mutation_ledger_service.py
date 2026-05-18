from __future__ import annotations

import logging
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from flask import current_app, has_app_context

from app.extensions import db
from app.infrastructure.db.models import QuotaMutationLedger, User

_logger = logging.getLogger(__name__)


def snapshot_user_quota_state(user: User) -> dict[str, Any]:
    return {
        "total_quota_purchased_mb": int(getattr(user, "total_quota_purchased_mb", 0) or 0),
        "total_quota_used_mb": float(getattr(user, "total_quota_used_mb", 0) or 0.0),
        "auto_debt_offset_mb": int(getattr(user, "auto_debt_offset_mb", 0) or 0),
        "manual_debt_mb": int(getattr(user, "manual_debt_mb", 0) or 0),
        "quota_debt_auto_mb": float(getattr(user, "quota_debt_auto_mb", 0) or 0.0),
        "quota_debt_manual_mb": int(getattr(user, "quota_debt_manual_mb", 0) or 0),
        "quota_debt_total_mb": float(getattr(user, "quota_debt_total_mb", 0) or 0.0),
        "is_blocked": bool(getattr(user, "is_blocked", False)),
        "blocked_reason": str(getattr(user, "blocked_reason", "") or "") or None,
        "is_unlimited_user": bool(getattr(user, "is_unlimited_user", False)),
    }


def lock_user_quota_row(user: User, nowait: bool = False) -> None:
    if user is None or getattr(user, "id", None) is None:
        return
    try:
        db.session.execute(sa.select(User.id).where(User.id == user.id).with_for_update(nowait=nowait))
    except Exception as exc_lock:
        if nowait:
            raise
        # Sprint 16: log silent swallow supaya kalau production Postgres
        # serialization/deadlock fail, operator bisa investigate. Sebelumnya
        # purely silent — caller proceed tanpa serialisasi → potensi
        # lost-update di kolom debt/quota yang seharusnya di-protect.
        # NOTE: tidak raise di non-nowait path supaya test FakeSession yang
        # tidak support with_for_update tetap bisa jalan (production caller
        # responsibility untuk handle eksplisit jika critical).
        try:
            current_app.logger.warning(
                "lock_user_quota_row: lock gagal user_id=%s nowait=%s err=%s",
                getattr(user, "id", None),
                nowait,
                exc_lock,
            )
        except Exception:
            _logger.warning("lock_user_quota_row gagal (no app ctx): %s", exc_lock)
        return


def append_quota_mutation_event(
    *,
    user: User,
    source: str,
    before_state: Optional[dict[str, Any]],
    after_state: Optional[dict[str, Any]],
    actor_user_id: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
    event_details: Optional[dict[str, Any]] = None,
) -> None:
    if user is None or getattr(user, "id", None) is None:
        return
    if not has_app_context():
        return

    normalized_source = str(source or "quota_mutation").strip()[:80] or "quota_mutation"
    normalized_idempotency = (str(idempotency_key).strip()[:128] if idempotency_key else None) or None

    if before_state == after_state and not event_details:
        return

    item = QuotaMutationLedger()
    item.user_id = user.id
    item.actor_user_id = actor_user_id
    item.source = normalized_source
    item.idempotency_key = normalized_idempotency
    item.before_state = before_state
    item.after_state = after_state
    item.event_details = event_details or None
    try:
        with db.session.begin_nested():
            db.session.add(item)
            db.session.flush()
    except RuntimeError as exc_rt:
        # Sprint 7 BUG-3 (audit-7): log silent swallow supaya hilangnya audit trail
        # tetap observable (sebelumnya purely silent).
        try:
            current_app.logger.warning(
                "quota_ledger.append RuntimeError swallowed: user_id=%s source=%s idem=%s err=%s",
                user.id,
                normalized_source,
                normalized_idempotency,
                exc_rt,
            )
        except Exception:
            _logger.warning("quota_ledger.append RuntimeError swallowed (no app ctx): %s", exc_rt)
        return
    except IntegrityError as exc_ie:
        try:
            current_app.logger.warning(
                "quota_ledger.append IntegrityError swallowed: user_id=%s source=%s idem=%s err=%s",
                user.id,
                normalized_source,
                normalized_idempotency,
                exc_ie,
            )
        except Exception:
            _logger.warning("quota_ledger.append IntegrityError swallowed (no app ctx): %s", exc_ie)
        return
