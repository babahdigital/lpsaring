# backend/app/infrastructure/http/transactions_routes.py
# VERSI FINAL LENGKAP: Dengan notifikasi invoice PDF via WhatsApp

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Dict, Optional

import midtransclient
from flask import (
    Blueprint, abort, current_app, jsonify, make_response, render_template, request
)
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import (
    ApprovalStatus, Package, Transaction, TransactionStatus, User
)
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
# --- Impor yang Disesuaikan ---
from app.services.notification_service import (
    generate_temp_invoice_token, get_notification_message, verify_temp_invoice_token
)
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf # Impor fungsi baru
# -----------------------------
from app.utils.formatters import format_to_local_phone
from .decorators import token_required

# Ketersediaan Klien (Gateway)
try:
    from app.infrastructure.gateways.mikrotik_client import (
        activate_or_update_hotspot_user,
        get_mikrotik_connection,
    )
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    MIKROTIK_CLIENT_AVAILABLE = False
    def get_mikrotik_connection(): return None
    def activate_or_update_hotspot_user(*args, **kwargs): return False, "Not implemented"

# --- PERBAIKAN IMPORT WHATSAPP CLIENT ---
# Impor kedua fungsi dari whatsapp_client
try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message, send_whatsapp_with_pdf
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    def send_whatsapp_message(to, body): return False
    def send_whatsapp_with_pdf(to, caption, pdf_url, filename): return False


WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import CSS, HTML
    HTML_MODULE = HTML
    CSS_MODULE = CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML_MODULE = None
    CSS_MODULE = None
    pass

transactions_bp = Blueprint(
    "transactions_api",
    __name__,
    url_prefix="/api/transactions",
    template_folder=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "../../templates"
    ),
)


# --- FUNGSI HELPER (TETAP SAMA) ---
def get_midtrans_core_api_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    return midtransclient.CoreApi(is_production=is_production, server_key=server_key)


def get_midtrans_snap_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    client_key = current_app.config.get("MIDTRANS_CLIENT_KEY")
    if not server_key or not client_key:
        raise ValueError("MIDTRANS_SERVER_KEY or MIDTRANS_CLIENT_KEY configuration is missing.")
    return midtransclient.Snap(
        is_production=is_production, server_key=server_key, client_key=client_key
    )


def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string:
        return None
    try:
        naive_dt = datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")
        offset_hours = int(current_app.config.get("MIDTRANS_DATETIME_INPUT_OFFSET_HOURS", 7))
        return naive_dt.replace(tzinfo=dt_timezone(timedelta(hours=offset_hours))).astimezone(
            dt_timezone.utc
        )
    except (ValueError, TypeError):
        return None


def extract_va_number(response_data: Dict[str, Any]):
    va_numbers = response_data.get("va_numbers")
    if isinstance(va_numbers, list) and len(va_numbers) > 0:
        for va_info in va_numbers:
            if isinstance(va_info, dict) and va_info.get("va_number"):
                return str(va_info.get("va_number")).strip()
    specific_fields = [
        "permata_va_number", "bca_va_number", "bni_va_number",
        "bri_va_number", "cimb_va_number", "mandiri_bill_key",
        "bill_key", "payment_code", "va_number",
    ]
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


# --- JINJA FILTERS (TETAP SAMA) ---
def format_datetime_short(value: datetime) -> str:
    if not isinstance(value, datetime): return ""
    try:
        app_tz_offset = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))
        local_dt = value.astimezone(app_tz)
        return local_dt.strftime("%d %b %Y, %H:%M WITA")
    except Exception as e:
        current_app.logger.error(f"Error applying format_datetime_short filter: {e}", exc_info=True)
        return "Invalid Date"

def format_currency(value: Any) -> str:
    if value is None: return "Rp 0"
    try:
        decimal_value = Decimal(value)
        return f"Rp {decimal_value:,.0f}".replace(",", ".")
    except Exception as e:
        current_app.logger.error(f"Error applying format_currency filter: {e}", exc_info=True)
        return "Rp Error"

def format_status(value: str) -> str:
    if not isinstance(value, str): return value
    return value.replace("_", " ").title()

@transactions_bp.app_template_filter("format_datetime_short")
def _format_datetime_short_filter(value): return format_datetime_short(value)
@transactions_bp.app_template_filter("format_currency")
def _format_currency_filter(value): return format_currency(value)
@transactions_bp.app_template_filter("format_status")
def _format_status_filter(value): return format_status(value)

# --- SKEMA (TETAP SAMA) ---
class _InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID
class _InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = None
    transaction_id: str
    order_id: str
    redirect_url: Optional[str] = None
    class Config: from_attributes = True

# --- ENDPOINT /initiate (TETAP SAMA) ---
@transactions_bp.route("/initiate", methods=["POST"])
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    req_data_dict = request.get_json(silent=True) or {}
    try:
        req_data = _InitiateTransactionRequestSchema.model_validate(req_data_dict)
    except ValidationError as e:
        return jsonify({"success": False, "message": "Input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    session = db.session
    try:
        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        package = session.query(Package).options(selectinload(Package.profile)).get(req_data.package_id)
        if not package or not package.is_active or not package.profile:
            abort(HTTPStatus.BAD_REQUEST, description="Paket tidak valid, tidak aktif, atau tidak memiliki profil.")
        
        order_id = f"HS-{uuid.uuid4().hex[:12].upper()}"
        gross_amount = int(package.price or 0)

        new_transaction = Transaction(
            id=uuid.uuid4(), user_id=user.id, package_id=package.id,
            midtrans_order_id=order_id, amount=gross_amount, status=TransactionStatus.PENDING,
        )
        
        snap_params = {
            "transaction_details": {"order_id": order_id, "gross_amount": gross_amount},
            "item_details": [{"id": str(package.id), "price": gross_amount, "quantity": 1, "name": package.name[:100]}],
            "customer_details": {"first_name": user.full_name or "Pengguna", "phone": format_to_local_phone(user.phone_number)},
            "callbacks": {"finish": f"{current_app.config.get('FRONTEND_URL', 'http://localhost:3000').rstrip('/')}/payment/finish?order_id={order_id}&status=pending"}
        }

        snap = get_midtrans_snap_client()
        snap_response = snap.create_transaction(snap_params)
        
        snap_token = snap_response.get("token")
        redirect_url = snap_response.get("redirect_url")
        if not snap_token and not redirect_url:
            raise ValueError("Respons Midtrans tidak valid.")

        new_transaction.snap_token = snap_token
        new_transaction.snap_redirect_url = redirect_url
        session.add(new_transaction)
        session.commit()

        response_data = _InitiateTransactionResponseSchema(
            snap_token=snap_token, transaction_id=str(new_transaction.id),
            order_id=new_transaction.midtrans_order_id, redirect_url=redirect_url
        )
        return jsonify(response_data.model_dump(exclude_none=True)), HTTPStatus.OK

    except (ValueError, midtransclient.error_midtrans.MidtransAPIError) as ve:
        session.rollback()
        current_app.logger.error(f"Gateway Pembayaran Error: {ve}", exc_info=True)
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description=f"Gateway Pembayaran Error: {ve}")
    except SQLAlchemyError as db_err:
        session.rollback()
        current_app.logger.error(f"Kesalahan database saat memulai transaksi: {db_err}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan database saat memulai transaksi.")
    except Exception as e:
        session.rollback()
        current_app.logger.error(f"Kesalahan internal server: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan internal server: {e}")
    finally:
        session.remove()


# --- ENDPOINT /notification (DENGAN MODIFIKASI) ---
@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
    notification_payload = request.get_json(silent=True) or {}
    order_id = notification_payload.get("order_id")
    current_app.logger.info(f"WEBHOOK: Diterima untuk Order ID: {order_id}, Status Midtrans: {notification_payload.get('transaction_status')}")

    if not all([order_id, notification_payload.get("transaction_status"), notification_payload.get("status_code"), notification_payload.get("gross_amount")]):
        return jsonify({"status": "ok", "message": "Payload tidak lengkap"}), HTTPStatus.OK

    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    gross_amount_str = notification_payload.get("gross_amount")
    gross_amount_str_for_hash = (gross_amount_str if "." in gross_amount_str else gross_amount_str + ".00")
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()

    if (calculated_signature != notification_payload.get("signature_key") and current_app.config.get("MIDTRANS_IS_PRODUCTION", False)):
        return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN

    session = db.session
    try:
        transaction = (session.query(Transaction).options(
                selectinload(Transaction.user),
                selectinload(Transaction.package).selectinload(Package.profile),
            ).filter(Transaction.midtrans_order_id == order_id).with_for_update().first())

        if not transaction or transaction.status == TransactionStatus.SUCCESS:
            current_app.logger.info(f"WEBHOOK: Transaksi {order_id} tidak ditemukan atau sudah sukses. Diabaikan.")
            return jsonify({"status": "ok"}), HTTPStatus.OK

        midtrans_status = notification_payload.get("transaction_status")
        fraud_status = notification_payload.get("fraud_status")
        payment_success = (midtrans_status in ["capture", "settlement"] and fraud_status == "accept")

        status_map = {
            "capture": TransactionStatus.SUCCESS, "settlement": TransactionStatus.SUCCESS,
            "pending": TransactionStatus.PENDING, "deny": TransactionStatus.FAILED,
            "expire": TransactionStatus.EXPIRED, "cancel": TransactionStatus.CANCELLED,
        }
        transaction.status = status_map.get(midtrans_status, transaction.status)
        transaction.payment_method = notification_payload.get("payment_type")
        transaction.midtrans_transaction_id = notification_payload.get("transaction_id")
        transaction.payment_time = safe_parse_midtrans_datetime(notification_payload.get("settlement_time") or notification_payload.get("transaction_time"))
        transaction.va_number = extract_va_number(notification_payload)

        if payment_success:
            current_app.logger.info(f"WEBHOOK: Pembayaran SUKSES untuk {order_id}. Memulai proses penerapan dan sinkronisasi.")
            with get_mikrotik_connection() as mikrotik_api:
                if not mikrotik_api:
                    current_app.logger.error(f"WEBHOOK: Gagal konek ke Mikrotik untuk transaksi {order_id}. Proses dihentikan.")
                    session.commit()
                    return jsonify({"status": "error", "message": "Gagal koneksi ke sistem hotspot"}), HTTPStatus.INTERNAL_SERVER_ERROR

                is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                if is_success:
                    session.commit()
                    current_app.logger.info(f"WEBHOOK: Transaksi {order_id} dan update user BERHASIL di-commit. Pesan: {message}")

                    # --- BLOK BARU: KIRIM NOTIFIKASI WHATSAPP DENGAN INVOICE PDF ---
                    try:
                        user = transaction.user
                        package = transaction.package
                        
                        # 1. Buat token dan URL invoice sementara
                        temp_token = generate_temp_invoice_token(transaction.id)
                        # Pastikan menggunakan HTTPS di production
                        base_url = request.url_root.rstrip('/')
                        temp_invoice_url = f"{base_url}/api/transactions/invoice/temp/{temp_token}"
                        
                        # 2. Siapkan konteks untuk pesan
                        msg_context = {
                            "user_full_name": user.full_name,
                            "order_id": transaction.midtrans_order_id,
                            "package_name": package.name,
                            "package_price": format_currency(package.price)
                        }
                        
                        # 3. Dapatkan caption/body pesan dari service notifikasi
                        caption_message = get_notification_message("purchase_success_notification", msg_context)
                        
                        # 4. Kirim WhatsApp dengan PDF
                        filename = f"invoice-{transaction.midtrans_order_id}.pdf"
                        send_whatsapp_with_pdf(user.phone_number, caption_message, temp_invoice_url, filename)
                        current_app.logger.info(f"WEBHOOK: Notifikasi WhatsApp dengan invoice untuk {order_id} telah diantrekan untuk pengiriman.")

                    except Exception as e_notif:
                        # Kegagalan mengirim notif tidak boleh menggagalkan seluruh transaksi
                        current_app.logger.error(f"WEBHOOK: Gagal mengirim notifikasi WhatsApp untuk {order_id}: {e_notif}", exc_info=True)
                    # --- AKHIR BLOK BARU ---
                    
                else:
                    session.rollback()
                    current_app.logger.error(f"WEBHOOK: Proses transaksi {order_id} GAGAL dan di-rollback. Pesan: {message}")
        else:
            session.commit()

        return jsonify({"status": "ok"}), HTTPStatus.OK

    except Exception as e:
        if session.is_active: session.rollback()
        current_app.logger.error(f"WEBHOOK: Error tidak terduga untuk {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        if session: session.remove()


# --- ENDPOINT /by-order-id (TETAP SAMA) ---
@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    # Logika tetap sama, tidak perlu diubah.
    session = db.session
    try:
        transaction = (session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).options(
                selectinload(Transaction.user),
                selectinload(Transaction.package).selectinload(Package.profile),
            ).first())
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
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

                    with get_mikrotik_connection() as mikrotik_api:
                        if not mikrotik_api:
                            abort(HTTPStatus.SERVICE_UNAVAILABLE, "Gagal koneksi ke sistem hotspot untuk sinkronisasi.")
                        is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
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
            except midtransclient.error_midtrans.MidtransAPIError as midtrans_err:
                current_app.logger.warning(f"GET Detail: Gagal cek status Midtrans untuk PENDING {order_id}: {midtrans_err.message}")
            except Exception as e_check_status:
                current_app.logger.error(f"GET Detail: Error tak terduga saat cek status Midtrans untuk PENDING {order_id}: {e_check_status}")

        session.refresh(transaction)
        p = transaction.package
        u = transaction.user
        response_data = {
            "id": str(transaction.id), "midtrans_order_id": transaction.midtrans_order_id,
            "midtrans_transaction_id": transaction.midtrans_transaction_id, "status": transaction.status.value,
            "amount": float(transaction.amount or 0.0), "payment_method": transaction.payment_method,
            "payment_time": transaction.payment_time.isoformat() if transaction.payment_time else None,
            "expiry_time": transaction.expiry_time.isoformat() if transaction.expiry_time else None,
            "va_number": transaction.va_number, "payment_code": transaction.payment_code,
            "biller_code": getattr(transaction, 'biller_code', None), "qr_code_url": transaction.qr_code_url,
            "hotspot_password": transaction.hotspot_password,
            "package": {"id": str(p.id), "name": p.name, "description": p.description, "price": float(p.price or 0.0), "data_quota_gb": float(p.data_quota_gb or 0.0), "is_unlimited": (p.data_quota_gb == 0)} if p else None,
            "user": {"id": str(u.id), "phone_number": u.phone_number, "full_name": u.full_name, "quota_expiry_date": u.quota_expiry_date.isoformat() if u.quota_expiry_date else None, "is_unlimited_user": u.is_unlimited_user} if u else None,
        }
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        if session.is_active: session.rollback()
        current_app.logger.error(f"Kesalahan tak terduga saat mengambil detail transaksi: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)): raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        if session: session.remove()


# --- ENDPOINT /invoice (UNTUK DOWNLOAD MANUAL, TIDAK BERUBAH) ---
@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    # Logika endpoint ini tidak berubah, tetap berfungsi seperti sebelumnya untuk download manual.
    if not WEASYPRINT_AVAILABLE or not HTML_MODULE:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")
    session = db.session
    try:
        transaction = session.query(Transaction).options(selectinload(Transaction.user), selectinload(Transaction.package)).filter(Transaction.midtrans_order_id == midtrans_order_id).first()
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, "Transaksi tidak ditemukan.")
        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, "Anda tidak diizinkan mengakses invoice ini.")
        if transaction.status != TransactionStatus.SUCCESS:
            abort(HTTPStatus.BAD_REQUEST, "Invoice hanya tersedia untuk transaksi yang sudah sukses.")
        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        user_kamar_display = transaction.user.kamar
        if user_kamar_display and user_kamar_display.startswith("Kamar_"):
             user_kamar_display = user_kamar_display.replace("Kamar_", "")
        context = {
            'transaction': transaction, 'user': transaction.user, 'package': transaction.package,
            'user_kamar_value': user_kamar_display,
            'business_name': current_app.config.get('BUSINESS_NAME', 'Nama Bisnis Anda'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Alamat Bisnis Anda'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', 'Telepon Bisnis Anda'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'Email Bisnis Anda'),
            'invoice_date_local': datetime.now(app_tz),
        }
        html_string = render_template('invoice_template.html', **context)
        pdf_bytes = HTML_MODULE(string=html_string, base_url=request.url_root).write_pdf()
        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
        return response
    except Exception as e:
        if session.is_active: session.rollback()
        current_app.logger.error(f"Error saat membuat invoice PDF untuk {midtrans_order_id}: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)): raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session: session.remove()


# --- ENDPOINT BARU UNTUK AKSES INVOICE SEMENTARA DARI WHATSAPP ---
@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    """
    Menyajikan file PDF invoice menggunakan token akses sementara.
    Endpoint ini tidak memerlukan autentikasi @token_required karena token itu sendiri
    adalah bentuk otorisasi yang aman dan berumur pendek.
    """
    if not WEASYPRINT_AVAILABLE or not HTML_MODULE:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    # Verifikasi token. Max age bisa disesuaikan, misal 1 jam (3600 detik)
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
            abort(HTTPStatus.NOT_FOUND, description="Invoice tidak ditemukan atau transaksi belum berhasil.")

        # Logika pembuatan PDF sama persis dengan endpoint get_transaction_invoice
        app_tz = dt_timezone(timedelta(hours=int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))))
        user_kamar_display = transaction.user.kamar
        if user_kamar_display and user_kamar_display.startswith("Kamar_"):
             user_kamar_display = user_kamar_display.replace("Kamar_", "")
        context = {
            'transaction': transaction, 'user': transaction.user, 'package': transaction.package,
            'user_kamar_value': user_kamar_display,
            'business_name': current_app.config.get('BUSINESS_NAME', 'Nama Bisnis Anda'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Alamat Bisnis Anda'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', 'Telepon Bisnis Anda'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'Email Bisnis Anda'),
            'invoice_date_local': datetime.now(app_tz),
        }
        html_string = render_template('invoice_template.html', **context)
        pdf_bytes = HTML_MODULE(string=html_string, base_url=request.url_root).write_pdf()

        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
            
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        # Gunakan 'inline' agar bisa langsung ditampilkan jika dibuka di browser
        response.headers['Content-Disposition'] = f'inline; filename="invoice-{transaction.midtrans_order_id}.pdf"'
        
        current_app.logger.info(f"Invoice sementara untuk order {transaction.midtrans_order_id} berhasil diakses.")
        return response

    except Exception as e:
        if session.is_active: session.rollback()
        current_app.logger.error(f"Error saat membuat invoice sementara PDF untuk token: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session: session.remove()