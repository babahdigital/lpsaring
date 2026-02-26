from http import HTTPStatus

import midtransclient
from flask import abort, current_app, jsonify, make_response
from werkzeug.exceptions import HTTPException

from app.infrastructure.db.models import Transaction, TransactionEventSource, TransactionStatus, User, UserQuotaDebt
from app.infrastructure.http.error_envelope import error_response
from app.infrastructure.http.transactions.reconcile_service import reconcile_pending_transaction


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

        reconcile_pending_transaction(
            transaction=transaction,
            session=session,
            order_id=order_id,
            route_label="auth_get_transaction_by_order_id",
            should_allow_call=should_allow_call,
            get_midtrans_core_api_client=get_midtrans_core_api_client,
            record_success=record_success,
            record_failure=record_failure,
            log_transaction_event=log_transaction_event,
            safe_parse_midtrans_datetime=safe_parse_midtrans_datetime,
            extract_va_number=extract_va_number,
            is_qr_payment_type=is_qr_payment_type,
            extract_qr_code_url=extract_qr_code_url,
            begin_order_effect=begin_order_effect,
            finish_order_effect=finish_order_effect,
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
