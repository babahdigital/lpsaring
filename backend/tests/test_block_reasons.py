from app.utils.block_reasons import (
    AUTO_DEBT_LIMIT_PREFIX,
    MANUAL_DEBT_EOM_PREFIX,
    build_auto_debt_limit_reason,
    build_manual_debt_eom_reason,
    is_auto_debt_limit_reason,
    is_debt_block_reason,
    is_manual_debt_eom_reason,
)


def test_auto_debt_reason_detects_canonical_and_legacy():
    assert is_auto_debt_limit_reason("quota_debt_limit|debt_mb=10") is True
    assert is_auto_debt_limit_reason("quota_auto_debt_limit|debt_mb=10") is True
    assert is_auto_debt_limit_reason("other_reason|x=1") is False


def test_manual_eom_reason_detects_canonical_and_legacy():
    assert is_manual_debt_eom_reason("quota_manual_debt_end_of_month|manual_debt_mb=100") is True
    assert is_manual_debt_eom_reason("quota_debt_end_of_month|manual_debt_mb=100") is True
    assert is_manual_debt_eom_reason("other_reason|x=1") is False


def test_debt_block_reason_matches_both_kinds():
    assert is_debt_block_reason("quota_debt_limit|debt_mb=1") is True
    assert is_debt_block_reason("quota_manual_debt_end_of_month|manual_debt_mb=1") is True
    assert is_debt_block_reason("quota_debt_end_of_month|manual_debt_mb=1") is True
    assert is_debt_block_reason("manual_admin_block|reason=test") is False


def test_build_auto_debt_reason_uses_canonical_prefix():
    reason = build_auto_debt_limit_reason(debt_mb=12.345, limit_mb=500, source="sync")
    assert reason.startswith(AUTO_DEBT_LIMIT_PREFIX)
    assert "debt_mb=12.35" in reason
    assert "limit_mb=500" in reason
    assert "source=sync" in reason


def test_build_manual_eom_reason_uses_canonical_prefix_and_optional_fields():
    reason = build_manual_debt_eom_reason(
        debt_mb_text="1024.00",
        manual_debt_mb=1024,
        estimated_rp=25000,
        base_pkg_name="Paket A",
    )
    assert reason.startswith(MANUAL_DEBT_EOM_PREFIX)
    assert "manual_debt_mb=1024" in reason
    assert "estimated_rp=25000" in reason
    assert "base_pkg=Paket A" in reason
