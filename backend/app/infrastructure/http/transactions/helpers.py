import base64
import uuid

from flask import current_app, has_app_context

from app.infrastructure.db.models import User
from app.utils.formatters import get_phone_number_variations, normalize_to_e164


def _normalize_phone_digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _is_demo_user_eligible(user: User | None) -> bool:
    if user is None:
        return False

    if not bool(current_app.config.get("DEMO_MODE_ENABLED", False)):
        return False

    if bool(current_app.config.get("DEMO_ALLOW_ANY_PHONE", False)):
        return True

    allowed_raw = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(allowed_raw, list) or len(allowed_raw) == 0:
        return False

    user_phone_raw = str(getattr(user, "phone_number", "") or "").strip()
    if user_phone_raw == "":
        return False

    user_digits_variants: set[str] = {_normalize_phone_digits(user_phone_raw)}
    try:
        normalized_user = normalize_to_e164(user_phone_raw)
        for var in get_phone_number_variations(normalized_user):
            user_digits_variants.add(_normalize_phone_digits(var))
    except Exception:
        pass

    user_digits_variants = {v for v in user_digits_variants if v}
    if not user_digits_variants:
        return False

    for candidate in allowed_raw:
        candidate_raw = str(candidate or "").strip()
        if candidate_raw == "":
            continue

        candidate_digits_variants: set[str] = {_normalize_phone_digits(candidate_raw)}
        try:
            normalized_candidate = normalize_to_e164(candidate_raw)
            for var in get_phone_number_variations(normalized_candidate):
                candidate_digits_variants.add(_normalize_phone_digits(var))
        except Exception:
            pass

        candidate_digits_variants = {v for v in candidate_digits_variants if v}
        if user_digits_variants.intersection(candidate_digits_variants):
            return True

    return False


def _get_demo_package_ids() -> set[uuid.UUID]:
    if not bool(current_app.config.get("DEMO_MODE_ENABLED", False)):
        return set()
    if not bool(current_app.config.get("DEMO_SHOW_TEST_PACKAGE", False)):
        return set()

    raw = current_app.config.get("DEMO_PACKAGE_IDS") or []
    if not isinstance(raw, list):
        return set()

    result: set[uuid.UUID] = set()
    for item in raw:
        try:
            result.add(uuid.UUID(str(item)))
        except Exception:
            continue
    return result


def _get_primary_debt_order_prefix() -> str:
    if not has_app_context():
        return "DEBT"
    raw = str(current_app.config.get("DEBT_ORDER_ID_PREFIX", "DEBT") or "DEBT").strip()
    raw = raw.upper()

    allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
    cleaned = "".join(ch for ch in raw if ch in allowed)
    cleaned = cleaned.strip("-_")
    cleaned = cleaned[:22].rstrip("-_")
    return cleaned if cleaned else "DEBT"


def _get_legacy_debt_order_prefixes() -> list[str]:
    primary = _get_primary_debt_order_prefix()
    legacy_alnum = "".join(ch for ch in primary if ch.isalnum()).strip()
    prefixes: list[str] = []
    for p in (primary, legacy_alnum):
        p = str(p or "").strip().upper()
        if p and p not in prefixes:
            prefixes.append(p)
    return prefixes


def _get_debt_order_prefixes() -> list[str]:
    derived = _get_legacy_debt_order_prefixes()
    prefixes: list[str] = []
    for p in (*derived, "DEBT"):
        p = str(p or "").strip().upper()
        if p and p not in prefixes:
            prefixes.append(p)
    return prefixes


def _encode_uuid_base32(u: uuid.UUID) -> str:
    return base64.b32encode(u.bytes).decode("ascii").rstrip("=")


def _encode_uuid_base64url(u: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(u.bytes).decode("ascii").rstrip("=")


def _parse_manual_debt_id_core(core: str) -> uuid.UUID:
    raw = str(core or "").strip()
    if raw == "":
        raise ValueError("empty core")

    try:
        return uuid.UUID(raw)
    except Exception:
        pass

    hex_candidate = raw.replace("-", "").strip()
    if len(hex_candidate) == 32:
        try:
            return uuid.UUID(hex=hex_candidate)
        except Exception:
            pass

    b64 = raw.strip()
    if b64:
        try:
            pad_len = (-len(b64)) % 4
            data = base64.urlsafe_b64decode(b64 + ("=" * pad_len))
            if len(data) == 16:
                return uuid.UUID(bytes=data)
        except Exception:
            pass

    b32 = raw.upper()
    pad_len = (-len(b32)) % 8
    b32_padded = b32 + ("=" * pad_len)
    data = base64.b32decode(b32_padded, casefold=True)
    if len(data) != 16:
        raise ValueError("invalid base32 uuid bytes")
    return uuid.UUID(bytes=data)


def _extract_manual_debt_id_from_order_id(order_id: str | None) -> uuid.UUID | None:
    raw = str(order_id or "").strip()
    if "~" not in raw:
        return None
    for p in _get_debt_order_prefixes():
        prefix = f"{p}-"
        if not raw.startswith(prefix):
            continue
        try:
            core = raw[len(prefix) : raw.index("~")]
            parsed = _parse_manual_debt_id_core(core)
            return parsed
        except Exception:
            return None
    return None


def _is_debt_settlement_order_id(order_id: str | None) -> bool:
    raw = str(order_id or "").strip()
    for p in _get_debt_order_prefixes():
        if raw.startswith(f"{p}-"):
            return True
    return False
