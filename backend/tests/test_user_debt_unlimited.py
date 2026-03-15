from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.user_management import user_quota
from app.services.user_management import user_debt
from app.utils.block_reasons import build_auto_debt_limit_reason, build_manual_debt_eom_reason


class _NoopContextManager:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


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


@pytest.mark.parametrize(
    "blocked_reason",
    [
        build_auto_debt_limit_reason(debt_mb=1024, limit_mb=1024, source="test_set_unlimited"),
        build_manual_debt_eom_reason(debt_mb_text="1024", manual_debt_mb=1024),
    ],
)
def test_set_user_unlimited_keeps_existing_debt_block(monkeypatch, blocked_reason):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=None,
        is_unlimited_user=False,
        is_blocked=True,
        blocked_reason=blocked_reason,
        blocked_at="existing-blocked-at",
        blocked_by_id=uuid.uuid4(),
        full_name="Debt Block User",
        phone_number="+628111111111",
        mikrotik_password="pwd",
        mikrotik_server_name="srv-user",
        mikrotik_profile_name="profile-aktif",
        mikrotik_user_exists=True,
        quota_expiry_date=None,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=2048.0,
        auto_debt_offset_mb=0,
        manual_debt_mb=1024,
        devices=[],
    )
    admin_actor = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin Unlimited",
        is_super_admin_role=True,
    )

    monkeypatch.setattr(user_quota, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(user_quota, "append_quota_mutation_event", lambda **_kwargs: None)
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

    ok, _msg = user_quota.set_user_unlimited(user, admin_actor, True)

    assert ok is True
    assert user.is_unlimited_user is True
    assert user.is_blocked is True
    assert user.blocked_reason == blocked_reason
    assert user.blocked_at == "existing-blocked-at"
    assert user.blocked_by_id is not None
