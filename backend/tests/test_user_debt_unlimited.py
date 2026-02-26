from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.user_management import user_debt


def test_get_auto_debt_mb_returns_zero_for_unlimited_user():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=True,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=8192,
        auto_debt_offset_mb=0,
    )

    assert user_debt.get_auto_debt_mb(user) == 0.0


def test_clear_all_debts_to_zero_for_unlimited_clears_manual_only(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=True,
        manual_debt_mb=2048,
    )

    called = {"pay_mb": None}

    def _fake_apply_manual_debt_payment(*, user, admin_actor, pay_mb, source):
        called["pay_mb"] = int(pay_mb)
        user.manual_debt_mb = 0
        return int(pay_mb)

    monkeypatch.setattr(user_debt, "apply_manual_debt_payment", _fake_apply_manual_debt_payment)

    paid_auto_mb, paid_manual_mb = user_debt.clear_all_debts_to_zero(
        user=user,
        admin_actor=None,
        source="test_set_unlimited",
    )

    assert paid_auto_mb == 0
    assert paid_manual_mb == 2048
    assert called["pay_mb"] == 2048
    assert user.manual_debt_mb == 0
