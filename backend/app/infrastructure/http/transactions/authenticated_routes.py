import json
from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus

import midtransclient
from flask import abort, current_app, jsonify, make_response
from werkzeug.exceptions import HTTPException

from app.infrastructure.db.models import Transaction, TransactionEventSource, TransactionStatus, User, UserQuotaDebt
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from app.infrastructure.http.error_envelope import error_response


def get_transaction_by_order_id_impl(
    *,
    current_user_id,
    order_id: str,
    db,
    session,
    selectinload,
    Package,
    should_allow_call,
    get_midtrans_core_api_client,
    record_success,
    record_failure,
    log_transaction_event,
    safe_parse_midtrans_datetime,
    extract_va_number,
    is_qr_payment_type,
    extract_qr_code_url,
    is_debt_settlement_order_id,
    extract_manual_debt_id_from_order_id,
    begin_order_effect,
    finish_order_effect,
):
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

                    should_apply, effect_lock_key = begin_order_effect(order_id=order_id, effect_name="hotspot_apply")
                    if not should_apply:
                        current_app.logger.info(
                            "GET Detail: skip duplicate hotspot apply side-effect untuk order %s (effect lock/done).",
                            order_id,
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

        is_debt_settlement = is_debt_settlement_order_id(transaction.midtrans_order_id)
        manual_debt_id = extract_manual_debt_id_from_order_id(transaction.midtrans_order_id) if is_debt_settlement else None

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
            "snap_redirect_url": transaction.snap_redirect_url if getattr(transaction, "snap_token", None) else None,
            "deeplink_redirect_url": (
                transaction.snap_redirect_url if (transaction.snap_token is None and transaction.snap_redirect_url) else None
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
        if isinstance(e, (HTTPException, midtransclient.error_midtrans.MidtransAPIError)):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        if session:
            session.remove()


def cancel_transaction_impl(*, current_user_id, order_id: str, session, log_transaction_event):
    try:
        transaction = session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).with_for_update().first()
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan membatalkan transaksi ini.")

        if transaction.status == TransactionStatus.SUCCESS:
            return error_response(
                "Transaksi sudah sukses dan tidak bisa dibatalkan.",
                status_code=HTTPStatus.BAD_REQUEST,
                code="TRANSACTION_ALREADY_SUCCESS",
            )

        if transaction.status in (TransactionStatus.UNKNOWN, TransactionStatus.PENDING):
            transaction.status = TransactionStatus.CANCELLED
            log_transaction_event(
                session=session,
                transaction=transaction,
                source=TransactionEventSource.APP,
                event_type="CANCELLED_BY_USER",
                status=transaction.status,
                payload={"order_id": order_id},
            )
            session.commit()
        return jsonify({"success": True, "status": transaction.status.value}), HTTPStatus.OK
    except HTTPException:
        raise
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Gagal membatalkan transaksi {order_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal membatalkan transaksi.")
    finally:
        session.remove()


def get_transaction_qr_impl(*, current_user_id, midtrans_order_id: str, session, request, requests_module):
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
        upstream = requests_module.get(qr_url, timeout=timeout_seconds)
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
