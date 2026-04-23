from app.utils.quota_debt import (
    compute_debt_mb,
    compute_effective_remaining_mb,
    estimate_debt_rp_from_cheapest_package,
    format_rupiah,
    round_up_rp_to_10k,
)


def test_compute_debt_mb_basic():
    assert compute_debt_mb(100.0, 90.0) == 0.0
    assert compute_debt_mb(100.0, 100.0) == 0.0
    assert compute_debt_mb(100.0, 150.5) == 50.5


def test_compute_effective_remaining_mb_no_offset():
    assert compute_effective_remaining_mb(100.0, 30.0) == 70.0
    assert compute_effective_remaining_mb(100.0, 100.0) == 0.0
    assert compute_effective_remaining_mb(100.0, 150.0) == 0.0


def test_compute_effective_remaining_mb_with_offset_from_ex_unlimited():
    # Skenario user eks-unlimited: purchased=81920, used=156434, offset=156410.
    # Remaining efektif harus ~81896 MB, bukan 0.
    remaining = compute_effective_remaining_mb(
        purchased_mb=81920.0,
        used_mb=156434.96,
        auto_debt_offset_mb=156410.0,
    )
    assert remaining > 80000.0
    assert remaining < 82000.0


def test_compute_effective_remaining_mb_offset_fully_covers_overuse():
    # Offset cukup mengimbangi over-use: remaining = purchased.
    assert compute_effective_remaining_mb(1000.0, 500.0, 500.0) == 1000.0


def test_compute_effective_remaining_mb_debt_complement():
    # Saat remaining > 0 => debt harus 0 (compute_debt_mb(purchased+offset, used)).
    remaining = compute_effective_remaining_mb(100.0, 60.0, 20.0)
    debt = compute_debt_mb(100.0 + 20.0, 60.0)
    assert remaining == 60.0
    assert debt == 0.0

    # Saat used melebihi purchased+offset => remaining 0, debt > 0.
    remaining_neg = compute_effective_remaining_mb(50.0, 200.0, 20.0)
    debt_pos = compute_debt_mb(50.0 + 20.0, 200.0)
    assert remaining_neg == 0.0
    assert debt_pos > 0.0


def test_round_up_rp_to_10k():
    assert round_up_rp_to_10k(0) == 0
    assert round_up_rp_to_10k(1) == 10000
    assert round_up_rp_to_10k(9999) == 10000
    assert round_up_rp_to_10k(10000) == 10000
    assert round_up_rp_to_10k(58000) == 60000
    assert round_up_rp_to_10k(60000) == 60000


def test_format_rupiah():
    assert format_rupiah(0) == "0"
    assert format_rupiah(1000) == "1.000"
    assert format_rupiah(60000) == "60.000"


def test_estimate_debt_rp_from_cheapest_package_happy_path():
    # Cheapest package: 10GB for Rp 50.000
    # Price per MB = 50_000 / (10*1024) ~= 4.88
    est = estimate_debt_rp_from_cheapest_package(
        debt_mb=500.0,
        cheapest_package_price_rp=50000,
        cheapest_package_quota_gb=10.0,
        cheapest_package_name="Paket 10GB",
    )
    assert est.debt_mb == 500.0
    assert est.estimated_rp_raw is not None
    assert est.estimated_rp_rounded is not None
    # Rounded up to 10k
    assert est.estimated_rp_rounded % 10000 == 0


def test_estimate_debt_rp_missing_package():
    est = estimate_debt_rp_from_cheapest_package(
        debt_mb=500.0,
        cheapest_package_price_rp=None,
        cheapest_package_quota_gb=None,
    )
    assert est.estimated_rp_raw is None
    assert est.estimated_rp_rounded is None
