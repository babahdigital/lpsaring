# backend/app/infrastructure/http/transactions_routes.py
# VERSI PERBAIKAN FINAL: Menggunakan base URL publik dari konfigurasi dan Celery.

import os
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import midtransclient
from flask import Blueprint, current_app, make_response, render_template, request
import requests
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import selectinload

from app.extensions import db, limiter
from app.infrastructure.db.models import (
    Package,
    Transaction,
    User,
    UserQuotaDebt,
)
from app.services.user_management import user_debt as user_debt_service
from app.services.notification_service import verify_temp_invoice_token
from app.services.transaction_status_link_service import generate_transaction_status_token
from app.services import settings_service as _settings_service
from app.services.hotspot_sync_service import sync_address_list_for_single_user

# from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf # Tidak lagi dipanggil langsung
from app.utils.formatters import format_to_local_phone
from .decorators import token_required
from .transactions.helpers import (
    _encode_uuid_base32,
    _encode_uuid_base64url,
    _extract_manual_debt_id_from_order_id,
    _get_demo_package_ids,
    _get_debt_order_prefixes,
    _get_primary_debt_order_prefix,
    _is_debt_settlement_order_id,
    _is_demo_user_eligible,
)
from .transactions.events import log_transaction_event as _log_transaction_event
from .transactions.idempotency import is_duplicate_webhook as _is_duplicate_webhook
from .transactions.idempotency import begin_order_effect as _begin_order_effect
from .transactions.idempotency import finish_order_effect as _finish_order_effect
from .transactions.midtrans_payloads import build_core_api_charge_payload as _build_core_api_charge_payload
from .transactions.payment_policy import (
    get_core_api_enabled_payment_methods as _get_core_api_enabled_payment_methods,
    get_core_api_enabled_va_banks as _get_core_api_enabled_va_banks,
    get_payment_provider_mode as _get_payment_provider_mode,
    is_core_api_method_enabled as _is_core_api_method_enabled,
    is_core_api_va_bank_enabled as _is_core_api_va_bank_enabled,
    normalize_payment_method as _normalize_payment_method,
    normalize_va_bank as _normalize_va_bank,
    tx_has_core_initiation_data as _tx_has_core_initiation_data,
    tx_has_snap_initiation_data as _tx_has_snap_initiation_data,
    tx_matches_requested_core_payment as _tx_matches_requested_core_payment,
)
from .transactions.initiation_routes import (
    initiate_debt_settlement_transaction_impl,
    initiate_transaction_impl,
)
from .transactions.public_routes import (
    cancel_transaction_public_impl,
    get_transaction_by_order_id_public_impl,
    get_transaction_qr_public_impl,
)
from .transactions.authenticated_routes import (
    cancel_transaction_impl,
    get_transaction_by_order_id_impl,
    get_transaction_qr_impl,
)
from .transactions.invoice_routes import (
    get_temp_transaction_invoice_impl,
    get_transaction_invoice_impl,
)
from .transactions.webhook_routes import handle_notification_impl
from app.utils.circuit_breaker import record_failure, record_success, should_allow_call
from app.utils.metrics_utils import increment_metric

# Import Celery task
from app.tasks import send_whatsapp_invoice_task  # Import task Celery Anda

settings_service = _settings_service

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
    if was_blocked and (
        blocked_reason.startswith("quota_debt_limit|") or blocked_reason.startswith("quota_debt_end_of_month|")
    ):
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
    return initiate_transaction_impl(
        current_user_id=current_user_id,
        db=db,
        get_demo_package_ids=_get_demo_package_ids,
        is_demo_user_eligible=_is_demo_user_eligible,
        get_payment_provider_mode=_get_payment_provider_mode,
        normalize_payment_method=_normalize_payment_method,
        normalize_va_bank=_normalize_va_bank,
        get_core_api_enabled_payment_methods=_get_core_api_enabled_payment_methods,
        get_core_api_enabled_va_banks=_get_core_api_enabled_va_banks,
        is_core_api_method_enabled=_is_core_api_method_enabled,
        is_core_api_va_bank_enabled=_is_core_api_va_bank_enabled,
        tx_has_snap_initiation_data=_tx_has_snap_initiation_data,
        tx_has_core_initiation_data=_tx_has_core_initiation_data,
        tx_matches_requested_core_payment=_tx_matches_requested_core_payment,
        log_transaction_event=_log_transaction_event,
        generate_transaction_status_token=generate_transaction_status_token,
        should_allow_call=should_allow_call,
        get_midtrans_snap_client=get_midtrans_snap_client,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        build_core_api_charge_payload=_build_core_api_charge_payload,
        is_qr_payment_type=_is_qr_payment_type,
        extract_qr_code_url=extract_qr_code_url,
        extract_va_number=extract_va_number,
        extract_action_url=extract_action_url,
        record_success=record_success,
        record_failure=record_failure,
        format_to_local_phone=format_to_local_phone,
    )


@transactions_bp.route("/debt/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_debt_settlement_transaction(current_user_id: uuid.UUID):
    return initiate_debt_settlement_transaction_impl(
        current_user_id=current_user_id,
        db=db,
        log_transaction_event=_log_transaction_event,
        get_payment_provider_mode=_get_payment_provider_mode,
        normalize_payment_method=_normalize_payment_method,
        normalize_va_bank=_normalize_va_bank,
        get_core_api_enabled_payment_methods=_get_core_api_enabled_payment_methods,
        get_core_api_enabled_va_banks=_get_core_api_enabled_va_banks,
        is_core_api_method_enabled=_is_core_api_method_enabled,
        is_core_api_va_bank_enabled=_is_core_api_va_bank_enabled,
        estimate_debt_rp_for_mb=_estimate_debt_rp_for_mb,
        estimate_user_debt_rp=_estimate_user_debt_rp,
        get_debt_order_prefixes=_get_debt_order_prefixes,
        encode_uuid_base64url=_encode_uuid_base64url,
        encode_uuid_base32=_encode_uuid_base32,
        tx_has_snap_initiation_data=_tx_has_snap_initiation_data,
        tx_has_core_initiation_data=_tx_has_core_initiation_data,
        get_primary_debt_order_prefix=_get_primary_debt_order_prefix,
        generate_transaction_status_token=generate_transaction_status_token,
        should_allow_call=should_allow_call,
        get_midtrans_snap_client=get_midtrans_snap_client,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        build_core_api_charge_payload=_build_core_api_charge_payload,
        extract_va_number=extract_va_number,
        extract_action_url=extract_action_url,
        is_qr_payment_type=_is_qr_payment_type,
        extract_qr_code_url=extract_qr_code_url,
        record_success=record_success,
        record_failure=record_failure,
        format_to_local_phone=format_to_local_phone,
    )


@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
    return handle_notification_impl(
        db=db,
        is_duplicate_webhook=_is_duplicate_webhook,
        increment_metric=increment_metric,
        log_transaction_event=_log_transaction_event,
        safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
        extract_va_number=extract_va_number,
        extract_qr_code_url=extract_qr_code_url,
        is_qr_payment_type=_is_qr_payment_type,
        is_debt_settlement_order_id=_is_debt_settlement_order_id,
        apply_debt_settlement_on_success=_apply_debt_settlement_on_success,
        send_whatsapp_invoice_task=send_whatsapp_invoice_task,
        format_currency_fn=format_currency,
        begin_order_effect=_begin_order_effect,
        finish_order_effect=_finish_order_effect,
    )


@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    return get_transaction_by_order_id_impl(
        current_user_id=current_user_id,
        order_id=order_id,
        db=db,
        session=db.session,
        selectinload=selectinload,
        Package=Package,
        should_allow_call=should_allow_call,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        record_success=record_success,
        record_failure=record_failure,
        log_transaction_event=_log_transaction_event,
        safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
        extract_va_number=extract_va_number,
        is_qr_payment_type=_is_qr_payment_type,
        extract_qr_code_url=extract_qr_code_url,
        is_debt_settlement_order_id=_is_debt_settlement_order_id,
        extract_manual_debt_id_from_order_id=_extract_manual_debt_id_from_order_id,
        begin_order_effect=_begin_order_effect,
        finish_order_effect=_finish_order_effect,
    )


@transactions_bp.route("/public/by-order-id/<string:order_id>", methods=["GET"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_STATUS_RATE_LIMIT", "60 per minute"))
def get_transaction_by_order_id_public(order_id: str):
    return get_transaction_by_order_id_public_impl(
        order_id=order_id,
        db=db,
        request=request,
        should_allow_call=should_allow_call,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        record_success=record_success,
        record_failure=record_failure,
        log_transaction_event=_log_transaction_event,
        safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
        extract_va_number=extract_va_number,
        extract_qr_code_url=extract_qr_code_url,
        is_qr_payment_type=_is_qr_payment_type,
        is_debt_settlement_order_id=_is_debt_settlement_order_id,
        extract_manual_debt_id_from_order_id=_extract_manual_debt_id_from_order_id,
        begin_order_effect=_begin_order_effect,
        finish_order_effect=_finish_order_effect,
    )


@transactions_bp.route("/public/<string:order_id>/cancel", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT", "20 per minute"))
def cancel_transaction_public(order_id: str):
    return cancel_transaction_public_impl(
        order_id=order_id,
        db=db,
        request=request,
        log_transaction_event=_log_transaction_event,
    )


@transactions_bp.route("/public/<string:midtrans_order_id>/qr", methods=["GET"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_QR_RATE_LIMIT", "30 per minute"))
def get_transaction_qr_public(midtrans_order_id: str):
    return get_transaction_qr_public_impl(
        midtrans_order_id=midtrans_order_id,
        db=db,
        request=request,
        requests_module=requests,
    )


@transactions_bp.route("/<string:order_id>/cancel", methods=["POST"])
@token_required
def cancel_transaction(current_user_id: uuid.UUID, order_id: str):
    return cancel_transaction_impl(
        current_user_id=current_user_id,
        order_id=order_id,
        session=db.session,
        log_transaction_event=_log_transaction_event,
    )


@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    return get_transaction_invoice_impl(
        current_user_id=current_user_id,
        midtrans_order_id=midtrans_order_id,
        session=db.session,
        selectinload=selectinload,
        render_template=render_template,
        request=request,
        make_response=make_response,
        html_class=HTML,
        weasyprint_available=WEASYPRINT_AVAILABLE,
        midtransclient_module=midtransclient,
    )


@transactions_bp.route("/<string:midtrans_order_id>/qr", methods=["GET"])
@token_required
def get_transaction_qr(current_user_id: uuid.UUID, midtrans_order_id: str):
    return get_transaction_qr_impl(
        current_user_id=current_user_id,
        midtrans_order_id=midtrans_order_id,
        session=db.session,
        request=request,
        requests_module=requests,
    )


@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
# Tambahkan route baru untuk URL yang diakhiri dengan .pdf
@transactions_bp.route("/invoice/temp/<string:token>.pdf", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    return get_temp_transaction_invoice_impl(
        token=token,
        session=db.session,
        verify_temp_invoice_token=verify_temp_invoice_token,
        render_template=render_template,
        request=request,
        make_response=make_response,
        html_class=HTML,
        weasyprint_available=WEASYPRINT_AVAILABLE,
    )
