import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from http import HTTPStatus

from flask import abort, current_app
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import HTTPException

from app.infrastructure.db.models import Transaction, TransactionStatus, User


def get_transaction_invoice_impl(
    *,
    current_user_id,
    midtrans_order_id: str,
    session,
    selectinload,
    render_template,
    request,
    make_response,
    html_class,
    weasyprint_available: bool,
    midtransclient_module,
):
    if not weasyprint_available:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")
    assert html_class is not None

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
        pdf_bytes = html_class(string=html_string, base_url=public_base_url).write_pdf()

        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
        return response
    except HTTPException:
        raise
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Error saat membuat invoice PDF untuk {midtrans_order_id}: {e}", exc_info=True)
        if isinstance(e, midtransclient_module.error_midtrans.MidtransAPIError):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session:
            session.remove()


def get_temp_transaction_invoice_impl(
    *,
    token: str,
    session,
    verify_temp_invoice_token,
    render_template,
    request,
    make_response,
    html_class,
    weasyprint_available: bool,
):
    if not weasyprint_available or html_class is None:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    transaction_id = verify_temp_invoice_token(token, max_age_seconds=3600)
    if not transaction_id:
        abort(HTTPStatus.FORBIDDEN, description="Akses tidak valid atau link telah kedaluwarsa.")

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

        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("invoice_template.html", **context)
        pdf_bytes = html_class(string=html_string, base_url=public_base_url).write_pdf()

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{transaction.midtrans_order_id}.pdf"'

        return response
    except HTTPException:
        raise
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Error saat membuat invoice sementara PDF: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan tak terduga saat membuat invoice.")
    finally:
        session.remove()
