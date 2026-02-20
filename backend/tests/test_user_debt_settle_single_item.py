import uuid
from app.services.user_management import user_debt


class _User:
    def __init__(self, *, manual_debt_mb: int):
        self.id = uuid.uuid4()
        self.role = None
        self.manual_debt_mb = manual_debt_mb
        self.manual_debt_updated_at = None


class _Debt:
    def __init__(self, *, user_id, amount_mb: int, paid_mb: int = 0):
        self.user_id = user_id
        self.amount_mb = amount_mb
        self.paid_mb = paid_mb
        self.is_paid = False
        self.paid_at = None
        self.last_paid_by_id = None
        self.last_paid_source = None


def test_settle_single_manual_debt_item_pays_remaining_and_updates_cached_balance():
    user = _User(manual_debt_mb=500)
    debt = _Debt(user_id=user.id, amount_mb=500, paid_mb=100)

    paid = user_debt.settle_manual_debt_item_to_zero(
        user=user,
        admin_actor=None,
        debt=debt,
        source="test",
    )

    assert paid == 400
    assert debt.paid_mb == 500
    assert debt.is_paid is True
    assert user.manual_debt_mb == 100
    assert user.manual_debt_updated_at is not None


def test_settle_single_manual_debt_item_noop_when_wrong_user():
    user = _User(manual_debt_mb=500)
    debt = _Debt(user_id=uuid.uuid4(), amount_mb=500, paid_mb=0)

    paid = user_debt.settle_manual_debt_item_to_zero(
        user=user,
        admin_actor=None,
        debt=debt,
        source="test",
    )
    assert paid == 0
    assert debt.paid_mb == 0
