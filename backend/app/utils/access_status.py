from __future__ import annotations

from enum import StrEnum


class AccessStatus(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    HABIS = "habis"
    FUP = "fup"


ACCESS_STATUS_ORDER: tuple[str, ...] = (
    AccessStatus.OK,
    AccessStatus.BLOCKED,
    AccessStatus.INACTIVE,
    AccessStatus.EXPIRED,
    AccessStatus.HABIS,
    AccessStatus.FUP,
)


STATUS_PAGE_ALLOWED: set[str] = {
    AccessStatus.BLOCKED,
    AccessStatus.INACTIVE,
    AccessStatus.EXPIRED,
    AccessStatus.HABIS,
    AccessStatus.FUP,
}
