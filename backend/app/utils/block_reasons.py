from __future__ import annotations

from typing import Optional


AUTO_DEBT_LIMIT_PREFIX = "quota_debt_limit|"
AUTO_DEBT_LIMIT_LEGACY_PREFIX = "quota_auto_debt_limit|"

MANUAL_DEBT_EOM_PREFIX = "quota_manual_debt_end_of_month|"
MANUAL_DEBT_EOM_LEGACY_PREFIX = "quota_debt_end_of_month|"


def _normalize_reason(reason: object) -> str:
    return str(reason or "").strip().lower()


def is_auto_debt_limit_reason(reason: object) -> bool:
    normalized = _normalize_reason(reason)
    return normalized.startswith(AUTO_DEBT_LIMIT_PREFIX) or normalized.startswith(AUTO_DEBT_LIMIT_LEGACY_PREFIX)


def is_manual_debt_eom_reason(reason: object) -> bool:
    normalized = _normalize_reason(reason)
    return normalized.startswith(MANUAL_DEBT_EOM_PREFIX) or normalized.startswith(MANUAL_DEBT_EOM_LEGACY_PREFIX)


def is_debt_block_reason(reason: object) -> bool:
    return is_auto_debt_limit_reason(reason) or is_manual_debt_eom_reason(reason)


def build_auto_debt_limit_reason(*, debt_mb: float, limit_mb: int, source: str) -> str:
    return f"{AUTO_DEBT_LIMIT_PREFIX}debt_mb={float(debt_mb):.2f}|limit_mb={int(limit_mb)}|source={source}"


def build_manual_debt_eom_reason(
    *,
    debt_mb_text: str,
    manual_debt_mb: int,
    estimated_rp: Optional[int] = None,
    base_pkg_name: Optional[str] = None,
) -> str:
    reason = f"{MANUAL_DEBT_EOM_PREFIX}debt_mb={debt_mb_text}|manual_debt_mb={int(manual_debt_mb)}"
    if isinstance(estimated_rp, int):
        reason += f"|estimated_rp={int(estimated_rp)}"
    if base_pkg_name:
        reason += f"|base_pkg={base_pkg_name}"
    return reason
