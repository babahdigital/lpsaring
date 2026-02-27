from __future__ import annotations

import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.infrastructure.http.transactions import debt_helpers
from app.services.user_management import user_debt, user_quota
from app.utils.block_reasons import build_manual_debt_eom_reason


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
    def query(self, _model):
        return _FakeQuery(None)


class _NoopContextManager:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.stress
def test_stress_race_quota_debt_interleaving_invariants(monkeypatch):
    random.seed(20260228)

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=False,
        is_blocked=False,
        blocked_reason=None,
        blocked_at=None,
        blocked_by_id=None,
        full_name="Stress User",
        phone_number="+6281234567890",
        mikrotik_password="pwd",
        mikrotik_server_name="srv-user",
        mikrotik_profile_name="profile-aktif",
        mikrotik_user_exists=True,
        quota_expiry_date=None,
        total_quota_purchased_mb=2048,
        total_quota_used_mb=1024.0,
        auto_debt_offset_mb=0,
        manual_debt_mb=0,
        devices=[],
    )

    admin_actor = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin Stress",
        is_super_admin_role=True,
    )
    typed_user = cast(Any, user)
    typed_admin_actor = cast(Any, admin_actor)

    monkeypatch.setattr(user_debt, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(user_debt, "append_quota_mutation_event", lambda **_kwargs: None)
    monkeypatch.setattr(user_quota, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(user_quota, "append_quota_mutation_event", lambda **_kwargs: None)
    monkeypatch.setattr(debt_helpers, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(debt_helpers, "append_quota_mutation_event", lambda **_kwargs: None)

    monkeypatch.setattr(user_quota, "_handle_mikrotik_operation", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(user_quota, "resolve_target_profile_for_user", lambda _user: "profile-aktif")
    monkeypatch.setattr(user_quota, "sync_address_list_for_single_user", lambda _user: True)
    monkeypatch.setattr(user_quota, "get_mikrotik_connection", lambda: _NoopContextManager())
    monkeypatch.setattr(user_quota, "_sync_ip_binding_for_authorized_devices", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_quota, "_log_admin_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_quota, "_send_whatsapp_notification", lambda *_args, **_kwargs: None)

    fake_session = _FakeSession()

    def _flow_sync_usage() -> None:
        # Simulate periodic hotspot usage sync increments.
        user.total_quota_used_mb = float(user.total_quota_used_mb or 0.0) + float(random.choice([8, 16, 24, 32]))

    def _flow_inject_quota() -> None:
        ok, _msg = user_quota.inject_user_quota(
            user=typed_user,
            admin_actor=typed_admin_actor,
            mb_to_add=int(random.choice([32, 64, 96])),
            days_to_add=0,
        )
        assert ok is True

    def _flow_debt_settlement() -> None:
        transaction = SimpleNamespace(
            id=uuid.uuid4(),
            user=user,
            midtrans_order_id=f"BD-DBLP-{uuid.uuid4().hex[:12]}",
        )
        debt_helpers.apply_debt_settlement_on_success(session=fake_session, transaction=cast(Any, transaction))

    flows = [_flow_sync_usage, _flow_inject_quota, _flow_debt_settlement]

    def _worker(iterations: int) -> None:
        for _ in range(iterations):
            flow = random.choice(flows)
            flow()

    workers = 20
    iterations_per_worker = 30
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda _idx: _worker(iterations_per_worker), range(workers)))

    # Final forced settle: auto debt must become zero.
    user_debt.settle_auto_debt_to_zero(typed_user)

    assert int(user.total_quota_purchased_mb or 0) >= 0
    assert float(user.total_quota_used_mb or 0.0) >= 0.0
    assert int(user.auto_debt_offset_mb or 0) >= 0
    assert int(user.manual_debt_mb or 0) >= 0
    assert user_debt.get_auto_debt_mb(typed_user) == 0.0


@pytest.mark.stress
def test_stress_race_manual_debt_then_set_unlimited_invariants(monkeypatch):
    random.seed(20260301)

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=False,
        is_blocked=True,
        blocked_reason=build_manual_debt_eom_reason(debt_mb_text="256", manual_debt_mb=256),
        blocked_at="x",
        blocked_by_id=uuid.uuid4(),
        full_name="Stress Unlimited User",
        phone_number="+628111111111",
        mikrotik_password="pwd",
        mikrotik_server_name="srv-user",
        mikrotik_profile_name="profile-aktif",
        mikrotik_user_exists=True,
        quota_expiry_date=None,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=768.0,
        auto_debt_offset_mb=0,
        manual_debt_mb=256,
        devices=[],
    )

    admin_actor = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin Stress Unlimited",
        is_super_admin_role=True,
    )
    typed_user = cast(Any, user)
    typed_admin_actor = cast(Any, admin_actor)

    monkeypatch.setattr(user_debt, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(user_debt, "append_quota_mutation_event", lambda **_kwargs: None)
    monkeypatch.setattr(user_quota, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(user_quota, "append_quota_mutation_event", lambda **_kwargs: None)

    def _fake_clear_all_debts_to_zero(*, user, admin_actor, source):
        paid_auto = int(max(0, int(getattr(user, "auto_debt_offset_mb", 0) or 0)))
        paid_manual = int(max(0, int(getattr(user, "manual_debt_mb", 0) or 0)))
        user.auto_debt_offset_mb = int(getattr(user, "auto_debt_offset_mb", 0) or 0)
        user.manual_debt_mb = 0
        return paid_auto, paid_manual

    monkeypatch.setattr(user_debt, "clear_all_debts_to_zero", _fake_clear_all_debts_to_zero)

    monkeypatch.setattr(user_quota, "_handle_mikrotik_operation", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(
        user_quota.settings_service,
        "get_setting",
        lambda key, default=None: {
            "MIKROTIK_UNLIMITED_PROFILE": "profile-unlimited",
            "MIKROTIK_ACTIVE_PROFILE": "profile-aktif",
            "MIKROTIK_USER_PROFILE": "profile-aktif",
            "MIKROTIK_DEFAULT_PROFILE": "default",
            "MIKROTIK_KOMANDAN_PROFILE": "profile-aktif",
        }.get(key, default),
    )
    monkeypatch.setattr(user_quota, "sync_address_list_for_single_user", lambda _user: True)
    monkeypatch.setattr(user_quota, "get_mikrotik_connection", lambda: _NoopContextManager())
    monkeypatch.setattr(user_quota, "_sync_ip_binding_for_authorized_devices", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_quota, "_log_admin_action", lambda *_args, **_kwargs: None)

    def _flow_add_manual_debt_pressure() -> None:
        if bool(getattr(user, "is_unlimited_user", False)):
            return
        user.manual_debt_mb = int(user.manual_debt_mb or 0) + int(random.choice([8, 16, 24]))

    def _flow_set_unlimited_true() -> None:
        ok, _msg = user_quota.set_user_unlimited(typed_user, typed_admin_actor, True)
        assert ok is True

    flows = [_flow_add_manual_debt_pressure, _flow_set_unlimited_true]

    def _worker(iterations: int) -> None:
        for _ in range(iterations):
            random.choice(flows)()

    workers = 10
    iterations_per_worker = 25
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda _idx: _worker(iterations_per_worker), range(workers)))

    ok_final, _final_msg = user_quota.set_user_unlimited(typed_user, typed_admin_actor, True)
    assert ok_final is True

    assert bool(user.is_unlimited_user) is True
    assert int(user.manual_debt_mb or 0) == 0
    assert bool(user.is_blocked) is False
