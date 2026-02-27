import hashlib
import json
from http import HTTPStatus

from flask import current_app, jsonify, request
from sqlalchemy.orm import selectinload

from app.infrastructure.db.models import Transaction, TransactionEventSource, TransactionStatus
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services import settings_service
from app.services.notification_service import generate_temp_invoice_token, get_notification_message
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from app.services.transaction_status_link_service import generate_transaction_status_token
from .helpers import _is_demo_user_eligible


def handle_notification_impl(
    *,
    db,
    is_duplicate_webhook,
    increment_metric,
    log_transaction_event,
    safe_parse_midtrans_datetime,
    extract_va_number,
    extract_qr_code_url,
    is_qr_payment_type,
    is_debt_settlement_order_id,
    apply_debt_settlement_on_success,
    send_whatsapp_invoice_task,
    format_currency_fn,
    begin_order_effect,
    finish_order_effect,
):
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
    require_signature_validation_cfg = current_app.config.get("MIDTRANS_REQUIRE_SIGNATURE_VALIDATION")
    if isinstance(require_signature_validation_cfg, bool):
        require_signature_validation = require_signature_validation_cfg
    else:
        flask_env = str(current_app.config.get("FLASK_ENV", "") or "").strip().lower()
        require_signature_validation = flask_env == "production" or bool(
            current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
        )

    signature_key = notification_payload.get("signature_key")
    gross_amount_str = notification_payload.get("gross_amount", "0")
    gross_amount_str_for_hash = gross_amount_str if "." in gross_amount_str else gross_amount_str + ".00"
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()
    if require_signature_validation:
        if not server_key or not signature_key:
            return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN
        if calculated_signature != signature_key:
            return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN

    if is_duplicate_webhook(notification_payload):
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

        try:
            transaction.midtrans_notification_payload = json.dumps(notification_payload, ensure_ascii=False)
        except Exception:
            transaction.midtrans_notification_payload = None

        midtrans_status_raw = notification_payload.get("transaction_status")
        midtrans_status = str(midtrans_status_raw).strip().lower() if isinstance(midtrans_status_raw, str) else ""
        fraud_status_raw = notification_payload.get("fraud_status")
        fraud_status = str(fraud_status_raw).strip().lower() if isinstance(fraud_status_raw, str) else None
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

        log_transaction_event(
            session=session,
            transaction=transaction,
            source=TransactionEventSource.MIDTRANS_WEBHOOK,
            event_type="NOTIFICATION",
            status=transaction.status,
            payload=notification_payload,
        )
        if notification_payload.get("transaction_id"):
            transaction.midtrans_transaction_id = notification_payload.get("transaction_id")

        if notification_payload.get("payment_type") and not transaction.payment_method:
            transaction.payment_method = notification_payload.get("payment_type")

        if parsed_expiry := safe_parse_midtrans_datetime(notification_payload.get("expiry_time")):
            transaction.expiry_time = parsed_expiry

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

        if is_qr_payment_type(notification_payload.get("payment_type")):
            transaction.qr_code_url = extract_qr_code_url(notification_payload) or transaction.qr_code_url

        if payment_success:
            transaction.payment_time = (
                safe_parse_midtrans_datetime(notification_payload.get("settlement_time"))
                or safe_parse_midtrans_datetime(notification_payload.get("transaction_time"))
                or transaction.payment_time
            )

        if payment_success:
            if is_debt_settlement_order_id(order_id):
                try:
                    result = apply_debt_settlement_on_success(session=session, transaction=transaction)
                    log_transaction_event(
                        session=session,
                        transaction=transaction,
                        source=TransactionEventSource.APP,
                        event_type="DEBT_SETTLED",
                        status=transaction.status,
                        payload=result,
                    )
                    session.commit()
                    try:
                        sync_address_list_for_single_user(transaction.user)
                    except Exception as sync_err:
                        current_app.logger.warning(
                            "WEBHOOK: DEBT settlement %s commit ok tetapi sync MikroTik gagal: %s",
                            order_id,
                            sync_err,
                        )
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
                    return (
                        jsonify({"status": "error", "message": "Gagal memproses pelunasan tunggakan."}),
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
            else:
                is_demo_user = _is_demo_user_eligible(getattr(transaction, "user", None))
                if is_demo_user:
                    skip_msg = "Demo payment-only: skip MikroTik sync."
                    log_transaction_event(
                        session=session,
                        transaction=transaction,
                        source=TransactionEventSource.APP,
                        event_type="DEMO_PAYMENT_ONLY_SKIP_MIKROTIK",
                        status=transaction.status,
                        payload={"message": skip_msg},
                    )
                    session.commit()
                    current_app.logger.info("WEBHOOK: %s order_id=%s", skip_msg, order_id)
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

                        temp_invoice_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"

                        status_token = generate_transaction_status_token(transaction.midtrans_order_id)
                        status_url = f"{base_url.rstrip('/')}/payment/status?order_id={transaction.midtrans_order_id}&t={status_token}"

                        msg_context = {
                            "full_name": user.full_name,
                            "order_id": transaction.midtrans_order_id,
                            "package_name": package.name,
                            "package_price": format_currency_fn(package.price),
                            "status_url": status_url,
                        }
                        caption_message = get_notification_message("purchase_success_with_invoice", msg_context)
                        filename = f"invoice-{transaction.midtrans_order_id}.pdf"

                        request_id = request.environ.get("FLASK_REQUEST_ID", "")
                        send_whatsapp_invoice_task.delay(
                            str(user.phone_number),
                            caption_message,
                            temp_invoice_url,
                            filename,
                            request_id,
                        )
                    except Exception as e_notif:
                        current_app.logger.error(
                            f"WEBHOOK: Gagal kirim notif WhatsApp {order_id}: {e_notif}", exc_info=True
                        )
                    return jsonify({"status": "ok"}), HTTPStatus.OK

                should_apply, effect_lock_key = begin_order_effect(
                    order_id=order_id,
                    effect_name="hotspot_apply",
                    session=session,
                )
                if not should_apply:
                    current_app.logger.info(
                        "WEBHOOK: skip duplicate hotspot apply side-effect untuk order %s (effect lock/done).",
                        order_id,
                    )
                    session.commit()
                    return jsonify({"status": "ok", "message": "Duplicate side effect skipped"}), HTTPStatus.OK

                with get_mikrotik_connection() as mikrotik_api:
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

                            temp_invoice_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"

                            status_token = generate_transaction_status_token(transaction.midtrans_order_id)
                            status_url = f"{base_url.rstrip('/')}/payment/status?order_id={transaction.midtrans_order_id}&t={status_token}"

                            msg_context = {
                                "full_name": user.full_name,
                                "order_id": transaction.midtrans_order_id,
                                "package_name": package.name,
                                "package_price": format_currency_fn(package.price),
                                "status_url": status_url,
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
                        finally:
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
            session.commit()
            status_value = transaction.status.value if transaction.status is not None else "UNKNOWN"
            current_app.logger.info(f"WEBHOOK: Status transaksi {order_id} diupdate ke {status_value}.")
            if transaction.status in [TransactionStatus.FAILED, TransactionStatus.CANCELLED, TransactionStatus.EXPIRED]:
                increment_metric("payment.failed")

        return jsonify({"status": "ok"}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"WEBHOOK Error {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        db.session.remove()
