from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

from app.infrastructure.http.transactions import debt_helpers
from app.utils.block_reasons import build_auto_debt_limit_reason, build_manual_debt_eom_reason


class _FakeQuery:
    def __init__(self, result=None):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, debt_item=None):
        self._debt_item = debt_item
        self.commits = 0

    def query(self, model):
        if model.__name__ == 'UserQuotaDebt':
            return _FakeQuery(self._debt_item)
        return _FakeQuery(None)

    def commit(self):
        self.commits += 1


def test_apply_debt_settlement_manual_item_path(monkeypatch):
    manual_debt_id = uuid.uuid4()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        quota_debt_total_mb=2048,
        quota_debt_auto_mb=0,
        quota_debt_manual_mb=2048,
        is_blocked=True,
        blocked_reason=build_auto_debt_limit_reason(debt_mb=2048, limit_mb=500, source='test'),
        blocked_at='x',
        blocked_by_id=uuid.uuid4(),
    )
    transaction = SimpleNamespace(user=user, midtrans_order_id=f'DEBT-{manual_debt_id}~BD-LPSR-ORDER')
    fake_session = _FakeSession(debt_item=SimpleNamespace(id=manual_debt_id, user_id=user.id))

    called = {'manual': False, 'auto': False, 'sync': False}

    def _fake_settle_manual(*, user, admin_actor, debt, source):
        called['manual'] = True
        assert admin_actor is None
        assert debt is not None
        assert source == 'user_debt_settlement_payment_manual_item'
        user.quota_debt_total_mb = 0
        user.quota_debt_manual_mb = 0
        return 2048

    def _fake_clear_all(*, user, admin_actor, source):
        called['auto'] = True
        return (0, 0)

    monkeypatch.setattr(debt_helpers.user_debt_service, 'settle_manual_debt_item_to_zero', _fake_settle_manual)
    monkeypatch.setattr(debt_helpers.user_debt_service, 'clear_all_debts_to_zero', _fake_clear_all)
    monkeypatch.setattr(debt_helpers, 'sync_address_list_for_single_user', lambda _user: called.__setitem__('sync', True))

    result = debt_helpers.apply_debt_settlement_on_success(
        session=fake_session,
        transaction=cast(Any, transaction),
    )

    assert called['manual'] is True
    assert called['auto'] is False
    assert called['sync'] is True
    assert fake_session.commits == 1
    assert result['paid_manual_mb'] == 2048
    assert result['paid_auto_mb'] == 0
    assert result['unblocked'] is True
    assert user.is_blocked is False


def test_apply_debt_settlement_auto_path(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        quota_debt_total_mb=1024,
        quota_debt_auto_mb=1024,
        quota_debt_manual_mb=0,
        is_blocked=True,
        blocked_reason=build_manual_debt_eom_reason(debt_mb_text='1024', manual_debt_mb=1024),
        blocked_at='x',
        blocked_by_id=uuid.uuid4(),
    )
    transaction = SimpleNamespace(user=user, midtrans_order_id='DEBT-ORD-12345')
    fake_session = _FakeSession(debt_item=None)

    called = {'manual': False, 'auto': False}

    def _fake_settle_manual(*, user, admin_actor, debt, source):
        called['manual'] = True
        return 0

    def _fake_clear_all(*, user, admin_actor, source):
        called['auto'] = True
        assert source == 'user_debt_settlement_payment'
        user.quota_debt_total_mb = 0
        user.quota_debt_auto_mb = 0
        return (1024, 0)

    monkeypatch.setattr(debt_helpers.user_debt_service, 'settle_manual_debt_item_to_zero', _fake_settle_manual)
    monkeypatch.setattr(debt_helpers.user_debt_service, 'clear_all_debts_to_zero', _fake_clear_all)
    monkeypatch.setattr(debt_helpers, 'sync_address_list_for_single_user', lambda _user: None)

    result = debt_helpers.apply_debt_settlement_on_success(
        session=fake_session,
        transaction=cast(Any, transaction),
    )

    assert called['manual'] is False
    assert called['auto'] is True
    assert fake_session.commits == 1
    assert result['paid_auto_mb'] == 1024
    assert result['paid_manual_mb'] == 0
    assert result['unblocked'] is True
    assert user.is_blocked is False
