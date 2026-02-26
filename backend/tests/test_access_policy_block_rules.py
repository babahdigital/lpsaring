from __future__ import annotations

from types import SimpleNamespace

from app.services.access_policy_service import is_network_hard_block_required, resolve_allowed_binding_type_for_user


def test_network_hard_block_false_for_auto_debt_block_reason():
    user = SimpleNamespace(
        is_blocked=True,
        blocked_reason="quota_auto_debt_limit|debt_mb=512",
        is_active=True,
        approval_status="APPROVED",
        is_unlimited_user=False,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=1200,
        quota_expiry_date=None,
    )

    assert is_network_hard_block_required(user) is False


def test_network_hard_block_true_for_manual_eom_block_reason():
    user = SimpleNamespace(
        is_blocked=True,
        blocked_reason="quota_manual_debt_end_of_month|manual_debt_mb=10240",
        is_active=True,
        approval_status="APPROVED",
        is_unlimited_user=False,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=1200,
        quota_expiry_date=None,
    )

    assert is_network_hard_block_required(user) is True


def test_binding_type_blocked_only_for_hard_blocked_user(monkeypatch):
    monkeypatch.setattr(
        "app.services.access_policy_service.should_bypass_hotspot_login",
        lambda _user: False,
    )

    auto_blocked = SimpleNamespace(
        is_blocked=True,
        blocked_reason="quota_auto_debt_limit|debt_mb=900",
        is_active=True,
        approval_status="APPROVED",
        is_unlimited_user=False,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=1300,
        quota_expiry_date=None,
    )
    manual_blocked = SimpleNamespace(
        is_blocked=True,
        blocked_reason="quota_manual_debt_end_of_month|manual_debt_mb=10240",
        is_active=True,
        approval_status="APPROVED",
        is_unlimited_user=False,
        total_quota_purchased_mb=1024,
        total_quota_used_mb=1300,
        quota_expiry_date=None,
    )

    assert resolve_allowed_binding_type_for_user(auto_blocked) == "regular"
    assert resolve_allowed_binding_type_for_user(manual_blocked) == "blocked"
