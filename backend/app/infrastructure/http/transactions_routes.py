# backend/app/infrastructure/http/transactions_routes.py
# VERSI PERBAIKAN FINAL: Menggunakan base URL publik dari konfigurasi dan Celery.

import hashlib
import json
import os
import uuid
import base64
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Dict, Optional

import midtransclient
from flask import Blueprint, abort, current_app, has_app_context, jsonify, make_response, render_template, request
import requests
import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import HTTPException

from app.extensions import db, limiter
from app.infrastructure.db.models import (
    ApprovalStatus,
    Package,
    Transaction,
    TransactionEvent,
    TransactionEventSource,
    TransactionStatus,
    User,
    UserQuotaDebt,
)
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from app.services.user_management import user_debt as user_debt_service
from app.services.notification_service import (
    generate_temp_invoice_token,
    get_notification_message,
    verify_temp_invoice_token,
)
from app.services import settings_service
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection

# from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf # Tidak lagi dipanggil langsung
from app.utils.formatters import format_to_local_phone
from .decorators import token_required
from app.utils.circuit_breaker import record_failure, record_success, should_allow_call
from app.utils.metrics_utils import increment_metric

# Import Celery task
from app.tasks import send_whatsapp_invoice_task  # Import task Celery Anda

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    WEASYPRINT_AVAILABLE = False

transactions_bp = Blueprint(
    "transactions_api",
    __name__,
    url_prefix="/api/transactions",
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../templates"),
)


def _safe_json_dumps(value: object) -> str | None:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def _log_transaction_event(
    *,
    session,
    transaction: Transaction,
    source: TransactionEventSource,
    event_type: str,
    status: TransactionStatus | None = None,
    payload: object | None = None,
) -> None:
    ev = TransactionEvent()
    ev.id = uuid.uuid4()
    ev.transaction_id = transaction.id
    ev.source = source
    ev.event_type = event_type
    ev.status = status
    ev.payload = _safe_json_dumps(payload) if payload is not None else None
    session.add(ev)


def _is_debt_settlement_order_id(order_id: str | None) -> bool:
    raw = str(order_id or "").strip()
    for p in _get_debt_order_prefixes():
        if raw.startswith(f"{p}-"):
            return True
    return False


def _get_primary_debt_order_prefix() -> str:
    if not has_app_context():
        return "DEBT"
    raw = str(current_app.config.get("DEBT_ORDER_ID_PREFIX", "DEBT") or "DEBT").strip()
    raw = raw.upper()

    # Midtrans limit: transaction_details.order_id <= 50 chars.
    # Manual-debt format:
    #   <prefix>-<manual_debt_id_core>~<suffix>
    # where manual_debt_id_core uses base64url UUID (22 chars) and suffix is 4 chars.
    # Total = len(prefix) + 1 + 22 + 1 + 4 = len(prefix) + 28
    # Therefore keep prefix <= 22 to stay <= 50.
    allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
    cleaned = "".join(ch for ch in raw if ch in allowed)
    cleaned = cleaned.strip("-_")
    cleaned = cleaned[:22].rstrip("-_")
    return cleaned if cleaned else "DEBT"


def _get_legacy_debt_order_prefixes() -> list[str]:
    """Return legacy-compatible prefixes derived from current env.

    Historically, the prefix was sanitized to alphanumeric-only, so values like
    "BD-DBLP" became "BDDBLP". Keep recognizing those older prefixes to ensure
    existing transactions can still be detected/parsed.
    """
    primary = _get_primary_debt_order_prefix()
    legacy_alnum = "".join(ch for ch in primary if ch.isalnum()).strip()
    prefixes: list[str] = []
    for p in (primary, legacy_alnum):
        p = str(p or "").strip().upper()
        if p and p not in prefixes:
            prefixes.append(p)
    return prefixes


def _get_debt_order_prefixes() -> list[str]:
    # Backward compatibility: always recognize legacy "DEBT-".
    derived = _get_legacy_debt_order_prefixes()
    prefixes: list[str] = []
    for p in (*derived, "DEBT"):
        p = str(p or "").strip().upper()
        if p and p not in prefixes:
            prefixes.append(p)
    return prefixes


def _extract_manual_debt_id_from_order_id(order_id: str | None) -> uuid.UUID | None:
    """If order_id is a manual-debt settlement, return the UserQuotaDebt.id.

    Format: <prefix>-<uuid>~<suffix>
    """
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


def _encode_uuid_base32(u: uuid.UUID) -> str:
    # 16 bytes -> 26 chars base32 (no padding). Uses A-Z2-7.
    return base64.b32encode(u.bytes).decode("ascii").rstrip("=")


def _encode_uuid_base64url(u: uuid.UUID) -> str:
    # 16 bytes -> 22 chars base64url (no padding). Uses A-Za-z0-9_-.
    return base64.urlsafe_b64encode(u.bytes).decode("ascii").rstrip("=")


def _parse_manual_debt_id_core(core: str) -> uuid.UUID:
    # Accept legacy formats:
    # - UUID dashed (36 chars)
    # - UUID hex (32 chars)
    # - Base64URL no-padding (22 chars)
    # - Base32 no-padding (26 chars)
    raw = str(core or "").strip()
    if raw == "":
        raise ValueError("empty core")

    # Try standard UUID parsing first (dashed).
    try:
        return uuid.UUID(raw)
    except Exception:
        pass

    # Try 32 hex.
    hex_candidate = raw.replace("-", "").strip()
    if len(hex_candidate) == 32:
        try:
            return uuid.UUID(hex=hex_candidate)
        except Exception:
            pass

    # Try Base64URL (no padding).
    b64 = raw.strip()
    if b64:
        try:
            pad_len = (-len(b64)) % 4
            data = base64.urlsafe_b64decode(b64 + ("=" * pad_len))
            if len(data) == 16:
                return uuid.UUID(bytes=data)
        except Exception:
            pass

    # Try Base32 (no padding).
    # Add '=' padding to multiple of 8.
    b32 = raw.upper()
    pad_len = (-len(b32)) % 8
    b32_padded = b32 + ("=" * pad_len)
    data = base64.b32decode(b32_padded, casefold=True)
    if len(data) != 16:
        raise ValueError("invalid base32 uuid bytes")
    return uuid.UUID(bytes=data)


def _estimate_user_debt_rp(user: User) -> int:
    """Estimate user's total debt value in Rupiah (rounded) based on cheapest active package."""
    try:
        debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
    except Exception:
        debt_total_mb = 0.0
    if debt_total_mb <= 0:
        return 0

    try:
        debt_gb = float(debt_total_mb) / 1024.0

        base_q = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
        )

        ref_pkg = (
            base_q.filter(Package.data_quota_gb >= debt_gb)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .first()
        )
        if ref_pkg is None:
            ref_pkg = base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).first()

        if not ref_pkg or ref_pkg.price is None or ref_pkg.data_quota_gb is None:
            return 0

        from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package

        estimate = estimate_debt_rp_from_cheapest_package(
            debt_mb=float(debt_total_mb),
            cheapest_package_price_rp=int(ref_pkg.price),
            cheapest_package_quota_gb=float(ref_pkg.data_quota_gb),
            cheapest_package_name=str(getattr(ref_pkg, "name", "") or "") or None,
        )
        return int(estimate.estimated_rp_rounded or 0)
    except Exception:
        return 0


def _estimate_debt_rp_for_mb(debt_mb: float) -> int:
    """Estimate debt value in Rupiah (rounded) for a given MB using cheapest active package."""
    try:
        mb = float(debt_mb or 0)
    except Exception:
        mb = 0.0
    if mb <= 0:
        return 0

    try:
        debt_gb = float(mb) / 1024.0

        base_q = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
        )

        ref_pkg = (
            base_q.filter(Package.data_quota_gb >= debt_gb)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .first()
        )
        if ref_pkg is None:
            ref_pkg = base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).first()

        if not ref_pkg or ref_pkg.price is None or ref_pkg.data_quota_gb is None:
            return 0

        from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package

        estimate = estimate_debt_rp_from_cheapest_package(
            debt_mb=float(mb),
            cheapest_package_price_rp=int(ref_pkg.price),
            cheapest_package_quota_gb=float(ref_pkg.data_quota_gb),
            cheapest_package_name=str(getattr(ref_pkg, "name", "") or "") or None,
        )
        return int(estimate.estimated_rp_rounded or 0)
    except Exception:
        return 0


def _apply_debt_settlement_on_success(*, session, transaction: Transaction) -> dict[str, Any]:
    user = getattr(transaction, "user", None)
    if user is None:
        raise ValueError("Transaksi pelunasan tunggakan tidak memiliki user.")

    manual_debt_id = _extract_manual_debt_id_from_order_id(getattr(transaction, "midtrans_order_id", None))

    debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
    if debt_total_mb <= 0:
        return {"paid_auto_mb": 0, "paid_manual_mb": 0, "paid_total_mb": 0, "unblocked": False}

    debt_auto_before = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
    debt_manual_before = int(getattr(user, "quota_debt_manual_mb", 0) or 0)
    was_blocked = bool(getattr(user, "is_blocked", False))
    blocked_reason = str(getattr(user, "blocked_reason", "") or "")

    if manual_debt_id is not None:
        debt_item = (
            session.query(UserQuotaDebt)
            .filter(UserQuotaDebt.id == manual_debt_id)
            .filter(UserQuotaDebt.user_id == user.id)
            .with_for_update()
            .first()
        )
        paid_auto_mb = 0
        paid_manual_mb = int(
            user_debt_service.settle_manual_debt_item_to_zero(
                user=user,
                admin_actor=None,
                debt=debt_item,
                source="user_debt_settlement_payment_manual_item",
            )
        )
    else:
        paid_auto_mb, paid_manual_mb = user_debt_service.clear_all_debts_to_zero(
            user=user,
            admin_actor=None,
            source="user_debt_settlement_payment",
        )

    unblocked = False
    if was_blocked and blocked_reason.startswith("quota_debt_limit|"):
        # Only auto-unblock when all debts are fully cleared.
        if float(getattr(user, "quota_debt_total_mb", 0) or 0) <= 0:
            user.is_blocked = False
            user.blocked_reason = None
            user.blocked_at = None
            user.blocked_by_id = None
            unblocked = True

    session.commit()

    try:
        sync_address_list_for_single_user(user)
    except Exception as e:
        current_app.logger.warning("DEBT: gagal sync Mikrotik untuk user %s: %s", getattr(user, "id", "?"), e)

    return {
        "paid_auto_mb": int(paid_auto_mb),
        "paid_manual_mb": int(paid_manual_mb),
        "paid_total_mb": int(paid_auto_mb) + int(paid_manual_mb),
        "debt_auto_before": float(debt_auto_before),
        "debt_manual_before": int(debt_manual_before),
        "unblocked": bool(unblocked),
    }


# --- FUNGSI HELPER (Tidak ada perubahan) ---
def get_midtrans_core_api_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    client = midtransclient.CoreApi(is_production=is_production, server_key=server_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def get_midtrans_snap_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    client_key = current_app.config.get("MIDTRANS_CLIENT_KEY")
    if not server_key or not client_key:
        raise ValueError("MIDTRANS_SERVER_KEY atau MIDTRANS_CLIENT_KEY configuration is missing.")
    client = midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string:
        return None
    try:
        naive_dt = datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")
        offset_hours = int(current_app.config.get("MIDTRANS_DATETIME_INPUT_OFFSET_HOURS", 7))
        return naive_dt.replace(tzinfo=dt_timezone(timedelta(hours=offset_hours))).astimezone(dt_timezone.utc)
    except (ValueError, TypeError):
        return None


def extract_va_number(response_data: Dict[str, Any]):
    va_numbers = response_data.get("va_numbers")
    if isinstance(va_numbers, list) and len(va_numbers) > 0:
        for va_info in va_numbers:
            if isinstance(va_info, dict) and va_info.get("va_number"):
                return str(va_info.get("va_number")).strip()
    specific_fields = [
        "permata_va_number",
        "bca_va_number",
        "bni_va_number",
        "bri_va_number",
        "cimb_va_number",
        "va_number",
    ]
    for field in specific_fields:
        if field_value := response_data.get(field):
            return str(field_value).strip()
    return None


def extract_qr_code_url(response_data: Dict[str, Any]):
    actions = response_data.get("actions")
    if isinstance(actions, list):
        # Prefer new GoPay Dynamic QRIS URL (generate-qr-code-v2) if present.
        for action in actions:
            action_name = str(action.get("name", "")).lower()
            qr_url = action.get("url")
            if qr_url and "generate-qr-code-v2" in action_name:
                return qr_url
        for action in actions:
            action_name = action.get("name", "").lower()
            qr_url = action.get("url")
            if qr_url and "generate-qr-code" in action_name:
                return qr_url
    return response_data.get("qr_code_url")


def _is_qr_payment_type(payment_type: str | None) -> bool:
    pt = str(payment_type or "").strip().lower()
    return pt in {"qris", "gopay", "shopeepay"}


def extract_action_url(response_data: Dict[str, Any], *, action_name_contains: str) -> str | None:
    needle = str(action_name_contains or "").strip().lower()
    if needle == "":
        return None
    actions = response_data.get("actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = str(action.get("name", "")).strip().lower()
        url = action.get("url")
        if url and needle in name:
            return str(url).strip()
    return None


def _normalize_payment_provider_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"core", "coreapi", "core_api", "core-api", "core api"}:
        return "core_api"
    if raw in {"snap", "snap_ui", "snap-ui", "snap ui"}:
        return "snap"
    return "snap"


def _get_payment_provider_mode() -> str:
    # Default to Snap for backward compatibility.
    raw = (
        settings_service.get_setting("PAYMENT_PROVIDER_MODE", None)
        or current_app.config.get("PAYMENT_PROVIDER_MODE")
        or "snap"
    )
    return _normalize_payment_provider_mode(str(raw))


def _normalize_payment_method(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"qris", "gopay", "va", "shopeepay"}:
        return raw
    return None


def _normalize_va_bank(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"bca", "bni", "bri", "cimb", "mandiri", "permata"}:
        return raw
    return None


_CORE_API_METHOD_ORDER: tuple[str, ...] = ("qris", "gopay", "va", "shopeepay")
_CORE_API_VA_BANK_ORDER: tuple[str, ...] = ("bni", "bca", "bri", "mandiri", "permata", "cimb")


def _parse_csv_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip().lower() for p in text.split(",")]
    return [p for p in parts if p]


def _get_core_api_enabled_payment_methods() -> list[str]:
    # Default to existing behavior (QRIS/GoPay/VA) when setting is missing.
    raw = settings_service.get_setting("CORE_API_ENABLED_PAYMENT_METHODS", None)
    selected = set(_parse_csv_values(raw))
    enabled = [m for m in _CORE_API_METHOD_ORDER if m in selected]
    if enabled:
        return enabled
    return ["qris", "gopay", "va"]


def _get_core_api_enabled_va_banks() -> list[str]:
    raw = settings_service.get_setting("CORE_API_ENABLED_VA_BANKS", None)
    selected = set(_parse_csv_values(raw))
    enabled = [b for b in _CORE_API_VA_BANK_ORDER if b in selected]
    if enabled:
        return enabled
    return list(_CORE_API_VA_BANK_ORDER)


def _is_core_api_method_enabled(method: str, enabled_methods: list[str]) -> bool:
    m = str(method or "").strip().lower()
    return m in set(enabled_methods)


def _is_core_api_va_bank_enabled(bank: str, enabled_banks: list[str]) -> bool:
    b = str(bank or "").strip().lower()
    return b in set(enabled_banks)


def _tx_has_snap_initiation_data(tx: Transaction) -> bool:
    return bool(getattr(tx, "snap_token", None) or getattr(tx, "snap_redirect_url", None))


def _tx_has_core_initiation_data(tx: Transaction) -> bool:
    if getattr(tx, "qr_code_url", None):
        return True
    if getattr(tx, "va_number", None):
        return True
    if getattr(tx, "payment_code", None) and getattr(tx, "biller_code", None):
        return True
    return False


def _tx_matches_requested_core_payment(
    tx: Transaction,
    *,
    requested_method: str | None,
    requested_va_bank: str | None,
) -> bool:
    method = requested_method or "qris"

    tx_pm = str(getattr(tx, "payment_method", "") or "").strip().lower()

    if method in {"qris", "gopay", "shopeepay"}:
        # payment_method should be set on initiation; if not, fall back to stored initiation fields.
        if tx_pm:
            return tx_pm == method
        if method == "qris":
            return bool(getattr(tx, "qr_code_url", None))
        if method == "gopay":
            return bool(getattr(tx, "snap_redirect_url", None) or getattr(tx, "qr_code_url", None))
        if method == "shopeepay":
            return bool(getattr(tx, "snap_redirect_url", None) or getattr(tx, "qr_code_url", None))
        return False

    # method == "va"
    bank = requested_va_bank or "bni"
    if bank == "mandiri":
        if tx_pm:
            return tx_pm == "echannel"
        return bool(getattr(tx, "payment_code", None) and getattr(tx, "biller_code", None))

    if tx_pm:
        return tx_pm == f"{bank}_va"
    return False


def _build_core_api_charge_payload(
    *,
    order_id: str,
    gross_amount: int,
    item_id: str,
    item_name: str,
    customer_name: str,
    customer_phone: str,
    expiry_minutes: int,
    finish_url: str,
    method: str,
    va_bank: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": [{"id": item_id, "price": int(gross_amount), "quantity": 1, "name": item_name[:100]}],
        "customer_details": {
            "first_name": customer_name or "Pengguna",
            "phone": customer_phone,
        },
        "custom_expiry": {"expiry_duration": int(expiry_minutes), "unit": "minute"},
    }

    if method == "qris":
        payload["payment_type"] = "qris"
        payload["qris"] = {"acquirer": "gopay"}
        return payload

    if method == "gopay":
        payload["payment_type"] = "gopay"
        payload["gopay"] = {
            "enable_callback": True,
            "callback_url": str(finish_url),
        }
        return payload

    if method == "shopeepay":
        payload["payment_type"] = "shopeepay"
        # ShopeePay Core API supports callback_url; keep payload minimal.
        payload["shopeepay"] = {
            "callback_url": str(finish_url),
        }
        return payload

    # method == "va"
    bank = va_bank or "bni"
    if bank == "mandiri":
        payload["payment_type"] = "echannel"
        payload["echannel"] = {
            "bill_info1": "Pembayaran Hotspot",
            "bill_info2": item_name[:18] or "Hotspot",
        }
        return payload

    payload["payment_type"] = "bank_transfer"
    payload["bank_transfer"] = {"bank": bank}
    return payload


def _build_webhook_idempotency_key(payload: Dict[str, Any]) -> Optional[str]:
    order_id = payload.get("order_id")
    status_code = payload.get("status_code")
    transaction_status = payload.get("transaction_status")
    transaction_id = payload.get("transaction_id")
    if not order_id or not status_code or not transaction_status:
        return None
    token = transaction_id or "no_trx_id"
    return f"midtrans:webhook:{order_id}:{transaction_status}:{status_code}:{token}"


def _is_duplicate_webhook(payload: Dict[str, Any]) -> bool:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return False
    key = _build_webhook_idempotency_key(payload)
    if not key:
        return False
    try:
        ttl_seconds = int(current_app.config.get("MIDTRANS_WEBHOOK_IDEMPOTENCY_TTL_SECONDS", 86400))
    except Exception:
        ttl_seconds = 86400
    try:
        inserted = redis_client.set(key, "1", ex=ttl_seconds, nx=True)
        return inserted is None
    except Exception:
        return False


# --- JINJA FILTERS (Tidak ada perubahan) ---
def format_datetime_short(value: datetime) -> str:
    if not isinstance(value, datetime):
        return ""
    try:
        app_tz_offset = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))
        local_dt = value.astimezone(app_tz)
        return local_dt.strftime("%d %b %Y, %H:%M WITA")
    except Exception:
        return "Invalid Date"


def format_currency(value: Any) -> str:
    if value is None:
        return "Rp 0"
    try:
        decimal_value = Decimal(value)
        return f"Rp {decimal_value:,.0f}".replace(",", ".")
    except Exception:
        return "Rp Error"


def format_number(value: Any) -> str:
    if value is None:
        return "0"
    try:
        decimal_value = Decimal(value)
        return f"{decimal_value:,.0f}".replace(",", ".")
    except Exception:
        try:
            return str(value)
        except Exception:
            return "0"


def format_status(value: str) -> str:
    if not isinstance(value, str):
        return value
    return value.replace("_", " ").title()


@transactions_bp.app_template_filter("format_datetime_short")
def _format_datetime_short_filter(value):
    return format_datetime_short(value)


@transactions_bp.app_template_filter("format_currency")
def _format_currency_filter(value):
    return format_currency(value)


@transactions_bp.app_template_filter("format_number")
def _format_number_filter(value):
    return format_number(value)


@transactions_bp.app_template_filter("format_status")
def _format_status_filter(value):
    return format_status(value)


# --- Skema Pydantic ---
class _InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID
    payment_method: Optional[str] = None
    va_bank: Optional[str] = None


class _InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = Field(None, alias="snap_token")
    transaction_id: uuid.UUID = Field(..., alias="id")
    order_id: str = Field(..., alias="midtrans_order_id")
    redirect_url: Optional[str] = Field(None, alias="snap_redirect_url")
    payment_method: Optional[str] = Field(None, alias="payment_method")
    midtrans_transaction_id: Optional[str] = Field(None, alias="midtrans_transaction_id")
    expiry_time: Optional[datetime] = Field(None, alias="expiry_time")
    va_number: Optional[str] = Field(None, alias="va_number")
    payment_code: Optional[str] = Field(None, alias="payment_code")
    biller_code: Optional[str] = Field(None, alias="biller_code")
    qr_code_url: Optional[str] = Field(None, alias="qr_code_url")

    model_config = ConfigDict(from_attributes=True)


class _InitiateDebtSettlementResponseSchema(BaseModel):
    snap_token: Optional[str] = Field(None, alias="snap_token")
    transaction_id: uuid.UUID = Field(..., alias="id")
    order_id: str = Field(..., alias="midtrans_order_id")
    redirect_url: Optional[str] = Field(None, alias="snap_redirect_url")
    payment_method: Optional[str] = Field(None, alias="payment_method")
    midtrans_transaction_id: Optional[str] = Field(None, alias="midtrans_transaction_id")
    expiry_time: Optional[datetime] = Field(None, alias="expiry_time")
    va_number: Optional[str] = Field(None, alias="va_number")
    payment_code: Optional[str] = Field(None, alias="payment_code")
    biller_code: Optional[str] = Field(None, alias="biller_code")
    qr_code_url: Optional[str] = Field(None, alias="qr_code_url")

    model_config = ConfigDict(from_attributes=True)


# --- ENDPOINTS ---
@transactions_bp.route("/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    req_data_dict = request.get_json(silent=True) or {}
    try:
        req_data = _InitiateTransactionRequestSchema.model_validate(req_data_dict)
    except ValidationError as e:
        return jsonify(
            {"success": False, "message": "Input tidak valid.", "details": e.errors()}
        ), HTTPStatus.UNPROCESSABLE_ENTITY

    session = db.session
    try:
        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        package = session.query(Package).get(req_data.package_id)
        if not package or not package.is_active:
            abort(HTTPStatus.BAD_REQUEST, description="Paket tidak valid atau tidak aktif.")

        gross_amount = int(package.price or 0)

        provider_mode = _get_payment_provider_mode()
        requested_method = _normalize_payment_method(getattr(req_data, "payment_method", None))
        requested_va_bank = _normalize_va_bank(getattr(req_data, "va_bank", None))

        enabled_core_methods: list[str] = []
        enabled_core_va_banks: list[str] = []
        if provider_mode == "core_api":
            enabled_core_methods = _get_core_api_enabled_payment_methods()
            enabled_core_va_banks = _get_core_api_enabled_va_banks()

            if requested_method is not None and not _is_core_api_method_enabled(requested_method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            if requested_method == "va" and requested_va_bank is not None:
                if not _is_core_api_va_bank_enabled(requested_va_bank, enabled_core_va_banks):
                    abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

        now_utc = datetime.now(dt_timezone.utc)

        # Reuse existing active transaction to avoid creating many expired rows
        # due to repeated clicks/refreshes.
        existing_tx = (
            session.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .filter(Transaction.package_id == package.id)
            .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
            .filter(
                sa.or_(
                    Transaction.expiry_time.is_(None),
                    Transaction.expiry_time > now_utc,
                )
            )
            .order_by(Transaction.created_at.desc())
            .first()
        )
        if existing_tx:
            can_reuse = (
                _tx_has_snap_initiation_data(existing_tx)
                if provider_mode == "snap"
                else _tx_has_core_initiation_data(existing_tx)
            )
            if can_reuse and provider_mode == "core_api":
                # For Core API mode, only reuse if user requested the same payment method/bank.
                if not _tx_matches_requested_core_payment(
                    existing_tx,
                    requested_method=requested_method,
                    requested_va_bank=requested_va_bank,
                ):
                    existing_tx.status = TransactionStatus.CANCELLED
                    _log_transaction_event(
                        session=session,
                        transaction=existing_tx,
                        source=TransactionEventSource.APP,
                        event_type="CANCELLED_BY_NEW_INITIATE",
                        status=existing_tx.status,
                        payload={
                            "order_id": existing_tx.midtrans_order_id,
                            "requested_method": requested_method,
                            "requested_va_bank": requested_va_bank,
                            "reason": "requested_payment_mismatch",
                        },
                    )
                    session.commit()
                    can_reuse = False

            if can_reuse:
                _log_transaction_event(
                    session=session,
                    transaction=existing_tx,
                    source=TransactionEventSource.APP,
                    event_type="INITIATE_REUSED_EXISTING",
                    status=existing_tx.status,
                    payload={
                        "order_id": existing_tx.midtrans_order_id,
                        "package_id": str(existing_tx.package_id),
                        "amount": int(existing_tx.amount or 0),
                        "expiry_time": existing_tx.expiry_time.isoformat() if existing_tx.expiry_time else None,
                        "provider_mode": provider_mode,
                        "snap_token_present": bool(existing_tx.snap_token),
                        "redirect_url": existing_tx.snap_redirect_url,
                        "qr_code_url_present": bool(getattr(existing_tx, "qr_code_url", None)),
                        "va_number_present": bool(getattr(existing_tx, "va_number", None)),
                        "reason": "existing_active_transaction",
                    },
                )
                session.commit()
                response_data = _InitiateTransactionResponseSchema.model_validate(existing_tx, from_attributes=True)
                payload = response_data.model_dump(by_alias=False, exclude_none=True)
                payload["provider_mode"] = provider_mode
                return jsonify(payload), HTTPStatus.OK

        order_prefix = str(current_app.config.get("MIDTRANS_ORDER_ID_PREFIX", "BD-LPSR")).strip()
        order_prefix = order_prefix.strip("-")
        if not order_prefix:
            order_prefix = "BD-LPSR"
        order_id = f"{order_prefix}-{uuid.uuid4().hex[:12].upper()}"

        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        local_expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        # SQLAlchemy model init menerima keyword args, tetapi type-checker (Pylance)
        # tidak mengenali signature dinamis tersebut. Gunakan assignment eksplisit.
        new_transaction = Transaction()
        new_transaction.id = uuid.uuid4()
        new_transaction.user_id = user.id
        new_transaction.package_id = package.id
        new_transaction.midtrans_order_id = order_id
        new_transaction.amount = gross_amount
        new_transaction.status = TransactionStatus.UNKNOWN
        new_transaction.expiry_time = local_expiry_time

        # PERBAIKAN: Gunakan base URL publik jika tersedia, jika tidak fallback ke frontend URL
        # Ini untuk callback finish yang dilihat oleh browser pengguna.
        base_callback_url = (
            current_app.config.get("APP_PUBLIC_BASE_URL")
            or current_app.config.get("FRONTEND_URL")
            or current_app.config.get("APP_LINK_USER")
        )
        if not base_callback_url:
            current_app.logger.error("APP_PUBLIC_BASE_URL/FRONTEND_URL/APP_LINK_USER belum dikonfigurasi.")
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="APP_PUBLIC_BASE_URL belum dikonfigurasi.")
        finish_url_base = f"{base_callback_url.rstrip('/')}/payment/finish"
        # Core API callback_url: keep order_id in query because provider deeplink callbacks may not append params.
        finish_url = f"{finish_url_base}?order_id={order_id}"

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Midtrans sementara tidak tersedia.")

        snap_token: str | None = None
        redirect_url: str | None = None

        if provider_mode == "snap":
            snap_params = {
                "transaction_details": {"order_id": order_id, "gross_amount": gross_amount},
                "item_details": [
                    {"id": str(package.id), "price": gross_amount, "quantity": 1, "name": package.name[:100]}
                ],
                "customer_details": {
                    "first_name": user.full_name or "Pengguna",
                    "phone": format_to_local_phone(user.phone_number),
                },
                # Snap finish redirect biasanya sudah menambahkan order_id sendiri.
                # Jika kita tambahkan order_id juga, bisa jadi query duplicate (?order_id=..&order_id=..).
                "callbacks": {"finish": finish_url_base},
            }

            snap = get_midtrans_snap_client()
            snap_response = snap.create_transaction(snap_params)
            record_success("midtrans")

            snap_token = snap_response.get("token")
            redirect_url = snap_response.get("redirect_url")
            if not snap_token and not redirect_url:
                raise ValueError("Respons Midtrans tidak valid.")

            new_transaction.snap_token = snap_token
            new_transaction.snap_redirect_url = redirect_url
            new_transaction.status = TransactionStatus.UNKNOWN
        else:
            # Core API flow (no Snap UI). Default method is QRIS.
            method = requested_method or (enabled_core_methods[0] if enabled_core_methods else "qris")
            if enabled_core_methods and not _is_core_api_method_enabled(method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            va_bank = requested_va_bank
            if method == "va":
                if enabled_core_va_banks:
                    if va_bank is None:
                        # Prefer BNI when allowed, otherwise first enabled bank.
                        va_bank = "bni" if "bni" in enabled_core_va_banks else enabled_core_va_banks[0]
                    elif not _is_core_api_va_bank_enabled(va_bank, enabled_core_va_banks):
                        abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

            core_api = get_midtrans_core_api_client()
            charge_payload = _build_core_api_charge_payload(
                order_id=order_id,
                gross_amount=gross_amount,
                item_id=str(package.id),
                item_name=str(package.name or "Paket"),
                customer_name=str(user.full_name or "Pengguna"),
                customer_phone=(format_to_local_phone(user.phone_number) or ""),
                expiry_minutes=expiry_minutes,
                finish_url=finish_url,
                method=method,
                va_bank=va_bank,
            )

            charge_response = core_api.charge(charge_payload)
            record_success("midtrans")

            payment_type = str(charge_response.get("payment_type") or "").strip().lower() or None
            midtrans_trx_id = charge_response.get("transaction_id")

            new_transaction.midtrans_transaction_id = str(midtrans_trx_id).strip() if midtrans_trx_id else None
            new_transaction.snap_token = None
            # Reuse snap_redirect_url column to store non-snap deeplink redirect URL (e.g., GoPay app deeplink).
            new_transaction.snap_redirect_url = None

            # Mark as pending so /payment/finish can show instructions.
            new_transaction.status = TransactionStatus.PENDING

            # Normalize payment_method stored for UI display.
            if method == "va":
                bank = va_bank or "bni"
                if bank == "mandiri" or payment_type == "echannel":
                    new_transaction.payment_method = "echannel"
                    bill_key = charge_response.get("bill_key") or charge_response.get("mandiri_bill_key")
                    biller_code = charge_response.get("biller_code")
                    new_transaction.payment_code = str(bill_key).strip() if bill_key else None
                    new_transaction.biller_code = str(biller_code).strip() if biller_code else None
                else:
                    new_transaction.payment_method = f"{bank}_va"
                    new_transaction.va_number = extract_va_number(charge_response)
            else:
                new_transaction.payment_method = payment_type or method

            if method in {"gopay", "shopeepay"}:
                deeplink = extract_action_url(charge_response, action_name_contains="deeplink-redirect")
                if deeplink:
                    new_transaction.snap_redirect_url = deeplink

            if _is_qr_payment_type(payment_type or method):
                new_transaction.qr_code_url = extract_qr_code_url(charge_response)
            else:
                new_transaction.qr_code_url = None

        expiry_time = new_transaction.expiry_time

        _log_transaction_event(
            session=session,
            transaction=new_transaction,
            source=TransactionEventSource.APP,
            event_type="INITIATED",
            status=new_transaction.status,
            payload={
                "order_id": order_id,
                "package_id": str(package.id),
                "amount": gross_amount,
                "expiry_time": expiry_time.isoformat() if expiry_time is not None else None,
                "provider_mode": provider_mode,
                "requested_method": requested_method,
                "requested_va_bank": requested_va_bank,
                "snap_token_present": bool(snap_token),
                "redirect_url": redirect_url,
                "finish_url": finish_url,
                "qr_code_url_present": bool(getattr(new_transaction, "qr_code_url", None)),
                "va_number_present": bool(getattr(new_transaction, "va_number", None)),
            },
        )

        session.add(new_transaction)
        session.commit()

        response_data = _InitiateTransactionResponseSchema.model_validate(new_transaction, from_attributes=True)
        payload = response_data.model_dump(by_alias=False, exclude_none=True)
        payload["provider_mode"] = provider_mode
        return jsonify(payload), HTTPStatus.OK

    except HTTPException:
        # Preserve intended HTTP status codes from abort()/werkzeug.
        raise
    except Exception as e:
        record_failure("midtrans")
        db.session.rollback()
        current_app.logger.error(f"Error di initiate_transaction: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
    finally:
        db.session.remove()


@transactions_bp.route("/debt/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_debt_settlement_transaction(current_user_id: uuid.UUID):
    """Initiate Midtrans Snap payment to settle user's quota debt."""
    session = db.session
    try:
        req_data = request.get_json(silent=True) or {}
        manual_debt_id_raw = req_data.get("manual_debt_id")
        manual_debt_id: uuid.UUID | None = None
        if manual_debt_id_raw is not None:
            try:
                manual_debt_id = uuid.UUID(str(manual_debt_id_raw))
            except Exception:
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="manual_debt_id tidak valid.")

        provider_mode = _get_payment_provider_mode()
        requested_method = _normalize_payment_method(req_data.get("payment_method"))
        requested_va_bank = _normalize_va_bank(req_data.get("va_bank"))

        enabled_core_methods: list[str] = []
        enabled_core_va_banks: list[str] = []
        if provider_mode == "core_api":
            enabled_core_methods = _get_core_api_enabled_payment_methods()
            enabled_core_va_banks = _get_core_api_enabled_va_banks()

            if requested_method is not None and not _is_core_api_method_enabled(requested_method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            if requested_method == "va" and requested_va_bank is not None:
                if not _is_core_api_va_bank_enabled(requested_va_bank, enabled_core_va_banks):
                    abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        if bool(getattr(user, "is_unlimited_user", False)):
            abort(HTTPStatus.BAD_REQUEST, description="Pengguna unlimited tidak memiliki tunggakan kuota.")

        debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
        if debt_total_mb <= 0:
            abort(HTTPStatus.BAD_REQUEST, description="Tidak ada tunggakan kuota untuk dilunasi.")

        manual_item = None
        manual_item_remaining_mb = 0.0
        if manual_debt_id is not None:
            manual_item = (
                session.query(UserQuotaDebt)
                .filter(UserQuotaDebt.id == manual_debt_id)
                .filter(UserQuotaDebt.user_id == user.id)
                .first()
            )
            if manual_item is None:
                abort(HTTPStatus.NOT_FOUND, description="Hutang manual tidak ditemukan.")
            try:
                amount = int(getattr(manual_item, "amount_mb", 0) or 0)
                paid = int(getattr(manual_item, "paid_mb", 0) or 0)
            except Exception:
                amount = 0
                paid = 0
            manual_item_remaining_mb = float(max(0, amount - paid))
            if manual_item_remaining_mb <= 0:
                abort(HTTPStatus.BAD_REQUEST, description="Hutang manual tersebut sudah lunas.")

        gross_amount = int(
            (
                _estimate_debt_rp_for_mb(manual_item_remaining_mb)
                if manual_debt_id is not None
                else _estimate_user_debt_rp(user)
            )
            or 0
        )
        if gross_amount <= 0:
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                description="Estimasi tunggakan belum tersedia. Silakan hubungi admin atau coba lagi nanti.",
            )

        now_utc = datetime.now(dt_timezone.utc)
        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        local_expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        debt_prefixes = _get_debt_order_prefixes()
        debt_like_filters = [Transaction.midtrans_order_id.like(f"{p}-%") for p in debt_prefixes]

        existing_tx_query = (
            session.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .filter(sa.or_(*debt_like_filters))
            .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
            .filter(sa.or_(Transaction.expiry_time.is_(None), Transaction.expiry_time > now_utc))
            .order_by(Transaction.created_at.desc())
        )

        if manual_debt_id is not None:
            manual_uuid = str(manual_debt_id)
            manual_hex = str(getattr(manual_debt_id, "hex", "") or "").upper()
            manual_b64 = _encode_uuid_base64url(manual_debt_id)
            manual_b32 = _encode_uuid_base32(manual_debt_id)
            manual_like_filters: list[sa.ColumnElement[bool]] = []
            for p in debt_prefixes:
                manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_uuid}%"))
                if manual_hex:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_hex}%"))
                if manual_b64:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_b64}%"))
                if manual_b32:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_b32}%"))
            existing_tx_query = existing_tx_query.filter(sa.or_(*manual_like_filters))

        existing_tx = existing_tx_query.first()
        if existing_tx:
            can_reuse = (
                _tx_has_snap_initiation_data(existing_tx)
                if provider_mode == "snap"
                else _tx_has_core_initiation_data(existing_tx)
            )
            if can_reuse:
                response_data = _InitiateDebtSettlementResponseSchema.model_validate(existing_tx, from_attributes=True)
                payload = response_data.model_dump(by_alias=False, exclude_none=True)
                payload["provider_mode"] = provider_mode
                return jsonify(payload), HTTPStatus.OK

        debt_prefix = _get_primary_debt_order_prefix()
        if manual_debt_id is not None:
            manual_core = _encode_uuid_base64url(manual_debt_id)
            order_id = f"{debt_prefix}-{manual_core}~{uuid.uuid4().hex[:4].upper()}"
        else:
            order_id = f"{debt_prefix}-{uuid.uuid4().hex[:12].upper()}"

        new_transaction = Transaction()
        new_transaction.id = uuid.uuid4()
        new_transaction.user_id = user.id
        new_transaction.package_id = None
        new_transaction.midtrans_order_id = order_id
        new_transaction.amount = int(gross_amount)
        new_transaction.status = TransactionStatus.UNKNOWN
        new_transaction.expiry_time = local_expiry_time

        base_callback_url = (
            current_app.config.get("APP_PUBLIC_BASE_URL")
            or current_app.config.get("FRONTEND_URL")
            or current_app.config.get("APP_LINK_USER")
        )
        if not base_callback_url:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="APP_PUBLIC_BASE_URL belum dikonfigurasi.")
        finish_url_base = f"{base_callback_url.rstrip('/')}/payment/finish"
        finish_url = f"{finish_url_base}?order_id={order_id}&purpose=debt"

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Midtrans sementara tidak tersedia.")

        item_name = "Pelunasan Tunggakan Kuota" if manual_debt_id is None else "Pelunasan Hutang Manual"

        snap_token: str | None = None
        redirect_url: str | None = None

        if provider_mode == "snap":
            snap_params = {
                "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
                "item_details": [
                    {
                        "id": "DEBT_SETTLEMENT",
                        "price": int(gross_amount),
                        "quantity": 1,
                        "name": item_name[:100],
                    }
                ],
                "customer_details": {
                    "first_name": user.full_name or "Pengguna",
                    "phone": format_to_local_phone(user.phone_number),
                },
                "callbacks": {"finish": finish_url_base},
            }

            snap = get_midtrans_snap_client()
            snap_response = snap.create_transaction(snap_params)
            record_success("midtrans")

            snap_token = snap_response.get("token")
            redirect_url = snap_response.get("redirect_url")
            if not snap_token and not redirect_url:
                raise ValueError("Respons Midtrans tidak valid.")

            new_transaction.snap_token = snap_token
            new_transaction.snap_redirect_url = redirect_url
            new_transaction.status = TransactionStatus.UNKNOWN
        else:
            method = requested_method or (enabled_core_methods[0] if enabled_core_methods else "qris")
            if enabled_core_methods and not _is_core_api_method_enabled(method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            va_bank = requested_va_bank
            if method == "va":
                if enabled_core_va_banks:
                    if va_bank is None:
                        va_bank = "bni" if "bni" in enabled_core_va_banks else enabled_core_va_banks[0]
                    elif not _is_core_api_va_bank_enabled(va_bank, enabled_core_va_banks):
                        abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

            core_api = get_midtrans_core_api_client()
            charge_payload = _build_core_api_charge_payload(
                order_id=order_id,
                gross_amount=int(gross_amount),
                item_id="DEBT_SETTLEMENT",
                item_name=item_name,
                customer_name=str(user.full_name or "Pengguna"),
                customer_phone=(format_to_local_phone(user.phone_number) or ""),
                expiry_minutes=expiry_minutes,
                finish_url=finish_url,
                method=method,
                va_bank=va_bank,
            )
            charge_response = core_api.charge(charge_payload)
            record_success("midtrans")

            payment_type = str(charge_response.get("payment_type") or "").strip().lower() or None
            midtrans_trx_id = charge_response.get("transaction_id")
            new_transaction.midtrans_transaction_id = str(midtrans_trx_id).strip() if midtrans_trx_id else None
            new_transaction.snap_token = None
            # Reuse snap_redirect_url column to store non-snap deeplink redirect URL (e.g., GoPay app deeplink).
            new_transaction.snap_redirect_url = None
            new_transaction.status = TransactionStatus.PENDING

            if method == "va":
                bank = va_bank or "bni"
                if bank == "mandiri" or payment_type == "echannel":
                    new_transaction.payment_method = "echannel"
                    bill_key = charge_response.get("bill_key") or charge_response.get("mandiri_bill_key")
                    biller_code = charge_response.get("biller_code")
                    new_transaction.payment_code = str(bill_key).strip() if bill_key else None
                    new_transaction.biller_code = str(biller_code).strip() if biller_code else None
                else:
                    new_transaction.payment_method = f"{bank}_va"
                    new_transaction.va_number = extract_va_number(charge_response)
            else:
                new_transaction.payment_method = payment_type or method

            if method in {"gopay", "shopeepay"}:
                deeplink = extract_action_url(charge_response, action_name_contains="deeplink-redirect")
                if deeplink:
                    new_transaction.snap_redirect_url = deeplink

            if _is_qr_payment_type(payment_type or method):
                new_transaction.qr_code_url = extract_qr_code_url(charge_response)
            else:
                new_transaction.qr_code_url = None

        expiry_time = new_transaction.expiry_time

        _log_transaction_event(
            session=session,
            transaction=new_transaction,
            source=TransactionEventSource.APP,
            event_type="DEBT_INITIATED",
            status=new_transaction.status,
            payload={
                "order_id": order_id,
                "amount": int(gross_amount),
                "debt_total_mb": float(debt_total_mb),
                "expiry_time": expiry_time.isoformat() if expiry_time is not None else None,
                "provider_mode": provider_mode,
                "requested_method": requested_method,
                "requested_va_bank": requested_va_bank,
                "snap_token_present": bool(snap_token),
                "redirect_url": redirect_url,
                "finish_url": finish_url,
                "qr_code_url_present": bool(getattr(new_transaction, "qr_code_url", None)),
                "va_number_present": bool(getattr(new_transaction, "va_number", None)),
            },
        )

        session.add(new_transaction)
        session.commit()

        response_data = _InitiateDebtSettlementResponseSchema.model_validate(new_transaction, from_attributes=True)
        payload = response_data.model_dump(by_alias=False, exclude_none=True)
        payload["provider_mode"] = provider_mode
        return jsonify(payload), HTTPStatus.OK
    except HTTPException:
        raise
    except Exception as e:
        record_failure("midtrans")
        session.rollback()
        current_app.logger.error("Error di initiate_debt_settlement_transaction: %s", e, exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
    finally:
        db.session.remove()


@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
    notification_payload = request.get_json(silent=True) or {}
    order_id = notification_payload.get("order_id")
    current_app.logger.info(
        f"WEBHOOK: Diterima untuk Order ID: {order_id}, Status Midtrans: {notification_payload.get('transaction_status')}"
    )

    if not all(
        [
            order_id,
            notification_payload.get("transaction_status"),
            notification_payload.get("status_code"),
            notification_payload.get("gross_amount"),
        ]
    ):
        return jsonify({"status": "ok", "message": "Payload tidak lengkap"}), HTTPStatus.OK

    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    gross_amount_str = notification_payload.get("gross_amount", "0")
    gross_amount_str_for_hash = gross_amount_str if "." in gross_amount_str else gross_amount_str + ".00"
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()
    if calculated_signature != notification_payload.get("signature_key") and current_app.config.get(
        "MIDTRANS_IS_PRODUCTION", False
    ):
        return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN

    if _is_duplicate_webhook(notification_payload):
        increment_metric("payment.webhook.duplicate")
        return jsonify({"status": "ok", "message": "Duplicate notification"}), HTTPStatus.OK

    session = db.session
    try:
        transaction = (
            session.query(Transaction)
            .options(selectinload(Transaction.user), selectinload(Transaction.package))
            .filter(Transaction.midtrans_order_id == order_id)
            .with_for_update()
            .first()
        )

        if not transaction or transaction.status == TransactionStatus.SUCCESS:
            return jsonify({"status": "ok"}), HTTPStatus.OK

        # Simpan payload mentah agar admin bisa audit lengkap seperti data contoh.
        try:
            transaction.midtrans_notification_payload = json.dumps(notification_payload, ensure_ascii=False)
        except Exception:
            transaction.midtrans_notification_payload = None

        midtrans_status_raw = notification_payload.get("transaction_status")
        midtrans_status = str(midtrans_status_raw).strip().lower() if isinstance(midtrans_status_raw, str) else ""
        fraud_status_raw = notification_payload.get("fraud_status")
        fraud_status = str(fraud_status_raw).strip().lower() if isinstance(fraud_status_raw, str) else None
        # settlement umumnya final sukses; capture butuh fraud accept (untuk kartu) namun bisa None untuk metode lain.
        payment_success = False
        if midtrans_status == "settlement":
            payment_success = True
        elif midtrans_status == "capture":
            payment_success = fraud_status in (None, "accept")

        status_map: dict[str, TransactionStatus] = {
            "capture": TransactionStatus.SUCCESS,
            "settlement": TransactionStatus.SUCCESS,
            "pending": TransactionStatus.PENDING,
            "deny": TransactionStatus.FAILED,
            "expire": TransactionStatus.EXPIRED,
            "cancel": TransactionStatus.CANCELLED,
        }
        new_status = status_map.get(midtrans_status, transaction.status)
        if transaction.status == new_status and transaction.midtrans_transaction_id:
            return jsonify({"status": "ok"}), HTTPStatus.OK

        transaction.status = new_status

        _log_transaction_event(
            session=session,
            transaction=transaction,
            source=TransactionEventSource.MIDTRANS_WEBHOOK,
            event_type="NOTIFICATION",
            status=transaction.status,
            payload=notification_payload,
        )
        if notification_payload.get("transaction_id"):
            transaction.midtrans_transaction_id = notification_payload.get("transaction_id")

        # Enrich kolom transaksi dari payload (baik pending maupun final) agar tabel admin lengkap.
        if notification_payload.get("payment_type") and not transaction.payment_method:
            transaction.payment_method = notification_payload.get("payment_type")

        if parsed_expiry := safe_parse_midtrans_datetime(notification_payload.get("expiry_time")):
            transaction.expiry_time = parsed_expiry

        # Informasi pembayaran yang bisa dipakai di finish page.
        transaction.va_number = extract_va_number(notification_payload) or transaction.va_number

        bill_key = notification_payload.get("bill_key") or notification_payload.get("mandiri_bill_key")
        biller_code = notification_payload.get("biller_code")
        payment_code = notification_payload.get("payment_code")

        if bill_key and not transaction.payment_code:
            transaction.payment_code = bill_key
        if payment_code and not transaction.payment_code:
            transaction.payment_code = payment_code
        if biller_code and not transaction.biller_code:
            transaction.biller_code = biller_code

        if _is_qr_payment_type(notification_payload.get("payment_type")):
            transaction.qr_code_url = extract_qr_code_url(notification_payload) or transaction.qr_code_url

        if payment_success:
            # set payment time jika tersedia
            transaction.payment_time = (
                safe_parse_midtrans_datetime(notification_payload.get("settlement_time"))
                or safe_parse_midtrans_datetime(notification_payload.get("transaction_time"))
                or transaction.payment_time
            )

        if payment_success:
            # Special flow: user debt settlement (DEBT-*)
            if _is_debt_settlement_order_id(order_id):
                try:
                    result = _apply_debt_settlement_on_success(session=session, transaction=transaction)
                    _log_transaction_event(
                        session=session,
                        transaction=transaction,
                        source=TransactionEventSource.APP,
                        event_type="DEBT_SETTLED",
                        status=transaction.status,
                        payload=result,
                    )
                    session.commit()
                    current_app.logger.info(
                        "WEBHOOK: DEBT settlement %s berhasil. paid_total_mb=%s unblocked=%s",
                        order_id,
                        result.get("paid_total_mb"),
                        result.get("unblocked"),
                    )
                    increment_metric("payment.success")
                except Exception as e:
                    session.rollback()
                    current_app.logger.error("WEBHOOK: gagal settle DEBT %s: %s", order_id, e, exc_info=True)
                    increment_metric("payment.failed")
                    abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal memproses pelunasan tunggakan.")
            else:
                with get_mikrotik_connection() as mikrotik_api:
                    is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                    if is_success:
                        _log_transaction_event(
                            session=session,
                            transaction=transaction,
                            source=TransactionEventSource.APP,
                            event_type="MIKROTIK_APPLY_SUCCESS",
                            status=transaction.status,
                            payload={"message": message},
                        )
                        session.commit()  # Commit transaksi DULU
                        current_app.logger.info(f"WEBHOOK: Transaksi {order_id} BERHASIL di-commit. Pesan: {message}")
                        increment_metric("payment.success")
                        try:
                            user = transaction.user
                            package = transaction.package
                            if user is None or package is None:
                                current_app.logger.error(
                                    "WEBHOOK: transaksi %s sukses tetapi user/package tidak ter-load. Skip WA invoice.",
                                    order_id,
                                )
                                return jsonify({"status": "ok"}), HTTPStatus.OK
                            temp_token = generate_temp_invoice_token(str(transaction.id))

                            base_url = (
                                settings_service.get_setting("APP_PUBLIC_BASE_URL")
                                or settings_service.get_setting("FRONTEND_URL")
                                or settings_service.get_setting("APP_LINK_USER")
                                or request.url_root
                            )
                            if not base_url:
                                current_app.logger.error(
                                    "APP_PUBLIC_BASE_URL tidak diatur dan request.url_root kosong. Tidak dapat membuat URL invoice untuk WhatsApp."
                                )
                                raise ValueError("Konfigurasi alamat publik aplikasi tidak ditemukan.")

                            # --- PERUBAHAN KRUSIAL DI SINI: Tambahkan .pdf ke URL ---
                            # Ini akan membuat URL yang berakhir dengan .pdf, membantu Fonnte mengidentifikasi formatnya.
                            temp_invoice_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"
                            # --- AKHIR PERUBAHAN ---

                            msg_context = {
                                "full_name": user.full_name,
                                "order_id": transaction.midtrans_order_id,
                                "package_name": package.name,
                                "package_price": format_currency(package.price),
                            }
                            caption_message = get_notification_message("purchase_success_with_invoice", msg_context)
                            filename = f"invoice-{transaction.midtrans_order_id}.pdf"

                            current_app.logger.info(f"Mencoba mengirim WA dengan PDF dari URL: {temp_invoice_url}")

                            request_id = request.environ.get("FLASK_REQUEST_ID", "")
                            send_whatsapp_invoice_task.delay(
                                str(user.phone_number),
                                caption_message,
                                temp_invoice_url,
                                filename,
                                request_id,
                            )
                            current_app.logger.info(
                                f"Task pengiriman WhatsApp invoice untuk {order_id} dikirim ke Celery."
                            )

                        except Exception as e_notif:
                            current_app.logger.error(
                                f"WEBHOOK: Gagal kirim notif WhatsApp {order_id}: {e_notif}", exc_info=True
                            )
                    else:
                        session.rollback()  # Rollback jika Mikrotik gagal
                        try:
                            transaction_after = (
                                session.query(Transaction)
                                .filter(Transaction.midtrans_order_id == order_id)
                                .with_for_update()
                                .first()
                            )
                            if transaction_after is not None:
                                _log_transaction_event(
                                    session=session,
                                    transaction=transaction_after,
                                    source=TransactionEventSource.APP,
                                    event_type="MIKROTIK_APPLY_FAILED",
                                    status=transaction_after.status,
                                    payload={"message": message, "midtrans_status": midtrans_status},
                                )
                                session.commit()
                        except Exception:
                            session.rollback()
                        current_app.logger.error(
                            f"WEBHOOK: Gagal apply paket ke Mikrotik untuk {order_id}. Rollback transaksi."
                        )
                        increment_metric("payment.failed")
        else:
            session.commit()  # Commit status transaksi yang berubah (pending, deny, expire, cancel)
            current_app.logger.info(f"WEBHOOK: Status transaksi {order_id} diupdate ke {transaction.status.value}.")
            if transaction.status in [TransactionStatus.FAILED, TransactionStatus.CANCELLED, TransactionStatus.EXPIRED]:
                increment_metric("payment.failed")

        return jsonify({"status": "ok"}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"WEBHOOK Error {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        db.session.remove()


@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    session = db.session
    try:
        transaction = (
            session.query(Transaction)
            .filter(Transaction.midtrans_order_id == order_id)
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.package).selectinload(Package.profile),
            )
            .first()
        )
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan melihat transaksi ini.")

        if transaction.status in (TransactionStatus.PENDING, TransactionStatus.UNKNOWN):
            try:
                prev_status = transaction.status
                # Throttle Midtrans status checks to avoid spamming Core API during frontend polling.
                redis_client = getattr(current_app, "redis_client_otp", None)
                if redis_client is not None:
                    try:
                        ttl_seconds = int(current_app.config.get("MIDTRANS_STATUS_CHECK_THROTTLE_SECONDS", 8))
                    except Exception:
                        ttl_seconds = 8
                    ttl_seconds = max(3, min(ttl_seconds, 60))
                    throttle_key = f"midtrans:statuscheck:{order_id}"
                    try:
                        inserted = redis_client.set(throttle_key, "1", ex=ttl_seconds, nx=True)
                        if inserted is None:
                            # Skip calling Midtrans; return current DB state.
                            raise StopIteration
                    except StopIteration:
                        raise
                    except Exception:
                        # If Redis fails, continue without throttle.
                        pass

                if not should_allow_call("midtrans"):
                    abort(HTTPStatus.SERVICE_UNAVAILABLE, "Midtrans sementara tidak tersedia.")

                core_api = get_midtrans_core_api_client()
                midtrans_status_response = core_api.transactions.status(order_id)
                record_success("midtrans")

                # Log Midtrans status check only when we actually call Core API (throttled above).
                _log_transaction_event(
                    session=session,
                    transaction=transaction,
                    source=TransactionEventSource.MIDTRANS_STATUS,
                    event_type="STATUS_CHECK",
                    status=transaction.status,
                    payload=midtrans_status_response,
                )
                midtrans_trx_status_raw = midtrans_status_response.get("transaction_status")
                midtrans_trx_status = (
                    str(midtrans_trx_status_raw).strip().lower() if isinstance(midtrans_trx_status_raw, str) else ""
                )
                fraud_status_raw = midtrans_status_response.get("fraud_status")
                fraud_status = str(fraud_status_raw).strip().lower() if isinstance(fraud_status_raw, str) else None
                payment_success = False
                if midtrans_trx_status == "settlement":
                    payment_success = True
                elif midtrans_trx_status == "capture":
                    payment_success = fraud_status in (None, "accept")

                try:
                    transaction.midtrans_notification_payload = json.dumps(midtrans_status_response, ensure_ascii=False)
                except Exception:
                    pass

                if midtrans_status_response.get("payment_type") and not transaction.payment_method:
                    transaction.payment_method = midtrans_status_response.get("payment_type")
                if parsed_expiry := safe_parse_midtrans_datetime(midtrans_status_response.get("expiry_time")):
                    transaction.expiry_time = parsed_expiry
                transaction.va_number = extract_va_number(midtrans_status_response) or transaction.va_number
                if _is_qr_payment_type(midtrans_status_response.get("payment_type")):
                    transaction.qr_code_url = extract_qr_code_url(midtrans_status_response) or transaction.qr_code_url

                # Echannel (Mandiri Bill Payment) info can exist while still pending.
                bill_key = midtrans_status_response.get("bill_key") or midtrans_status_response.get("mandiri_bill_key")
                biller_code = midtrans_status_response.get("biller_code")
                payment_code = midtrans_status_response.get("payment_code")

                if bill_key and not transaction.payment_code:
                    transaction.payment_code = bill_key
                if payment_code and not transaction.payment_code:
                    transaction.payment_code = payment_code
                if biller_code and not transaction.biller_code:
                    transaction.biller_code = biller_code

                if payment_success:
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.midtrans_transaction_id = midtrans_status_response.get("transaction_id")
                    transaction.payment_time = safe_parse_midtrans_datetime(
                        midtrans_status_response.get("settlement_time")
                    ) or datetime.now(dt_timezone.utc)
                    transaction.payment_code = midtrans_status_response.get("payment_code") or transaction.payment_code
                    transaction.biller_code = midtrans_status_response.get("biller_code") or transaction.biller_code

                    with get_mikrotik_connection() as mikrotik_api:
                        if not mikrotik_api:
                            abort(HTTPStatus.SERVICE_UNAVAILABLE, "Gagal koneksi ke sistem hotspot untuk sinkronisasi.")
                        is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                        if is_success:
                            _log_transaction_event(
                                session=session,
                                transaction=transaction,
                                source=TransactionEventSource.APP,
                                event_type="MIKROTIK_APPLY_SUCCESS",
                                status=transaction.status,
                                payload={"message": message},
                            )
                            session.commit()
                        else:
                            session.rollback()
                            try:
                                transaction_after = (
                                    session.query(Transaction)
                                    .filter(Transaction.midtrans_order_id == order_id)
                                    .with_for_update()
                                    .first()
                                )
                                if transaction_after is not None:
                                    _log_transaction_event(
                                        session=session,
                                        transaction=transaction_after,
                                        source=TransactionEventSource.APP,
                                        event_type="MIKROTIK_APPLY_FAILED",
                                        status=transaction_after.status,
                                        payload={"message": message},
                                    )
                                    session.commit()
                            except Exception:
                                session.rollback()
                            abort(HTTPStatus.INTERNAL_SERVER_ERROR, f"Gagal menerapkan paket: {message}")
                else:
                    status_map: dict[str, TransactionStatus] = {
                        "deny": TransactionStatus.FAILED,
                        "expire": TransactionStatus.EXPIRED,
                        "cancel": TransactionStatus.CANCELLED,
                    }
                    if new_status := status_map.get(midtrans_trx_status):
                        if transaction.status != new_status:
                            transaction.status = new_status
                            session.commit()

                if prev_status != transaction.status:
                    _log_transaction_event(
                        session=session,
                        transaction=transaction,
                        source=TransactionEventSource.APP,
                        event_type="STATUS_CHANGED",
                        status=transaction.status,
                        payload={"from": prev_status.value, "to": transaction.status.value},
                    )
                    session.commit()
            except midtransclient.error_midtrans.MidtransAPIError as midtrans_err:
                record_failure("midtrans")
                current_app.logger.warning(
                    f"GET Detail: Gagal cek status Midtrans untuk PENDING {order_id}: {midtrans_err.message}"
                )
            except StopIteration:
                pass
            except Exception as e_check_status:
                record_failure("midtrans")
                current_app.logger.error(
                    f"GET Detail: Error tak terduga saat cek status Midtrans untuk PENDING {order_id}: {e_check_status}"
                )

        session.refresh(transaction)
        p = transaction.package
        u = transaction.user

        is_debt_settlement = _is_debt_settlement_order_id(transaction.midtrans_order_id)
        manual_debt_id = (
            _extract_manual_debt_id_from_order_id(transaction.midtrans_order_id) if is_debt_settlement else None
        )

        debt_type: str | None = None
        debt_mb: int | None = None
        debt_note: str | None = None
        if is_debt_settlement:
            if manual_debt_id is not None:
                debt_type = "manual"
                try:
                    debt_row = session.get(UserQuotaDebt, manual_debt_id)
                except Exception:
                    debt_row = None
                if debt_row is not None:
                    try:
                        debt_mb = int(max(0, int(debt_row.amount_mb or 0) - int(debt_row.paid_mb or 0)))
                    except Exception:
                        debt_mb = None
                    try:
                        debt_note = str(debt_row.note or "").strip() or None
                    except Exception:
                        debt_note = None
            else:
                debt_type = "auto"
                try:
                    debt_mb_float = float(getattr(u, "quota_debt_auto_mb", 0.0) or 0.0) if u is not None else 0.0
                    debt_mb = int(round(max(0.0, debt_mb_float)))
                except Exception:
                    debt_mb = None

        response_data = {
            "id": str(transaction.id),
            "midtrans_order_id": transaction.midtrans_order_id,
            "midtrans_transaction_id": transaction.midtrans_transaction_id,
            "status": transaction.status.value,
            "purpose": "debt" if is_debt_settlement else "purchase",
            "debt_type": debt_type,
            "debt_mb": debt_mb,
            "debt_note": debt_note,
            "amount": float(transaction.amount or 0.0),
            "payment_method": transaction.payment_method,
            "snap_token": transaction.snap_token if getattr(transaction, "snap_token", None) else None,
            "snap_redirect_url": (
                transaction.snap_redirect_url if getattr(transaction, "snap_token", None) else None
            ),
            "deeplink_redirect_url": (
                transaction.snap_redirect_url
                if (transaction.snap_token is None and transaction.snap_redirect_url)
                else None
            ),
            "payment_time": transaction.payment_time.isoformat() if transaction.payment_time else None,
            "expiry_time": transaction.expiry_time.isoformat() if transaction.expiry_time else None,
            "va_number": transaction.va_number,
            "payment_code": transaction.payment_code,
            "biller_code": getattr(transaction, "biller_code", None),
            "qr_code_url": transaction.qr_code_url,
            "hotspot_password": transaction.hotspot_password,
            "package": {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "price": float(p.price or 0.0),
                "data_quota_gb": float(p.data_quota_gb or 0.0),
                "is_unlimited": (p.data_quota_gb == 0),
            }
            if p
            else None,
            "user": {
                "id": str(u.id),
                "phone_number": u.phone_number,
                "full_name": u.full_name,
                "quota_expiry_date": u.quota_expiry_date.isoformat() if u.quota_expiry_date else None,
                "is_unlimited_user": u.is_unlimited_user,
            }
            if u
            else None,
        }
        response = jsonify(response_data)
        response.headers["Cache-Control"] = "no-store"
        return response, HTTPStatus.OK
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Kesalahan tak terduga saat mengambil detail transaksi: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        if session:
            session.remove()


@transactions_bp.route("/<string:order_id>/cancel", methods=["POST"])
@token_required
def cancel_transaction(current_user_id: uuid.UUID, order_id: str):
    session = db.session
    try:
        transaction = (
            session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).with_for_update().first()
        )
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan membatalkan transaksi ini.")

        if transaction.status == TransactionStatus.SUCCESS:
            return jsonify(
                {"success": False, "message": "Transaksi sudah sukses dan tidak bisa dibatalkan."}
            ), HTTPStatus.BAD_REQUEST

        if transaction.status in (TransactionStatus.UNKNOWN, TransactionStatus.PENDING):
            transaction.status = TransactionStatus.CANCELLED
            _log_transaction_event(
                session=session,
                transaction=transaction,
                source=TransactionEventSource.APP,
                event_type="CANCELLED_BY_USER",
                status=transaction.status,
                payload={"order_id": order_id},
            )
            session.commit()
        return jsonify({"success": True, "status": transaction.status.value}), HTTPStatus.OK
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Gagal membatalkan transaksi {order_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal membatalkan transaksi.")
    finally:
        session.remove()


@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    if not WEASYPRINT_AVAILABLE:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")
    assert HTML is not None
    session = db.session
    try:
        transaction = (
            session.query(Transaction)
            .options(selectinload(Transaction.user), selectinload(Transaction.package))
            .filter(Transaction.midtrans_order_id == midtrans_order_id)
            .first()
        )
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, "Transaksi tidak ditemukan.")
        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, "Anda tidak diizinkan mengakses invoice ini.")
        if transaction.status != TransactionStatus.SUCCESS:
            abort(HTTPStatus.BAD_REQUEST, "Invoice hanya tersedia untuk transaksi yang sudah sukses.")

        if transaction.user is None:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Data pengguna transaksi tidak tersedia.")

        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        user_kamar_display = getattr(transaction.user, "kamar", None)
        if user_kamar_display and user_kamar_display.startswith("Kamar_"):
            user_kamar_display = user_kamar_display.replace("Kamar_", "")
        context = {
            "transaction": transaction,
            "user": transaction.user,
            "package": transaction.package,
            "user_kamar_value": user_kamar_display,
            "business_name": current_app.config.get("BUSINESS_NAME", "Nama Bisnis Anda"),
            "business_address": current_app.config.get("BUSINESS_ADDRESS", "Alamat Bisnis Anda"),
            "business_phone": current_app.config.get("BUSINESS_PHONE", "Telepon Bisnis Anda"),
            "business_email": current_app.config.get("BUSINESS_EMAIL", "Email Bisnis Anda"),
            "invoice_date_local": datetime.now(app_tz),
        }

        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("invoice_template.html", **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()

        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
        return response
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Error saat membuat invoice PDF untuk {midtrans_order_id}: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session:
            session.remove()


@transactions_bp.route("/<string:midtrans_order_id>/qr", methods=["GET"])
@token_required
def get_transaction_qr(current_user_id: uuid.UUID, midtrans_order_id: str):
    session = db.session
    try:
        transaction = session.query(Transaction).filter(Transaction.midtrans_order_id == midtrans_order_id).first()
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, "Transaksi tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, "Anda tidak diizinkan mengakses QR ini.")

        qr_url = str(getattr(transaction, "qr_code_url", "") or "").strip()
        if not qr_url:
            abort(HTTPStatus.NOT_FOUND, "QR Code tidak tersedia untuk transaksi ini.")

        timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
        upstream = requests.get(qr_url, timeout=timeout_seconds)
        if upstream.status_code >= 400:
            abort(HTTPStatus.BAD_GATEWAY, "Gagal mengambil QR Code dari provider pembayaran.")

        content_type = upstream.headers.get("Content-Type") or "application/octet-stream"
        ext = ""
        if "png" in content_type:
            ext = ".png"
        elif "svg" in content_type:
            ext = ".svg"
        elif "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"

        response = make_response(upstream.content)
        response.headers["Content-Type"] = content_type
        download = str(request.args.get("download", "")).strip().lower() in {"1", "true", "yes"}
        disposition = "attachment" if download else "inline"
        response.headers["Content-Disposition"] = f'{disposition}; filename="{midtrans_order_id}-qr{ext}"'
        response.headers["Cache-Control"] = "no-store"
        return response
    except HTTPException:
        raise
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Error saat mengambil QR untuk {midtrans_order_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        session.remove()


@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
# Tambahkan route baru untuk URL yang diakhiri dengan .pdf
@transactions_bp.route("/invoice/temp/<string:token>.pdf", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    if not WEASYPRINT_AVAILABLE or HTML is None:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    transaction_id = verify_temp_invoice_token(token, max_age_seconds=3600)
    if not transaction_id:
        abort(HTTPStatus.FORBIDDEN, description="Akses tidak valid atau link telah kedaluwarsa.")

    session = db.session
    try:
        transaction = (
            session.query(Transaction)
            .options(selectinload(Transaction.user), selectinload(Transaction.package))
            .filter(Transaction.id == uuid.UUID(transaction_id))
            .first()
        )

        if not transaction or transaction.status != TransactionStatus.SUCCESS:
            abort(HTTPStatus.NOT_FOUND, "Invoice tidak ditemukan atau transaksi belum berhasil.")

        if transaction.user is None:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Data pengguna transaksi tidak tersedia.")

        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        kamar_value = getattr(transaction.user, "kamar", None)
        user_kamar_display = kamar_value.replace("Kamar_", "") if isinstance(kamar_value, str) and kamar_value else ""
        context = {
            "transaction": transaction,
            "user": transaction.user,
            "package": transaction.package,
            "user_kamar_value": user_kamar_display,
            "business_name": current_app.config.get("BUSINESS_NAME", "Nama Bisnis Anda"),
            "business_address": current_app.config.get("BUSINESS_ADDRESS", "Alamat Bisnis Anda"),
            "business_phone": current_app.config.get("BUSINESS_PHONE", "Telepon Bisnis Anda"),
            "business_email": current_app.config.get("BUSINESS_EMAIL", "Email Bisnis Anda"),
            "invoice_date_local": datetime.now(app_tz),
        }

        # PERBAIKAN: Gunakan base URL publik untuk merender PDF agar path aset (jika ada) benar
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("invoice_template.html", **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{transaction.midtrans_order_id}.pdf"'

        return response
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat membuat invoice sementara PDF: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan tak terduga saat membuat invoice.")
    finally:
        db.session.remove()
