from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass(frozen=True)
class DebtEstimate:
    debt_mb: float
    estimated_rp_raw: Optional[int]
    estimated_rp_rounded: Optional[int]
    price_per_mb_rp: Optional[float]
    package_name: Optional[str]


def compute_debt_mb(purchased_mb: float, used_mb: float) -> float:
    """Return debt in MB with better numeric stability.

    Inputs may come from floats (e.g., converted from bytes) and can carry
    floating precision artifacts. Use Decimal(str(...)) to avoid negative/near-zero
    drift (e.g., -1e-12).
    """

    def _to_decimal(value: object) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    purchased = _to_decimal(purchased_mb)
    used = _to_decimal(used_mb)
    debt = used - purchased

    if debt <= 0:
        return 0.0

    # Quantize to 2 decimals MB to keep output stable for UI/logs.
    try:
        debt = debt.quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
    except Exception:
        pass

    return float(debt)


def round_up_rp_to_10k(value_rp: int) -> int:
    if value_rp <= 0:
        return 0
    return int(math.ceil(value_rp / 10000.0) * 10000)


def format_rupiah(value_rp: int) -> str:
    try:
        value_int = int(value_rp)
    except (TypeError, ValueError):
        return str(value_rp)
    return f"{value_int:,}".replace(",", ".")


def estimate_debt_rp_from_cheapest_package(
    *,
    debt_mb: float,
    cheapest_package_price_rp: Optional[int],
    cheapest_package_quota_gb: Optional[float],
    cheapest_package_name: Optional[str] = None,
) -> DebtEstimate:
    if debt_mb <= 0:
        return DebtEstimate(
            debt_mb=0.0,
            estimated_rp_raw=0,
            estimated_rp_rounded=0,
            price_per_mb_rp=0.0,
            package_name=cheapest_package_name,
        )

    if not cheapest_package_price_rp or not cheapest_package_quota_gb or cheapest_package_quota_gb <= 0:
        return DebtEstimate(
            debt_mb=float(debt_mb),
            estimated_rp_raw=None,
            estimated_rp_rounded=None,
            price_per_mb_rp=None,
            package_name=cheapest_package_name,
        )

    try:
        price = Decimal(int(cheapest_package_price_rp))
        quota_mb = Decimal(str(cheapest_package_quota_gb)) * Decimal(1024)
        if quota_mb <= 0:
            raise InvalidOperation
        price_per_mb = price / quota_mb
        estimated_raw = int((price_per_mb * Decimal(str(debt_mb))).to_integral_value(rounding="ROUND_HALF_UP"))
    except (InvalidOperation, ValueError, TypeError):
        return DebtEstimate(
            debt_mb=float(debt_mb),
            estimated_rp_raw=None,
            estimated_rp_rounded=None,
            price_per_mb_rp=None,
            package_name=cheapest_package_name,
        )

    rounded = round_up_rp_to_10k(estimated_raw)
    return DebtEstimate(
        debt_mb=float(debt_mb),
        estimated_rp_raw=estimated_raw,
        estimated_rp_rounded=rounded,
        price_per_mb_rp=float(price_per_mb),
        package_name=cheapest_package_name,
    )
