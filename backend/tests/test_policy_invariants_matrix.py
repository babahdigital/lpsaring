from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import access_policy_service as policy


def _approved_user(**overrides):
    base = {
        "is_blocked": False,
        "blocked_reason": None,
        "is_active": True,
        "approval_status": "APPROVED",
        "is_unlimited_user": False,
        "total_quota_purchased_mb": 8192,
        "total_quota_used_mb": 1024,
        "quota_expiry_date": datetime.now(timezone.utc) + timedelta(days=3),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "user,expected_status",
    [
        (_approved_user(is_blocked=True, blocked_reason="quota_auto_debt_limit|debt_mb=700"), "blocked"),
        (_approved_user(is_active=False), "inactive"),
        (_approved_user(approval_status="PENDING_APPROVAL"), "inactive"),
        (_approved_user(is_unlimited_user=True, quota_expiry_date=None), "unlimited"),
        (_approved_user(quota_expiry_date=datetime.now(timezone.utc) - timedelta(minutes=1)), "expired"),
        (_approved_user(total_quota_purchased_mb=1024, total_quota_used_mb=1024), "habis"),
        (_approved_user(total_quota_purchased_mb=8192, total_quota_used_mb=7168), "fup"),
        (_approved_user(total_quota_purchased_mb=8192, total_quota_used_mb=1024), "active"),
    ],
)
def test_policy_invariant_status_matrix(monkeypatch, user, expected_status):
    monkeypatch.setattr(policy.settings_service, "get_setting_as_int", lambda key, default=0: 3072)

    assert policy.get_user_access_status(user) == expected_status


def test_policy_invariant_auto_debt_block_is_not_network_hard_block():
    user = _approved_user(is_blocked=True, blocked_reason="quota_auto_debt_limit|debt_mb=800")

    assert policy.is_network_hard_block_required(user) is False
    assert policy.resolve_allowed_binding_type_for_user(user) == "regular"


def test_policy_invariant_manual_eom_block_is_network_hard_block():
    user = _approved_user(is_blocked=True, blocked_reason="quota_manual_debt_end_of_month|manual_debt_mb=10240")

    assert policy.is_network_hard_block_required(user) is True
    assert policy.resolve_allowed_binding_type_for_user(user) == "blocked"


def test_policy_invariant_unlimited_needs_no_hotspot_login(monkeypatch):
    user = _approved_user(is_unlimited_user=True, quota_expiry_date=None)

    monkeypatch.setattr(policy, "get_hotspot_bypass_statuses", lambda: {"active", "fup", "unlimited"})

    assert policy.should_bypass_hotspot_login(user) is True
    assert policy.resolve_allowed_binding_type_for_user(user) == "bypassed"
