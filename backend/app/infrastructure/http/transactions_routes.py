# backend/app/infrastructure/http/transactions_routes.py
# PENYEMPURNAAN: Beralih ke Flask-JWT-Extended untuk autentikasi.
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false

import hashlib
import uuid
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Dict, Optional

from flask import (
    Blueprint, abort, current_app, jsonify, make_response, render_template, request
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from flask_jwt_extended import jwt_required, get_current_user # [PERBAIKAN] Impor baru

import midtransclient

from app.extensions import db, limiter
from app.infrastructure.db.models import (
    ApprovalStatus, Package, Transaction, TransactionStatus, User
)
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from app.services.notification_service import (
    generate_temp_invoice_token, get_notification_message, verify_temp_invoice_token
)
from app.services import settings_service
from app.utils.formatters import format_to_local_phone
# [DIHAPUS] Impor decorator lama tidak diperlukan lagi.
# from .decorators import token_required

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    HTML = None
    WEASYPRINT_AVAILABLE = False
    logging.getLogger(__name__).warning(f"WeasyPrint tidak tersedia: {e}. Fitur PDF dinonaktifkan.")

transactions_bp = Blueprint("transactions_api", __name__)
module_log = logging.getLogger(__name__)

# ... (Semua fungsi helper dari baris 53 hingga 128 tetap sama persis) ...
def get_midtrans_core_api_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise ValueError("Konfigurasi MIDTRANS_SERVER_KEY tidak ditemukan.")
    return midtransclient.CoreApi(is_production=is_production, server_key=server_key)

def get_midtrans_snap_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    client_key = current_app.config.get("MIDTRANS_CLIENT_KEY")
    if not server_key or not client_key:
        raise ValueError("Konfigurasi MIDTRANS_SERVER_KEY atau MIDTRANS_CLIENT_KEY tidak ditemukan.")
    return midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)

def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string: return None
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
    specific_fields = ["permata_va_number", "bca_va_number", "bni_va_number", "bri_va_number", "cimb_va_number", "mandiri_bill_key", "bill_key", "payment_code", "va_number"]
    for field in specific_fields:
        if field_value := response_data.get(field):
            return str(field_value).strip()
    return None

def extract_qr_code_url(response_data: Dict[str, Any]):
    actions = response_data.get("actions")
    if isinstance(actions, list):
        for action in actions:
            action_name = action.get("name", "").lower()
            qr_url = action.get("url")
            if qr_url and "generate-qr-code" in action_name:
                return qr_url
    return response_data.get("qr_code_url")

def format_datetime_short(value: datetime) -> str:
    if not isinstance(value, datetime): return ""
    try:
        app_tz_offset = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))
        local_dt = value.astimezone(app_tz)
        return local_dt.strftime("%d %b %Y, %H:%M WITA")
    except Exception: return "Invalid Date"

def format_currency(value: Any) -> str:
    if value is None: return "Rp 0"
    try:
        decimal_value = Decimal(value)
        return f"Rp {decimal_value:,.0f}".replace(",", ".")
    except Exception: return "Rp Error"

def format_status(value: str) -> str:
    if not isinstance(value, str): return value
    return value.replace("_", " ").title()

@transactions_bp.app_template_filter("format_datetime_short")
def _format_datetime_short_filter(value): return format_datetime_short(value)
@transactions_bp.app_template_filter("format_currency")
def _format_currency_filter(value): return format_currency(value)
@transactions_bp.app_template_filter("format_status")
def _format_status_filter(value): return format_status(value)


@transactions_bp.route("/initiate", methods=["POST"])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
@limiter.limit("10 per minute")
def initiate_transaction():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    req_data = request.get_json(silent=True)
    if not req_data or 'package_id' not in req_data:
        return jsonify({"success": False, "message": "Input tidak valid, 'package_id' diperlukan."}), HTTPStatus.BAD_REQUEST

    try:
        package_id = uuid.UUID(req_data['package_id'])
    except ValueError:
        return jsonify({"success": False, "message": "Format 'package_id' tidak valid."}), HTTPStatus.BAD_REQUEST
    
    session = db.session
    try:
        package = session.get(Package, package_id)
        if not package or not package.is_active:
            return jsonify({"success": False, "message": "Paket tidak valid atau tidak aktif."}), HTTPStatus.BAD_REQUEST

        order_id = f"HS-{uuid.uuid4().hex[:12].upper()}"
        gross_amount = int(package.price or 0)

        new_transaction = Transaction(
            id=uuid.uuid4(), user_id=current_user.id, package_id=package.id,
            midtrans_order_id=order_id, amount=gross_amount, status=TransactionStatus.PENDING,
        )
        
        base_callback_url = current_app.config.get('APP_PUBLIC_BASE_URL') or current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        finish_url = f"{base_callback_url.rstrip('/')}/payment/finish?order_id={order_id}"
        
        snap_params = {
            "transaction_details": {"order_id": order_id, "gross_amount": gross_amount},
            "item_details": [{"id": str(package.id), "price": gross_amount, "quantity": 1, "name": package.name[:100]}],
            "customer_details": {"first_name": current_user.full_name or "Pengguna", "phone": format_to_local_phone(current_user.phone_number)},
            "callbacks": {"finish": finish_url }
        }

        snap = get_midtrans_snap_client()
        snap_response = snap.create_transaction(snap_params)
        
        new_transaction.snap_token = snap_response.get("token")
        new_transaction.snap_redirect_url = snap_response.get("redirect_url")
        
        if not new_transaction.snap_token:
            raise ValueError("Respons Midtrans tidak valid, snap_token tidak ditemukan.")

        session.add(new_transaction)
        session.commit()

        if settings_service.get_setting('SEND_INVOICE_ON_CREATION', 'False') == 'True':
            try:
                from app.tasks import send_whatsapp_invoice_task
                temp_token = generate_temp_invoice_token(str(new_transaction.id))
                base_url = current_app.config.get('APP_PUBLIC_BASE_URL')
                if not base_url: raise ValueError("Konfigurasi APP_PUBLIC_BASE_URL tidak ditemukan.")
                pdf_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"
                caption = get_notification_message("transaction_created", {"full_name": current_user.full_name, "order_id": order_id, "package_name": package.name, "price": format_currency(gross_amount), "payment_link": new_transaction.snap_redirect_url})
                send_whatsapp_invoice_task.delay(recipient_number=current_user.phone_number, caption=caption, pdf_url=pdf_url, filename=f"invoice-{order_id}.pdf")
            except Exception as e_task: module_log.error(f"Gagal mengirim task notifikasi untuk {order_id}: {e_task}", exc_info=True)

        return jsonify({
            "snap_token": new_transaction.snap_token,
            "order_id": new_transaction.midtrans_order_id,
            "redirect_url": new_transaction.snap_redirect_url
        }), HTTPStatus.CREATED
        
    except Exception as e:
        session.rollback()
        
        if hasattr(e, 'api_response') and hasattr(e, 'message'):
            error_message = f"Midtrans API Error: {e.message}"
            module_log.error(f"Gagal membuat transaksi Midtrans untuk Order ID {order_id}. Detail: {error_message}")
            if e.api_response:
                 module_log.error(f"Response dari Midtrans (Status: {e.api_response.status_code}): {e.api_response.text}")
            
            return jsonify({"success": False, "message": f"Gateway pembayaran menolak permintaan: {e.message}"}), HTTPStatus.BAD_GATEWAY
        else:
            module_log.error(f"Error tak terduga di initiate_transaction untuk Order ID {order_id}: {e}", exc_info=True)
            return jsonify({"success": False, "message": "Terjadi kesalahan internal saat memulai transaksi."}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        session.remove()


@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
    notification_payload = request.get_json(silent=True) or {}
    order_id = notification_payload.get("order_id")
    module_log.info(f"WEBHOOK: Diterima untuk Order ID: {order_id}, Status Midtrans: {notification_payload.get('transaction_status')}")

    if not all([order_id, notification_payload.get("transaction_status"), notification_payload.get("status_code"), notification_payload.get("gross_amount")]):
        return jsonify({"status": "ok", "message": "Payload tidak lengkap"}), HTTPStatus.OK

    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    gross_amount_str = notification_payload.get("gross_amount", "0")
    gross_amount_str_for_hash = (gross_amount_str if "." in gross_amount_str else gross_amount_str + ".00")
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()
    if (calculated_signature != notification_payload.get("signature_key") and current_app.config.get("MIDTRANS_IS_PRODUCTION", False)):
        return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN

    session = db.session
    try:
        transaction = session.query(Transaction).options(selectinload(Transaction.user), selectinload(Transaction.package)).filter(Transaction.midtrans_order_id == order_id).with_for_update().first()
        if not transaction or transaction.status == TransactionStatus.SUCCESS:
            return jsonify({"status": "ok"}), HTTPStatus.OK

        midtrans_status = notification_payload.get("transaction_status")
        fraud_status = notification_payload.get("fraud_status")
        payment_success = (midtrans_status in ["capture", "settlement"] and fraud_status == "accept")
        status_map = {"capture": TransactionStatus.SUCCESS, "settlement": TransactionStatus.SUCCESS, "pending": TransactionStatus.PENDING, "deny": TransactionStatus.FAILED, "expire": TransactionStatus.EXPIRED, "cancel": TransactionStatus.CANCELLED}
        transaction.status = status_map.get(midtrans_status, transaction.status)

        if payment_success:
            is_success, message = apply_package_and_sync_to_mikrotik(transaction)
            
            if is_success:
                session.commit()
                module_log.info(f"WEBHOOK: Transaksi {order_id} BERHASIL di-commit. Pesan: {message}")
                try:
                    from app.tasks import send_whatsapp_invoice_task
                    user, package = transaction.user, transaction.package
                    temp_token = generate_temp_invoice_token(str(transaction.id))
                    base_url = current_app.config.get('APP_PUBLIC_BASE_URL')
                    if not base_url: raise ValueError("Konfigurasi APP_PUBLIC_BASE_URL tidak ditemukan.")
                    temp_invoice_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"
                    msg_context = {"full_name": user.full_name, "order_id": transaction.midtrans_order_id, "package_name": package.name, "package_price": format_currency(package.price)}
                    caption_message = get_notification_message("purchase_success_with_invoice", msg_context)
                    filename = f"invoice-{transaction.midtrans_order_id}.pdf"
                    send_whatsapp_invoice_task.delay(str(user.phone_number), caption_message, temp_invoice_url, filename)
                except Exception as e_notif: module_log.error(f"WEBHOOK: Gagal kirim notif WhatsApp {order_id}: {e_notif}", exc_info=True)
            else:
                session.rollback()
                module_log.error(f"WEBHOOK: Gagal apply paket ke Mikrotik untuk {order_id}. Rollback transaksi.")
        else:
            session.commit()
            module_log.info(f"WEBHOOK: Status transaksi {order_id} diupdate ke {transaction.status.value}.")
        return jsonify({"status": "ok"}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        module_log.error(f"WEBHOOK Error {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        session.remove()

@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_transaction_by_order_id(order_id: str):
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()
    
    session = db.session
    try:
        transaction = (session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).options(selectinload(Transaction.user), selectinload(Transaction.package).selectinload(Package.profile)).first())
        if not transaction: abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")
        
        if transaction.user_id != current_user.id and not current_user.is_admin_role:
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan melihat transaksi ini.")

        if transaction.status == TransactionStatus.PENDING:
            try:
                core_api = get_midtrans_core_api_client()
                midtrans_status_response = core_api.transactions.status(order_id)
                midtrans_trx_status = midtrans_status_response.get("transaction_status")
                fraud_status = midtrans_status_response.get("fraud_status")
                payment_success = (midtrans_trx_status in ["capture", "settlement"] and fraud_status == "accept")

                if payment_success:
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.payment_method = midtrans_status_response.get("payment_type")
                    transaction.midtrans_transaction_id = midtrans_status_response.get("transaction_id")
                    transaction.payment_time = safe_parse_midtrans_datetime(midtrans_status_response.get("settlement_time")) or datetime.now(dt_timezone.utc)
                    transaction.va_number = extract_va_number(midtrans_status_response)

                    is_success, message = apply_package_and_sync_to_mikrotik(transaction)

                    if is_success:
                        session.commit()
                    else:
                        session.rollback()
                        abort(HTTPStatus.INTERNAL_SERVER_ERROR, f"Gagal menerapkan paket: {message}")
                else:
                    status_map = {"deny": TransactionStatus.FAILED, "expire": TransactionStatus.EXPIRED, "cancel": TransactionStatus.CANCELLED}
                    if new_status := status_map.get(midtrans_trx_status):
                        if transaction.status != new_status:
                            transaction.status = new_status
                            session.commit()
            except midtransclient.error_midtrans.MidtransAPIError as midtrans_err: current_app.logger.warning(f"GET Detail: Gagal cek status Midtrans untuk PENDING {order_id}: {midtrans_err.message}")
            except Exception as e_check_status: current_app.logger.error(f"GET Detail: Error tak terduga saat cek status Midtrans untuk PENDING {order_id}: {e_check_status}")

        session.refresh(transaction)
        p, u = transaction.package, transaction.user
        response_data = {"id": str(transaction.id), "midtrans_order_id": transaction.midtrans_order_id, "status": transaction.status.value, "amount": float(transaction.amount or 0.0), "package": {"id": str(p.id), "name": p.name} if p else None, "user": {"id": str(u.id), "full_name": u.full_name} if u else None}
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        if session.is_active: session.rollback()
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)): raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        if session: session.remove()

@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_transaction_invoice(midtrans_order_id: str):
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    if not WEASYPRINT_AVAILABLE:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")
    session = db.session
    try:
        transaction = session.query(Transaction).options(selectinload(Transaction.user), selectinload(Transaction.package)).filter(Transaction.midtrans_order_id == midtrans_order_id).first()
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, "Transaksi tidak ditemukan.")
        if transaction.user_id != current_user.id and not current_user.is_admin_role:
            abort(HTTPStatus.FORBIDDEN, "Anda tidak diizinkan mengakses invoice ini.")
        if transaction.status != TransactionStatus.SUCCESS:
            abort(HTTPStatus.BAD_REQUEST, "Invoice hanya tersedia untuk transaksi yang sudah sukses.")
        
        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        
        blok_obj = transaction.user.blok
        kamar_obj = transaction.user.kamar
        blok_display = blok_obj.value if blok_obj else ""
        kamar_display = kamar_obj.value.replace("Kamar_", "") if kamar_obj else ""

        context = {
            'transaction': transaction, 'user': transaction.user, 'package': transaction.package,
            'user_blok_value': blok_display,
            'user_kamar_value': kamar_display,
            'business_name': current_app.config.get('BUSINESS_NAME', 'Nama Bisnis Anda'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Alamat Bisnis Anda'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', 'Telepon Bisnis Anda'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'Email Bisnis Anda'),
            'invoice_date_local': datetime.now(app_tz),
        }
        
        public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
        html_string = render_template('invoice_template.html', **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()

        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
        return response
    except Exception as e:
        if session.is_active: session.rollback()
        module_log.error(f"Error saat membuat invoice PDF untuk {midtrans_order_id}: {e}", exc_info=True)
        if isinstance(e, HTTPStatus): 
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session: session.remove()

@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
@transactions_bp.route("/invoice/temp/<string:token>.pdf", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    if not WEASYPRINT_AVAILABLE or not HTML:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    transaction_id = verify_temp_invoice_token(token, max_age_seconds=3600)
    if not transaction_id:
        abort(HTTPStatus.FORBIDDEN, description="Akses tidak valid atau link telah kedaluwarsa.")
        
    session = db.session
    try:
        transaction = session.query(Transaction).options(
            selectinload(Transaction.user), 
            selectinload(Transaction.package)
        ).filter(Transaction.id == uuid.UUID(transaction_id)).first()

        if not transaction or transaction.status != TransactionStatus.SUCCESS:
            abort(HTTPStatus.NOT_FOUND, "Invoice tidak ditemukan atau transaksi belum berhasil.")
        
        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        
        blok_obj = transaction.user.blok
        kamar_obj = transaction.user.kamar
        blok_display = blok_obj.value if blok_obj else ""
        kamar_display = kamar_obj.value.replace("Kamar_", "") if kamar_obj else ""

        context = {
            'transaction': transaction, 'user': transaction.user, 'package': transaction.package,
            'user_blok_value': blok_display,
            'user_kamar_value': kamar_display,
            'business_name': current_app.config.get('BUSINESS_NAME', 'Nama Bisnis Anda'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Alamat Bisnis Anda'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', 'Telepon Bisnis Anda'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'Email Bisnis Anda'),
            'invoice_date_local': datetime.now(app_tz),
        }

        public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
        html_string = render_template('invoice_template.html', **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
            
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="invoice-{transaction.midtrans_order_id}.pdf"'
        
        return response
    except Exception as e:
        db.session.rollback()
        module_log.error(f"Error saat membuat invoice sementara PDF: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan tak terduga saat membuat invoice.")
    finally:
        session.remove()