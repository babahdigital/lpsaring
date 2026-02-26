# backend/app/infrastructure/http/transactions_routes.py
# VERSI PERBAIKAN FINAL: Menggunakan base URL publik dari konfigurasi dan Celery.

import os
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any

import midtransclient
from flask import Blueprint, current_app, make_response, render_template, request
import requests
from sqlalchemy.orm import selectinload

from app.extensions import db, limiter
from app.infrastructure.db.models import (
    Package,
)
from app.services.notification_service import verify_temp_invoice_token
from app.services.transaction_status_link_service import generate_transaction_status_token
from app.services import settings_service as _settings_service

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
from .transactions.debt_helpers import (
    apply_debt_settlement_on_success as _apply_debt_settlement_on_success,
    estimate_debt_rp_for_mb as _estimate_debt_rp_for_mb,
    estimate_user_debt_rp as _estimate_user_debt_rp,
)
from .transactions.midtrans_helpers import (
    extract_action_url,
    extract_qr_code_url,
    extract_va_number,
    get_midtrans_core_api_client,
    get_midtrans_snap_client,
    is_qr_payment_type as _is_qr_payment_type,
    safe_parse_midtrans_datetime,
)
from .transactions.dependency_builders import TransactionsDependencyBuilders
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

# --- FUNGSI HELPER (Tidak ada perubahan) ---
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


def _deps() -> TransactionsDependencyBuilders:
    return TransactionsDependencyBuilders(
        db=db,
        request=request,
        selectinload=selectinload,
        package_model=Package,
        requests_module=requests,
        render_template=render_template,
        make_response=make_response,
        html_class=HTML,
        weasyprint_available=WEASYPRINT_AVAILABLE,
        midtransclient_module=midtransclient,
        verify_temp_invoice_token=verify_temp_invoice_token,
        should_allow_call=should_allow_call,
        record_success=record_success,
        record_failure=record_failure,
        increment_metric=increment_metric,
        generate_transaction_status_token=generate_transaction_status_token,
        format_to_local_phone=format_to_local_phone,
        format_currency=format_currency,
        send_whatsapp_invoice_task=send_whatsapp_invoice_task,
        is_duplicate_webhook=_is_duplicate_webhook,
        begin_order_effect=_begin_order_effect,
        finish_order_effect=_finish_order_effect,
        log_transaction_event=_log_transaction_event,
        safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
        extract_va_number=extract_va_number,
        extract_qr_code_url=extract_qr_code_url,
        extract_action_url=extract_action_url,
        is_qr_payment_type=_is_qr_payment_type,
        is_debt_settlement_order_id=_is_debt_settlement_order_id,
        extract_manual_debt_id_from_order_id=_extract_manual_debt_id_from_order_id,
        apply_debt_settlement_on_success=_apply_debt_settlement_on_success,
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
        get_debt_order_prefixes=_get_debt_order_prefixes,
        get_primary_debt_order_prefix=_get_primary_debt_order_prefix,
        encode_uuid_base64url=_encode_uuid_base64url,
        encode_uuid_base32=_encode_uuid_base32,
        estimate_debt_rp_for_mb=_estimate_debt_rp_for_mb,
        estimate_user_debt_rp=_estimate_user_debt_rp,
        get_midtrans_snap_client=get_midtrans_snap_client,
        get_midtrans_core_api_client=get_midtrans_core_api_client,
        build_core_api_charge_payload=_build_core_api_charge_payload,
    )


# --- ENDPOINTS ---
@transactions_bp.route("/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    return initiate_transaction_impl(
        current_user_id=current_user_id,
        **_deps().build_initiate_transaction_dependencies(),
    )


@transactions_bp.route("/debt/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_debt_settlement_transaction(current_user_id: uuid.UUID):
    return initiate_debt_settlement_transaction_impl(
        current_user_id=current_user_id,
        **_deps().build_debt_initiate_dependencies(),
    )


@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
    return handle_notification_impl(**_deps().build_notification_dependencies())


@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    return get_transaction_by_order_id_impl(
        current_user_id=current_user_id,
        order_id=order_id,
        **_deps().build_authenticated_detail_dependencies(),
    )


@transactions_bp.route("/public/by-order-id/<string:order_id>", methods=["GET"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_STATUS_RATE_LIMIT", "60 per minute"))
def get_transaction_by_order_id_public(order_id: str):
    return get_transaction_by_order_id_public_impl(
        order_id=order_id,
        **_deps().build_public_detail_dependencies(),
    )


@transactions_bp.route("/public/<string:order_id>/cancel", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT", "20 per minute"))
def cancel_transaction_public(order_id: str):
    return cancel_transaction_public_impl(
        order_id=order_id,
        **_deps().build_public_cancel_dependencies(),
    )


@transactions_bp.route("/public/<string:midtrans_order_id>/qr", methods=["GET"])
@limiter.limit(lambda: current_app.config.get("PUBLIC_TRANSACTION_QR_RATE_LIMIT", "30 per minute"))
def get_transaction_qr_public(midtrans_order_id: str):
    return get_transaction_qr_public_impl(
        midtrans_order_id=midtrans_order_id,
        **_deps().build_qr_public_dependencies(),
    )


@transactions_bp.route("/<string:order_id>/cancel", methods=["POST"])
@token_required
def cancel_transaction(current_user_id: uuid.UUID, order_id: str):
    return cancel_transaction_impl(
        current_user_id=current_user_id,
        order_id=order_id,
        **_deps().build_authenticated_cancel_dependencies(),
    )


@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    return get_transaction_invoice_impl(
        current_user_id=current_user_id,
        midtrans_order_id=midtrans_order_id,
        **_deps().build_invoice_dependencies(),
    )


@transactions_bp.route("/<string:midtrans_order_id>/qr", methods=["GET"])
@token_required
def get_transaction_qr(current_user_id: uuid.UUID, midtrans_order_id: str):
    return get_transaction_qr_impl(
        current_user_id=current_user_id,
        midtrans_order_id=midtrans_order_id,
        **_deps().build_authenticated_qr_dependencies(),
    )


@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
# Tambahkan route baru untuk URL yang diakhiri dengan .pdf
@transactions_bp.route("/invoice/temp/<string:token>.pdf", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    return get_temp_transaction_invoice_impl(
        token=token,
        **_deps().build_temp_invoice_dependencies(),
    )
