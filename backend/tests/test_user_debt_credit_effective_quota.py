from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

from app.services.user_management import user_debt


def test_consume_injected_mb_for_auto_debt_only_reduces_effective_quota():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=False,
        total_quota_purchased_mb=1000,
        total_quota_used_mb=1010,
        auto_debt_offset_mb=0,
        manual_debt_mb=0,
    )

    paid_auto_mb, remaining_injected_mb = user_debt.consume_injected_mb_for_auto_debt_only(
        user=cast(Any, user),
        admin_actor=None,
        injected_mb=20480,
        source="test_manual_debt_advance",
    )

    assert paid_auto_mb == 10
    assert remaining_injected_mb == 20470
    assert user.auto_debt_offset_mb == 10


def test_consume_injected_mb_for_debt_consumes_auto_then_manual(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=False,
        total_quota_purchased_mb=1000,
        total_quota_used_mb=1030,
        auto_debt_offset_mb=0,
        manual_debt_mb=100,
    )

    def _fake_apply_manual_debt_payment(*, user, admin_actor, pay_mb, source):
        paid = int(pay_mb)
        user.manual_debt_mb = max(0, int(user.manual_debt_mb) - paid)
        return paid

    monkeypatch.setattr(user_debt, "apply_manual_debt_payment", _fake_apply_manual_debt_payment)

    paid_auto_mb, paid_manual_mb, remaining_injected_mb = user_debt.consume_injected_mb_for_debt(
        user=cast(Any, user),
        admin_actor=None,
        injected_mb=200,
        source="test_inject",
    )

    assert paid_auto_mb == 30
    assert paid_manual_mb == 100
    assert remaining_injected_mb == 70
    assert user.auto_debt_offset_mb == 30
    assert user.manual_debt_mb == 0
