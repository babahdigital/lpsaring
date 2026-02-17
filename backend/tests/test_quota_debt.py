from app.utils.quota_debt import (
    compute_debt_mb,
    estimate_debt_rp_from_cheapest_package,
    format_rupiah,
    round_up_rp_to_10k,
)


def test_compute_debt_mb_basic():
    assert compute_debt_mb(100.0, 90.0) == 0.0
    assert compute_debt_mb(100.0, 100.0) == 0.0
    assert compute_debt_mb(100.0, 150.5) == 50.5


def test_round_up_rp_to_10k():
    assert round_up_rp_to_10k(0) == 0
    assert round_up_rp_to_10k(1) == 10000
    assert round_up_rp_to_10k(9999) == 10000
    assert round_up_rp_to_10k(10000) == 10000
    assert round_up_rp_to_10k(58000) == 60000
    assert round_up_rp_to_10k(60000) == 60000


def test_format_rupiah():
    assert format_rupiah(0) == '0'
    assert format_rupiah(1000) == '1.000'
    assert format_rupiah(60000) == '60.000'


def test_estimate_debt_rp_from_cheapest_package_happy_path():
    # Cheapest package: 10GB for Rp 50.000
    # Price per MB = 50_000 / (10*1024) ~= 4.88
    est = estimate_debt_rp_from_cheapest_package(
        debt_mb=500.0,
        cheapest_package_price_rp=50000,
        cheapest_package_quota_gb=10.0,
        cheapest_package_name='Paket 10GB',
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
