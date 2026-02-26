from __future__ import annotations

import json
from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Any

import midtransclient
from flask import abort, current_app, has_request_context, request

from app.infrastructure.db.models import Transaction, TransactionEventSource, TransactionStatus
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from .helpers import _is_demo_user_eligible


def _log_tx(route_label: str, level: str, message: str, **context: Any) -> None:
    payload = {
        "route": route_label,
        "order_id": context.get("order_id"),
        "user_id": context.get("user_id"),
        "event": context.get("event"),
        "status_before": context.get("status_before"),
        "status_after": context.get("status_after"),
        "request_id": context.get("request_id"),
    }
    if level == "warning":
        current_app.logger.warning("%s | tx_ctx=%s", message, payload)
        return
    if level == "error":
        current_app.logger.error("%s | tx_ctx=%s", message, payload)
        return
    current_app.logger.info("%s | tx_ctx=%s", message, payload)


def _get_request_id() -> str:
    if not has_request_context():
        return ""
    try:
        req_id = request.headers.get("X-Request-ID")
        if req_id:
            return str(req_id)
    except Exception:
        pass
    try:
        return str((request.environ or {}).get("FLASK_REQUEST_ID", "") or "")
    except Exception:
        return ""


def reconcile_pending_transaction(
    *,
    transaction: Transaction,
    session,
    order_id: str,
    route_label: str,
    should_allow_call,
    get_midtrans_core_api_client,
    record_success,
    record_failure,
    log_transaction_event,
    safe_parse_midtrans_datetime,
    extract_va_number,
    is_qr_payment_type,
    extract_qr_code_url,
    begin_order_effect,
    finish_order_effect,
) -> None:
    if transaction.status not in (TransactionStatus.PENDING, TransactionStatus.UNKNOWN):
        return

    try:
        prev_status = transaction.status
        request_id = _get_request_id()

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
                    raise StopIteration
            except StopIteration:
                raise
            except Exception:
                pass

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, "Midtrans sementara tidak tersedia.")

        core_api = get_midtrans_core_api_client()
        midtrans_status_response = core_api.transactions.status(order_id)
        record_success("midtrans")

        log_transaction_event(
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
        if is_qr_payment_type(midtrans_status_response.get("payment_type")):
            transaction.qr_code_url = extract_qr_code_url(midtrans_status_response) or transaction.qr_code_url

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

            if _is_demo_user_eligible(getattr(transaction, "user", None)):
                log_transaction_event(
                    session=session,
                    transaction=transaction,
                    source=TransactionEventSource.APP,
                    event_type="DEMO_PAYMENT_ONLY_SKIP_MIKROTIK",
                    status=transaction.status,
                    payload={"message": "Demo payment-only: skip MikroTik sync."},
                )
                session.commit()
                _log_tx(
                    route_label,
                    "info",
                    "Demo payment-only transaction committed without MikroTik sync",
                    order_id=order_id,
                    event="demo_skip_mikrotik",
                    user_id=str(getattr(transaction, "user_id", "") or ""),
                    status_before=prev_status.value,
                    status_after=transaction.status.value,
                    request_id=request_id,
                )
                return

            should_apply, effect_lock_key = begin_order_effect(
                order_id=order_id,
                effect_name="hotspot_apply",
                session=session,
            )
            if not should_apply:
                _log_tx(
                    route_label,
                    "info",
                    "Skip duplicate hotspot apply side-effect",
                    order_id=order_id,
                    event="hotspot_apply_skip",
                    user_id=str(getattr(transaction, "user_id", "") or ""),
                    status_before=prev_status.value,
                    status_after=transaction.status.value,
                    request_id=request_id,
                )
                session.commit()
            else:
                with get_mikrotik_connection() as mikrotik_api:
                    if not mikrotik_api:
                        finish_order_effect(
                            order_id=order_id,
                            lock_key=effect_lock_key,
                            success=False,
                            effect_name="hotspot_apply",
                        )
                        abort(HTTPStatus.SERVICE_UNAVAILABLE, "Gagal koneksi ke sistem hotspot untuk sinkronisasi.")

                    is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                    if is_success:
                        log_transaction_event(
                            session=session,
                            transaction=transaction,
                            source=TransactionEventSource.APP,
                            event_type="MIKROTIK_APPLY_SUCCESS",
                            status=transaction.status,
                            payload={"message": message},
                        )
                        session.commit()
                        finish_order_effect(
                            order_id=order_id,
                            lock_key=effect_lock_key,
                            success=True,
                            effect_name="hotspot_apply",
                        )
                    else:
                        finish_order_effect(
                            order_id=order_id,
                            lock_key=effect_lock_key,
                            success=False,
                            effect_name="hotspot_apply",
                        )
                        session.rollback()
                        try:
                            transaction_after = (
                                session.query(Transaction)
                                .filter(Transaction.midtrans_order_id == order_id)
                                .with_for_update()
                                .first()
                            )
                            if transaction_after is not None:
                                log_transaction_event(
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
            log_transaction_event(
                session=session,
                transaction=transaction,
                source=TransactionEventSource.APP,
                event_type="STATUS_CHANGED",
                status=transaction.status,
                payload={"from": prev_status.value, "to": transaction.status.value},
            )
            session.commit()
            _log_tx(
                route_label,
                "info",
                "Transaction status updated from reconcile",
                order_id=order_id,
                event="status_changed",
                user_id=str(getattr(transaction, "user_id", "") or ""),
                status_before=prev_status.value,
                status_after=transaction.status.value,
                request_id=request_id,
            )
    except midtransclient.error_midtrans.MidtransAPIError as midtrans_err:
        record_failure("midtrans")
        _log_tx(
            route_label,
            "warning",
            f"Midtrans status check failed: {midtrans_err.message}",
            order_id=order_id,
            user_id=str(getattr(transaction, "user_id", "") or ""),
            event="midtrans_status_error",
            status_before=transaction.status.value,
            status_after=transaction.status.value,
            request_id=_get_request_id(),
        )
    except StopIteration:
        return
    except Exception as e_check_status:
        record_failure("midtrans")
        _log_tx(
            route_label,
            "error",
            f"Unexpected error while reconcile transaction: {e_check_status}",
            order_id=order_id,
            user_id=str(getattr(transaction, "user_id", "") or ""),
            event="reconcile_unexpected_error",
            status_before=transaction.status.value,
            status_after=transaction.status.value,
            request_id=_get_request_id(),
        )
