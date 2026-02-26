from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TransactionsDependencyBuilders:
    db: Any
    request: Any
    selectinload: Any
    package_model: Any
    requests_module: Any
    render_template: Any
    make_response: Any
    html_class: Any
    weasyprint_available: bool
    midtransclient_module: Any
    verify_temp_invoice_token: Any
    should_allow_call: Any
    record_success: Any
    record_failure: Any
    increment_metric: Any
    generate_transaction_status_token: Any
    format_to_local_phone: Any
    format_currency: Any
    send_whatsapp_invoice_task: Any
    is_duplicate_webhook: Any
    begin_order_effect: Any
    finish_order_effect: Any
    log_transaction_event: Any
    safe_parse_midtrans_datetime: Any
    extract_va_number: Any
    extract_qr_code_url: Any
    extract_action_url: Any
    is_qr_payment_type: Any
    is_debt_settlement_order_id: Any
    extract_manual_debt_id_from_order_id: Any
    apply_debt_settlement_on_success: Any
    get_demo_package_ids: Any
    is_demo_user_eligible: Any
    get_payment_provider_mode: Any
    normalize_payment_method: Any
    normalize_va_bank: Any
    get_core_api_enabled_payment_methods: Any
    get_core_api_enabled_va_banks: Any
    is_core_api_method_enabled: Any
    is_core_api_va_bank_enabled: Any
    tx_has_snap_initiation_data: Any
    tx_has_core_initiation_data: Any
    tx_matches_requested_core_payment: Any
    get_debt_order_prefixes: Any
    get_primary_debt_order_prefix: Any
    encode_uuid_base64url: Any
    encode_uuid_base32: Any
    estimate_debt_rp_for_mb: Any
    estimate_user_debt_rp: Any
    get_midtrans_snap_client: Any
    get_midtrans_core_api_client: Any
    build_core_api_charge_payload: Any

    def build_initiate_transaction_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "get_demo_package_ids": self.get_demo_package_ids,
            "is_demo_user_eligible": self.is_demo_user_eligible,
            "get_payment_provider_mode": self.get_payment_provider_mode,
            "normalize_payment_method": self.normalize_payment_method,
            "normalize_va_bank": self.normalize_va_bank,
            "get_core_api_enabled_payment_methods": self.get_core_api_enabled_payment_methods,
            "get_core_api_enabled_va_banks": self.get_core_api_enabled_va_banks,
            "is_core_api_method_enabled": self.is_core_api_method_enabled,
            "is_core_api_va_bank_enabled": self.is_core_api_va_bank_enabled,
            "tx_has_snap_initiation_data": self.tx_has_snap_initiation_data,
            "tx_has_core_initiation_data": self.tx_has_core_initiation_data,
            "tx_matches_requested_core_payment": self.tx_matches_requested_core_payment,
            "log_transaction_event": self.log_transaction_event,
            "generate_transaction_status_token": self.generate_transaction_status_token,
            "should_allow_call": self.should_allow_call,
            "get_midtrans_snap_client": self.get_midtrans_snap_client,
            "get_midtrans_core_api_client": self.get_midtrans_core_api_client,
            "build_core_api_charge_payload": self.build_core_api_charge_payload,
            "is_qr_payment_type": self.is_qr_payment_type,
            "extract_qr_code_url": self.extract_qr_code_url,
            "extract_va_number": self.extract_va_number,
            "extract_action_url": self.extract_action_url,
            "record_success": self.record_success,
            "record_failure": self.record_failure,
            "format_to_local_phone": self.format_to_local_phone,
        }

    def build_debt_initiate_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "log_transaction_event": self.log_transaction_event,
            "get_payment_provider_mode": self.get_payment_provider_mode,
            "normalize_payment_method": self.normalize_payment_method,
            "normalize_va_bank": self.normalize_va_bank,
            "get_core_api_enabled_payment_methods": self.get_core_api_enabled_payment_methods,
            "get_core_api_enabled_va_banks": self.get_core_api_enabled_va_banks,
            "is_core_api_method_enabled": self.is_core_api_method_enabled,
            "is_core_api_va_bank_enabled": self.is_core_api_va_bank_enabled,
            "estimate_debt_rp_for_mb": self.estimate_debt_rp_for_mb,
            "estimate_user_debt_rp": self.estimate_user_debt_rp,
            "get_debt_order_prefixes": self.get_debt_order_prefixes,
            "encode_uuid_base64url": self.encode_uuid_base64url,
            "encode_uuid_base32": self.encode_uuid_base32,
            "tx_has_snap_initiation_data": self.tx_has_snap_initiation_data,
            "tx_has_core_initiation_data": self.tx_has_core_initiation_data,
            "get_primary_debt_order_prefix": self.get_primary_debt_order_prefix,
            "generate_transaction_status_token": self.generate_transaction_status_token,
            "should_allow_call": self.should_allow_call,
            "get_midtrans_snap_client": self.get_midtrans_snap_client,
            "get_midtrans_core_api_client": self.get_midtrans_core_api_client,
            "build_core_api_charge_payload": self.build_core_api_charge_payload,
            "extract_va_number": self.extract_va_number,
            "extract_action_url": self.extract_action_url,
            "is_qr_payment_type": self.is_qr_payment_type,
            "extract_qr_code_url": self.extract_qr_code_url,
            "record_success": self.record_success,
            "record_failure": self.record_failure,
            "format_to_local_phone": self.format_to_local_phone,
        }

    def build_notification_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "is_duplicate_webhook": self.is_duplicate_webhook,
            "increment_metric": self.increment_metric,
            "log_transaction_event": self.log_transaction_event,
            "safe_parse_midtrans_datetime": self.safe_parse_midtrans_datetime,
            "extract_va_number": self.extract_va_number,
            "extract_qr_code_url": self.extract_qr_code_url,
            "is_qr_payment_type": self.is_qr_payment_type,
            "is_debt_settlement_order_id": self.is_debt_settlement_order_id,
            "apply_debt_settlement_on_success": self.apply_debt_settlement_on_success,
            "send_whatsapp_invoice_task": self.send_whatsapp_invoice_task,
            "format_currency_fn": self.format_currency,
            "begin_order_effect": self.begin_order_effect,
            "finish_order_effect": self.finish_order_effect,
        }

    def build_authenticated_detail_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "session": self.db.session,
            "selectinload": self.selectinload,
            "Package": self.package_model,
            "should_allow_call": self.should_allow_call,
            "get_midtrans_core_api_client": self.get_midtrans_core_api_client,
            "record_success": self.record_success,
            "record_failure": self.record_failure,
            "log_transaction_event": self.log_transaction_event,
            "safe_parse_midtrans_datetime": self.safe_parse_midtrans_datetime,
            "extract_va_number": self.extract_va_number,
            "is_qr_payment_type": self.is_qr_payment_type,
            "extract_qr_code_url": self.extract_qr_code_url,
            "is_debt_settlement_order_id": self.is_debt_settlement_order_id,
            "extract_manual_debt_id_from_order_id": self.extract_manual_debt_id_from_order_id,
            "begin_order_effect": self.begin_order_effect,
            "finish_order_effect": self.finish_order_effect,
        }

    def build_public_detail_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "request": self.request,
            "should_allow_call": self.should_allow_call,
            "get_midtrans_core_api_client": self.get_midtrans_core_api_client,
            "record_success": self.record_success,
            "record_failure": self.record_failure,
            "log_transaction_event": self.log_transaction_event,
            "safe_parse_midtrans_datetime": self.safe_parse_midtrans_datetime,
            "extract_va_number": self.extract_va_number,
            "extract_qr_code_url": self.extract_qr_code_url,
            "is_qr_payment_type": self.is_qr_payment_type,
            "is_debt_settlement_order_id": self.is_debt_settlement_order_id,
            "extract_manual_debt_id_from_order_id": self.extract_manual_debt_id_from_order_id,
            "begin_order_effect": self.begin_order_effect,
            "finish_order_effect": self.finish_order_effect,
        }

    def build_public_cancel_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "request": self.request,
            "log_transaction_event": self.log_transaction_event,
        }

    def build_qr_public_dependencies(self) -> dict[str, Any]:
        return {
            "db": self.db,
            "request": self.request,
            "requests_module": self.requests_module,
        }

    def build_authenticated_cancel_dependencies(self) -> dict[str, Any]:
        return {
            "session": self.db.session,
            "log_transaction_event": self.log_transaction_event,
        }

    def build_invoice_dependencies(self) -> dict[str, Any]:
        return {
            "session": self.db.session,
            "selectinload": self.selectinload,
            "render_template": self.render_template,
            "request": self.request,
            "make_response": self.make_response,
            "html_class": self.html_class,
            "weasyprint_available": self.weasyprint_available,
            "midtransclient_module": self.midtransclient_module,
        }

    def build_authenticated_qr_dependencies(self) -> dict[str, Any]:
        return {
            "session": self.db.session,
            "request": self.request,
            "requests_module": self.requests_module,
        }

    def build_temp_invoice_dependencies(self) -> dict[str, Any]:
        return {
            "session": self.db.session,
            "verify_temp_invoice_token": self.verify_temp_invoice_token,
            "render_template": self.render_template,
            "request": self.request,
            "make_response": self.make_response,
            "html_class": self.html_class,
            "weasyprint_available": self.weasyprint_available,
        }
