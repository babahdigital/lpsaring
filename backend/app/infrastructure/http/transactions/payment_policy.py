from flask import current_app

from app.services import settings_service
from app.infrastructure.db.models import Transaction


_CORE_API_METHOD_ORDER: tuple[str, ...] = ("qris", "gopay", "va", "shopeepay")
_CORE_API_VA_BANK_ORDER: tuple[str, ...] = ("bni", "bca", "bri", "mandiri", "permata", "cimb")


def normalize_payment_provider_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"core", "coreapi", "core_api", "core-api", "core api"}:
        return "core_api"
    if raw in {"snap", "snap_ui", "snap-ui", "snap ui"}:
        return "snap"
    return "snap"


def get_payment_provider_mode() -> str:
    raw = (
        settings_service.get_setting("PAYMENT_PROVIDER_MODE", None)
        or current_app.config.get("PAYMENT_PROVIDER_MODE")
        or "snap"
    )
    return normalize_payment_provider_mode(str(raw))


def normalize_payment_method(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"qris", "gopay", "va", "shopeepay"}:
        return raw
    return None


def normalize_va_bank(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"bca", "bni", "bri", "cimb", "mandiri", "permata"}:
        return raw
    return None


def parse_csv_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip().lower() for p in text.split(",")]
    return [p for p in parts if p]


def get_core_api_enabled_payment_methods() -> list[str]:
    raw = settings_service.get_setting("CORE_API_ENABLED_PAYMENT_METHODS", None)
    selected = set(parse_csv_values(raw))
    enabled = [m for m in _CORE_API_METHOD_ORDER if m in selected]
    if enabled:
        return enabled
    return ["qris", "gopay", "va"]


def get_core_api_enabled_va_banks() -> list[str]:
    raw = settings_service.get_setting("CORE_API_ENABLED_VA_BANKS", None)
    selected = set(parse_csv_values(raw))
    enabled = [b for b in _CORE_API_VA_BANK_ORDER if b in selected]
    if enabled:
        return enabled
    return list(_CORE_API_VA_BANK_ORDER)


def is_core_api_method_enabled(method: str, enabled_methods: list[str]) -> bool:
    m = str(method or "").strip().lower()
    return m in set(enabled_methods)


def is_core_api_va_bank_enabled(bank: str, enabled_banks: list[str]) -> bool:
    b = str(bank or "").strip().lower()
    return b in set(enabled_banks)


def tx_has_snap_initiation_data(tx: Transaction) -> bool:
    return bool(getattr(tx, "snap_token", None) or getattr(tx, "snap_redirect_url", None))


def tx_has_core_initiation_data(tx: Transaction) -> bool:
    if getattr(tx, "qr_code_url", None):
        return True
    if getattr(tx, "va_number", None):
        return True
    if getattr(tx, "payment_code", None) and getattr(tx, "biller_code", None):
        return True
    return False


def tx_matches_requested_core_payment(
    tx: Transaction,
    *,
    requested_method: str | None,
    requested_va_bank: str | None,
) -> bool:
    method = requested_method or "qris"

    tx_pm = str(getattr(tx, "payment_method", "") or "").strip().lower()

    if method in {"qris", "gopay", "shopeepay"}:
        if tx_pm:
            return tx_pm == method
        if method == "qris":
            return bool(getattr(tx, "qr_code_url", None))
        if method == "gopay":
            return bool(getattr(tx, "snap_redirect_url", None) or getattr(tx, "qr_code_url", None))
        if method == "shopeepay":
            return bool(getattr(tx, "snap_redirect_url", None) or getattr(tx, "qr_code_url", None))
        return False

    bank = requested_va_bank or "bni"
    if bank == "mandiri":
        if tx_pm:
            return tx_pm == "echannel"
        return bool(getattr(tx, "payment_code", None) and getattr(tx, "biller_code", None))

    if tx_pm:
        return tx_pm == f"{bank}_va"
    return False
