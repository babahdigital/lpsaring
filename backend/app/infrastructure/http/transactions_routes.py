# backend/app/infrastructure/http/transactions_routes.py
# VERSI FINAL: Memperbaiki alur dengan memanggil service dari GET dan POST secara konsisten.

from flask import Blueprint, request, jsonify, abort, render_template, current_app, make_response
import midtransclient
import uuid
import hashlib
from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from typing import Any, Optional, Dict
import secrets
import string
from http import HTTPStatus
from pydantic import BaseModel, Field, ValidationError
import os # Import os module

from app.extensions import db
from app.infrastructure.db.models import Package, PackageProfile, Transaction, TransactionStatus, User, UserRole, ApprovalStatus, UserBlok, UserKamar
from .decorators import token_required

# Impor service baru
from app.services.transaction_service import apply_package_to_user

# Ketersediaan Klien (Gateway)
try:
    from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user, format_to_local_phone
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    MIKROTIK_CLIENT_AVAILABLE = False
    def get_mikrotik_connection(): return None
    def activate_or_update_hotspot_user(api_connection, user_mikrotik_username: str, mikrotik_profile_name: str, hotspot_password: str, comment:str="", limit_bytes_total:Optional[int]=None, session_timeout_seconds:Optional[int]=None, force_update_profile: bool = False): return False, "Not implemented"
    def format_to_local_phone(phone): return phone

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    def send_whatsapp_message(to, body): return False

WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML, CSS
    HTML_MODULE = HTML
    CSS_MODULE = CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML_MODULE = None
    CSS_MODULE = None
    pass

# Definisikan Blueprint dengan template_folder
transactions_bp = Blueprint(
    'transactions_api',
    __name__,
    url_prefix='/api/transactions',
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../templates')
)

# Fungsi Helper
def format_quota_display(mb_value: Optional[int]) -> str:
    if mb_value is None or mb_value < 0: return "0 MB"
    gb_threshold = 1024
    if mb_value >= gb_threshold:
        gb_value = mb_value / gb_threshold
        if gb_value == int(gb_value): return f"{int(gb_value)} GB"
        return f"{gb_value:.2f} GB".replace('.', ',')
    else: return f"{mb_value} MB"

def get_midtrans_core_api_client():
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    if not server_key: raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    return midtransclient.CoreApi(is_production=is_production, server_key=server_key)

def get_midtrans_snap_client():
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    client_key = current_app.config.get('MIDTRANS_CLIENT_KEY')
    if not server_key or not client_key: raise ValueError("MIDTRANS_SERVER_KEY or MIDTRANS_CLIENT_KEY configuration is missing.")
    return midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)

def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string: return None
    try:
        naive_dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
        offset_hours = int(current_app.config.get('MIDTRANS_DATETIME_INPUT_OFFSET_HOURS', 7))
        return naive_dt.replace(tzinfo=dt_timezone(timedelta(hours=offset_hours))).astimezone(dt_timezone.utc)
    except (ValueError, TypeError): return None

def extract_va_number(response_data: Dict[str, Any]):
    va_numbers = response_data.get('va_numbers')
    if isinstance(va_numbers, list) and len(va_numbers) > 0:
        for va_info in va_numbers:
            if isinstance(va_info, dict) and va_info.get('va_number'): return str(va_info.get('va_number')).strip()
    specific_fields = ['permata_va_number', 'bca_va_number', 'bni_va_number', 'bri_va_number', 'cimb_va_number', 'mandiri_bill_key', 'bill_key', 'payment_code', 'va_number']
    for field in specific_fields:
        if field_value := response_data.get(field): return str(field_value).strip()
    return None

def extract_qr_code_url(response_data: Dict[str, Any]):
    actions = response_data.get('actions')
    if isinstance(actions, list):
        for action in actions:
            action_name = action.get('name', '').lower()
            qr_url = action.get('url')
            if qr_url and 'generate-qr-code' in action_name: return qr_url
    return response_data.get('qr_code_url')

def generate_random_password(length: int = 6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))

# --- Jinja2 Custom Filters ---
# Filter untuk memformat tanggal waktu ke format pendek
def format_datetime_short(value: datetime) -> str:
    if not isinstance(value, datetime):
        return ""
    # Format: 14 Jun 2025, 02:35 WITA
    try:
        # Asumsi waktu yang masuk sudah dalam UTC dan kita ingin mengkonversinya ke WITA (GMT+8)
        # Atau sesuai dengan app_tz yang didefinisikan
        app_tz_offset = int(current_app.config.get('APP_TIMEZONE_OFFSET', 8)) # Default ke 8 untuk WITA
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))

        # Konversi ke zona waktu aplikasi
        local_dt = value.astimezone(app_tz)
        return local_dt.strftime("%d %b %Y, %H:%M WITA")
    except Exception as e:
        current_app.logger.error(f"Error applying format_datetime_short filter: {e}", exc_info=True)
        return "Invalid Date"

# Filter untuk memformat mata uang
def format_currency(value: Any) -> str:
    if value is None:
        return "Rp 0"
    try:
        # Konversi ke Decimal untuk akurasi
        decimal_value = Decimal(value)
        # Format sebagai mata uang Rupiah
        return f"Rp {decimal_value:,.0f}".replace(",", ".") # Mengganti koma dengan titik untuk ribuan
    except Exception as e:
        current_app.logger.error(f"Error applying format_currency filter: {e}", exc_info=True)
        return "Rp Error"

# Filter untuk memformat status transaksi
def format_status(value: str) -> str:
    if not isinstance(value, str):
        return value
    # Mengganti underscore dengan spasi dan mengubah ke title case
    return value.replace('_', ' ').title()

# Daftarkan filter kustom ke Jinja2 environment saat Blueprint dibuat
# (Ini akan berjalan saat aplikasi Flask diinisialisasi dan blueprint ini didaftarkan)
@transactions_bp.app_template_filter('format_datetime_short')
def _format_datetime_short_filter(value):
    return format_datetime_short(value)

@transactions_bp.app_template_filter('format_currency')
def _format_currency_filter(value):
    return format_currency(value)

@transactions_bp.app_template_filter('format_status')
def _format_status_filter(value):
    return format_status(value)

# Skema
class _InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID

class _InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = None
    transaction_id: str
    order_id: str
    redirect_url: Optional[str] = None
    class Config:
        from_attributes = True

# Endpoint /initiate
@transactions_bp.route('/initiate', methods=['POST'])
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    current_app.logger.info(f"POST /api/transactions/initiate - Authenticated user ID: {current_user_id}")
    if not (db and hasattr(db, 'session') and Package and User and Transaction and PackageProfile and get_midtrans_snap_client and get_midtrans_core_api_client and format_to_local_phone and send_whatsapp_message):
        current_app.logger.critical("CRITICAL: Database models, session, or gateway functions are not available for transaction initiation. Check imports and app context.")
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan konfigurasi server. Hubungi administrator.")

    req_data_dict = request.get_json(silent=True) or {}
    try:
        req_data = _InitiateTransactionRequestSchema.model_validate(req_data_dict)
    except ValidationError as e:
        current_app.logger.warning(f"Initiate transaction validation error by user {current_user_id}: {e.errors()}")
        return jsonify({"success": False, "message": "Input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    session = db.session
    order_id = ""
    try:
        user = session.get(User, current_user_id)
        if not user:
            current_app.logger.error(f"User with ID {current_user_id} from token not found in DB for transaction initiation.")
            abort(HTTPStatus.NOT_FOUND, description=f"Pengguna dengan ID {current_user_id} tidak ditemukan.")

        if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            message = "Akun Anda belum aktif atau belum disetujui untuk melakukan transaksi."
            if user.approval_status == ApprovalStatus.PENDING_APPROVAL:
                message = "Akun Anda sedang menunggu persetujuan Admin sebelum dapat melakukan transaksi."
            elif user.approval_status == ApprovalStatus.REJECTED:
                message = "Transaksi tidak dapat dilanjutkan karena akun Anda ditolak."
            current_app.logger.warning(f"Transaction initiation denied for user {current_user_id}. Status: active={user.is_active}, approval={user.approval_status.value if user.approval_status else 'N/A'}")
            abort(HTTPStatus.FORBIDDEN, description=message)

        package = session.query(Package).options(selectinload(Package.profile)).get(req_data.package_id)
        if not package:
            abort(HTTPStatus.NOT_FOUND, description=f"Paket ID {req_data.package_id} tidak ditemukan.")

        if not package.is_active:
            abort(HTTPStatus.BAD_REQUEST, description=f"Paket '{package.name}' tidak aktif.")
        
        if not package.profile:
            current_app.logger.error(f"Package {package.id} ('{package.name}') has no associated profile.")
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Paket '{package.name}' tidak memiliki profil Mikrotik yang valid. Hubungi administrator.")

        user_phone_for_log = getattr(user, 'phone_number', '[Phone Missing]')
        current_app.logger.info(f"Initiating transaction for pkg: {package.name} (ID: {package.id}) by User: {user_phone_for_log} (ID: {current_user_id})...")

        order_id = f"HS-{uuid.uuid4().hex[:12].upper()}"
        transaction_id_internal = uuid.uuid4()

        if package.price is None:
             current_app.logger.error(f"Package {package.id} ('{package.name}') has NULL price.")
             abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Paket '{package.name}' tidak memiliki harga yang valid.")
        
        gross_amount = int(package.price)

        new_transaction = Transaction(
            id=transaction_id_internal,
            user_id=user.id,
            package_id=package.id,
            midtrans_order_id=order_id,
            amount=gross_amount,
            status=TransactionStatus.PENDING
        )

        transaction_details = {'order_id': order_id, 'gross_amount': gross_amount}
        item_details = [{'id': str(package.id), 'price': gross_amount, 'quantity': 1, 'name': package.name[:100]}]
        customer_details = {k: v for k, v in {'first_name': user.full_name or 'Pengguna Hotspot', 'phone': format_to_local_phone(user.phone_number)}.items() if v}

        snap_params: Dict[str, Any] = {'transaction_details': transaction_details, 'item_details': item_details}
        if customer_details: snap_params['customer_details'] = customer_details

        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        finish_url = f"{frontend_url.rstrip('/')}/payment/finish?order_id={order_id}&status=pending"
        snap_params['callbacks'] = {'finish': finish_url}

        current_app.logger.info(f"Requesting Midtrans Snap token for Order ID: {order_id} with amount: {gross_amount}")
        snap = get_midtrans_snap_client()
        snap_response = snap.create_transaction(snap_params)
        current_app.logger.debug(f"Midtrans Snap response for {order_id}: {snap_response}")

        snap_token = snap_response.get('token')
        redirect_url = snap_response.get('redirect_url')

        if not snap_token and not redirect_url:
            current_app.logger.error(f"Midtrans response for {order_id} missing BOTH Snap token and redirect URL.")
            raise ValueError("Respons Midtrans tidak valid (token/URL tidak ditemukan).")

        new_transaction.snap_token = snap_token
        new_transaction.snap_redirect_url = redirect_url

        session.add(new_transaction)
        session.commit()

        current_app.logger.info(f"Transaction {order_id} (Internal ID: {transaction_id_internal}) initiated (PENDING) and saved. Snap Token: {'Yes' if snap_token else 'No'}, Redirect URL: {'Yes' if redirect_url else 'No'}")
        response_data = _InitiateTransactionResponseSchema(snap_token=snap_token or "", transaction_id=str(transaction_id_internal), order_id=order_id, redirect_url=redirect_url)
        return jsonify(response_data.model_dump(exclude_none=True)), HTTPStatus.OK

    except ValueError as ve:
        session.rollback()
        current_app.logger.error(f"Value Error during initiate for {order_id or 'N/A'}: {ve}", exc_info=True)
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description=f"Gateway Pembayaran Error: {ve}")
    except midtransclient.error_midtrans.MidtransAPIError as m_err:
        session.rollback()
        error_message = f"Midtrans API Error: {m_err.message} (HTTP {m_err.http_status_code}). Response: {m_err.api_response_dict}"
        current_app.logger.error(f"Error during Midtrans initiate for {order_id or 'N/A'}: {error_message}", exc_info=False)
        friendly_message = m_err.message if m_err.message and "please usedana" not in m_err.message.lower() else "Terjadi masalah dengan gateway pembayaran."
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description=f"Gateway Pembayaran Error: {friendly_message}")
    except SQLAlchemyError as db_err:
        session.rollback()
        current_app.logger.error(f"DB error during initiate for {order_id or 'N/A'}: {db_err}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan database saat memulai transaksi.")
    except Exception as e:
        session.rollback()
        current_app.logger.error(f"Unexpected error during initiate for {order_id or 'N/A'}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan internal server: {e}")
    finally:
        session.remove()

@transactions_bp.route('/notification', methods=['POST'])
def handle_notification():
    """Menangani notifikasi pembayaran dari Midtrans dengan alur yang disempurnakan."""
    notification_payload = request.get_json(silent=True) or {}
    order_id = notification_payload.get('order_id')
    current_app.logger.info(f"WEBHOOK: Diterima untuk Order ID: {order_id}, Status Midtrans: {notification_payload.get('transaction_status')}")

    # Validasi payload dan signature
    if not all([order_id, notification_payload.get('transaction_status'), notification_payload.get('status_code'), notification_payload.get('gross_amount')]):
        current_app.logger.error(f"WEBHOOK: Payload tidak lengkap untuk {order_id or 'Unknown Order'}.")
        return jsonify({"status": "ok", "message": "Payload tidak lengkap"}), HTTPStatus.OK

    signature_key_payload = notification_payload.get('signature_key')
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    gross_amount_str = notification_payload.get('gross_amount')
    gross_amount_str_for_hash = gross_amount_str if '.' in gross_amount_str else gross_amount_str + '.00'
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode('utf-8')).hexdigest()

    if calculated_signature != signature_key_payload:
        current_app.logger.error(f"WEBHOOK: Signature tidak valid untuk {order_id}.")
        if is_production: return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN
        else: current_app.logger.warning(f"WEBHOOK: Signature mismatch untuk {order_id} di non-production. Tetap proses...")
    else: current_app.logger.info(f"WEBHOOK: Signature terverifikasi untuk {order_id}")

    session = db.session
    try:
        transaction = session.query(Transaction).options(
            selectinload(Transaction.user),
            selectinload(Transaction.package).selectinload(Package.profile)
        ).filter(Transaction.midtrans_order_id == order_id).with_for_update().first()

        if not transaction:
            current_app.logger.warning(f"WEBHOOK: Transaksi {order_id} tidak ditemukan. Diabaikan.")
            return jsonify({"status": "ok"}), HTTPStatus.OK

        # Cek jika transaksi sudah final
        if transaction.status in [TransactionStatus.SUCCESS, TransactionStatus.FAILED, TransactionStatus.EXPIRED, TransactionStatus.CANCELLED]:
            current_app.logger.info(f"WEBHOOK: Transaksi {order_id} sudah dalam status final ({transaction.status.value}). Diabaikan.")
            return jsonify({"status": "ok"}), HTTPStatus.OK

        # Update status transaksi berdasarkan notifikasi Midtrans
        new_status_enum, payment_success = transaction.status, False
        midtrans_status = notification_payload.get('transaction_status')
        fraud_status = notification_payload.get('fraud_status')

        if midtrans_status in ['capture', 'settlement'] and fraud_status == 'accept':
            new_status_enum, payment_success = TransactionStatus.SUCCESS, True
        elif midtrans_status == 'pending': new_status_enum = TransactionStatus.PENDING
        elif midtrans_status == 'deny': new_status_enum = TransactionStatus.FAILED
        elif midtrans_status == 'expire': new_status_enum = TransactionStatus.EXPIRED
        elif midtrans_status == 'cancel': new_status_enum = TransactionStatus.CANCELLED
        
        transaction.status = new_status_enum
        transaction.payment_method = notification_payload.get('payment_type')
        transaction.midtrans_transaction_id = notification_payload.get('transaction_id')
        transaction.payment_time = safe_parse_midtrans_datetime(notification_payload.get('settlement_time') or notification_payload.get('transaction_time'))
        transaction.va_number = extract_va_number(notification_payload)
        transaction.payment_code = notification_payload.get('payment_code') or notification_payload.get('bill_key')

        # Alur proses jika pembayaran SUKSES
        if payment_success and new_status_enum == TransactionStatus.SUCCESS:
            current_app.logger.info(f"WEBHOOK: Pembayaran SUKSES untuk {order_id}. Memulai proses penerapan paket.")

            # LANGKAH 1: Panggil service untuk menerapkan logika bisnis ke objek user
            package_applied = apply_package_to_user(transaction)
            
            if not package_applied:
                current_app.logger.error(f"WEBHOOK: Service 'apply_package_to_user' GAGAL untuk TX {order_id}. Rollback.")
                session.rollback()
                return jsonify({"status": "error", "message": "Gagal menerapkan logika paket"}), HTTPStatus.INTERNAL_SERVER_ERROR

            # LANGKAH 2 (KRUSIAL): Commit perubahan status transaksi DAN status pengguna ke database SEKARANG.
            try:
                current_app.logger.info(f"WEBHOOK: Melakukan commit perubahan user dan transaksi untuk TX {order_id} ke database...")
                session.commit()
                current_app.logger.info(f"WEBHOOK: Commit BERHASIL. User {transaction.user.id} kini resmi { 'UNLIMITED' if transaction.user.is_unlimited_user else 'BERKUOTA' } di database.")
            except SQLAlchemyError as e_commit:
                current_app.logger.error(f"WEBHOOK: Gagal melakukan commit data utama untuk TX {order_id}: {e_commit}", exc_info=True)
                session.rollback()
                return jsonify({"status": "error", "message": "Gagal menyimpan data utama ke database"}), HTTPStatus.INTERNAL_SERVER_ERROR

            # LANGKAH 3: Lanjutkan dengan sinkronisasi ke Mikrotik, kirim notifikasi, dll.
            # Data user, package, dan profile sudah paling update dari DB.
            user = transaction.user
            package = transaction.package
            package_profile = package.profile

            # Pastikan data relasi ada
            if not user or not package or not package_profile:
                current_app.logger.error(f"WEBHOOK: Data user/paket/profil hilang setelah commit untuk TX {order_id}.")
                # Tidak perlu rollback karena data utama sudah masuk. Ini adalah error state yang perlu diinvestigasi.
                return jsonify({"status": "ok", "message": "Data utama tersimpan, tapi data relasi hilang"}), HTTPStatus.OK

            # Generate password baru jika perlu dan simpan ke transaksi
            password_untuk_mikrotik = user.mikrotik_password
            if not password_untuk_mikrotik or not (len(password_untuk_mikrotik) == 6 and password_untuk_mikrotik.isdigit()):
                password_untuk_mikrotik = generate_random_password()
                user.mikrotik_password = password_untuk_mikrotik # Simpan juga di user
            transaction.hotspot_password = password_untuk_mikrotik

            # LANGKAH 4: Sinkronisasi ke Mikrotik menggunakan data yang SUDAH di-commit.
            hotspot_username_for_mt = format_to_local_phone(user.phone_number)
            if MIKROTIK_CLIENT_AVAILABLE and hotspot_username_for_mt and user.is_active and user.approval_status == ApprovalStatus.APPROVED:
                with get_mikrotik_connection() as api_conn:
                    if api_conn:
                        # Ambil nilai FINAL dari objek user yang sudah ter-update
                        limit_bytes = 0 if user.is_unlimited_user else int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
                        timeout_sec = max(0, int((user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds())) if user.quota_expiry_date else 0
                        
                        current_app.logger.info(f"WEBHOOK: Sinkronisasi ke Mikrotik untuk user '{hotspot_username_for_mt}'. Profil: {package_profile.profile_name}, Limit Bytes: {limit_bytes}, Timeout: {timeout_sec}s.")
                        
                        success_mt, msg_mt = activate_or_update_hotspot_user(
                            api_connection=api_conn,
                            user_mikrotik_username=hotspot_username_for_mt,
                            mikrotik_profile_name=package_profile.profile_name,
                            hotspot_password=password_untuk_mikrotik,
                            comment=f"Order:{order_id}",
                            limit_bytes_total=limit_bytes,
                            session_timeout_seconds=timeout_sec,
                            force_update_profile=True
                        )
                        if not success_mt:
                            current_app.logger.error(f"WEBHOOK: SINKRONISASI MIKROTIK GAGAL untuk {hotspot_username_for_mt}. Pesan: {msg_mt}. Data di DB sudah terupdate, perlu cek manual.")
            
            # Commit terakhir untuk menyimpan password jika ada perubahan
            session.commit()
        
        else: # Jika status bukan success (pending, failed, dll)
            session.commit()

        return jsonify({"status": "ok"}), HTTPStatus.OK

    except Exception as e:
        if session.is_active: session.rollback()
        current_app.logger.error(f"WEBHOOK: Error tidak terduga untuk {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        if session:
            session.remove()


# Endpoint /by-order-id (Lengkap dengan Perbaikan Final)
@transactions_bp.route('/by-order-id/<string:order_id>', methods=['GET'])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    if not current_user_id: abort(HTTPStatus.UNAUTHORIZED, description="ID User tidak valid.")
    current_app.logger.info(f"GET /api/transactions/by-order-id/{order_id} requested by user ID: {current_user_id}.")
    
    session = db.session
    try:
        # Mengambil data user yang meminta dan data transaksi dalam satu blok
        requesting_user = session.get(User, current_user_id)
        if not requesting_user: abort(HTTPStatus.UNAUTHORIZED, description="Pengguna peminta tidak ditemukan.")

        transaction = session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).options(selectinload(Transaction.user), selectinload(Transaction.package).selectinload(Package.profile)).first()
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        # Otorisasi: hanya pemilik atau admin yang boleh melihat
        if not (transaction.user_id == current_user_id or requesting_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]):
            current_app.logger.warning(f"Unauthorized attempt to access transaction {order_id} by user {current_user_id} (Role: {requesting_user.role.value if requesting_user.role else 'N/A'}).")
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan melihat detail transaksi ini.")

        # Cek jika transaksi masih PENDING di DB, coba sinkronkan dengan Midtrans
        if transaction.status == TransactionStatus.PENDING:
            current_app.logger.info(f"GET Detail: Transaction {order_id} is PENDING in DB, checking status with Midtrans...")
            try:
                core_api = get_midtrans_core_api_client()
                midtrans_status_response: Dict[str, Any] = core_api.transactions.status(order_id)
                
                midtrans_trx_status = midtrans_status_response.get('transaction_status')
                fraud_status = midtrans_status_response.get('fraud_status')
                payment_success = False

                if midtrans_trx_status in ['capture', 'settlement'] and fraud_status == 'accept':
                    payment_success = True

                # Jika pembayaran sukses, proses seluruh alur bisnis
                if payment_success:
                    current_app.logger.info(f"GET Detail: Pembayaran SUKSES untuk {order_id} terdeteksi. Memulai proses penerapan paket...")
                    
                    # Update status dan detail transaksi
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.payment_method = midtrans_status_response.get('payment_type')
                    transaction.midtrans_transaction_id = midtrans_status_response.get('transaction_id')
                    payment_timestamp_str = midtrans_status_response.get('settlement_time') or midtrans_status_response.get('transaction_time')
                    transaction.payment_time = safe_parse_midtrans_datetime(payment_timestamp_str) or datetime.now(dt_timezone.utc)
                    transaction.va_number = extract_va_number(midtrans_status_response)
                    transaction.payment_code = midtrans_status_response.get('payment_code') or midtrans_status_response.get('bill_key')
                    transaction.biller_code = midtrans_status_response.get('biller_code') # Pastikan field ini ada
                    transaction.qr_code_url = extract_qr_code_url(midtrans_status_response)
                    
                    # Panggil service untuk menerapkan manfaat paket
                    package_applied = apply_package_to_user(transaction)
                    if not package_applied:
                        current_app.logger.error(f"GET Detail: Service 'apply_package_to_user' GAGAL untuk TX {order_id}. Rollback.")
                        session.rollback()
                        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menerapkan logika paket")
                    
                    # Commit semua perubahan (transaksi dan user) ke DB
                    session.commit()
                    current_app.logger.info(f"GET Detail: Perubahan untuk transaksi {order_id} berhasil di-commit dari alur GET.")

                    # Lakukan sinkronisasi ke Mikrotik (opsional, untuk respons instan)
                    # Data user, package, dan profile sudah paling update dari DB.
                    user = transaction.user
                    package = transaction.package
                    package_profile = package.profile

                    if MIKROTIK_CLIENT_AVAILABLE and user and user.phone_number and user.is_active and user.approval_status == ApprovalStatus.APPROVED and package_profile:
                        hotspot_username_for_mt = format_to_local_phone(user.phone_number)
                        with get_mikrotik_connection() as api_conn:
                            if api_conn:
                                limit_bytes = 0 if user.is_unlimited_user else int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
                                timeout_sec = max(0, int((user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds())) if user.quota_expiry_date else 0
                                
                                current_app.logger.info(f"GET Detail: Sinkronisasi ke Mikrotik untuk user '{hotspot_username_for_mt}'. Profil: {package_profile.profile_name}, Limit Bytes: {limit_bytes}, Timeout: {timeout_sec}s.")
                                
                                success_mt, msg_mt = activate_or_update_hotspot_user(
                                    api_connection=api_conn,
                                    user_mikrotik_username=hotspot_username_for_mt,
                                    mikrotik_profile_name=package_profile.profile_name,
                                    hotspot_password=user.mikrotik_password, # Gunakan password yang sudah ada di user
                                    comment=f"Order:{order_id}",
                                    limit_bytes_total=limit_bytes,
                                    session_timeout_seconds=timeout_sec,
                                    force_update_profile=True
                                )
                                if not success_mt:
                                    current_app.logger.error(f"GET Detail: SINKRONISASI MIKROTIK GAGAL untuk {hotspot_username_for_mt}. Pesan: {msg_mt}. Data di DB sudah terupdate, perlu cek manual.")
                    # Commit terakhir untuk menyimpan password jika ada perubahan (jika generate_random_password dipanggil di service atau di sini)
                    session.commit()


                elif midtrans_trx_status == 'pending':
                    current_app.logger.debug(f"GET Detail: Masih PENDING untuk {order_id}. Memperbarui detail pembayaran dari API Midtrans.")
                    # Memperbarui detail pembayaran lainnya jika transaksi masih PENDING
                    details_to_check_and_update = {
                        'expiry_time': safe_parse_midtrans_datetime(midtrans_status_response.get('expiry_time')),
                        'va_number': extract_va_number(midtrans_status_response),
                        'payment_code': midtrans_status_response.get('payment_code') or midtrans_status_response.get('bill_key'),
                        'biller_code': midtrans_status_response.get('biller_code'),
                        'qr_code_url': extract_qr_code_url(midtrans_status_response)
                    }
                    update_db_needed_for_pending = False
                    for attr, new_value_from_api in details_to_check_and_update.items():
                        if hasattr(transaction, attr):
                            current_db_value = getattr(transaction, attr)
                            if (new_value_from_api is not None and new_value_from_api != "" and new_value_from_api != current_db_value) or (current_db_value is None and new_value_from_api is not None and new_value_from_api != ""):
                                setattr(transaction, attr, new_value_from_api)
                                update_db_needed_for_pending = True
                                current_app.logger.info(f"GET Detail: Diperbarui '{attr}' untuk transaksi PENDING {order_id} dari API Midtrans. Lama: '{current_db_value}', Baru: '{new_value_from_api}'")
                    if update_db_needed_for_pending:
                        session.commit()
                        current_app.logger.info(f"GET Detail: Detail transaksi PENDING {order_id} diperbarui dan di-commit di DB dari API status GET.")

                else: # Jika status bukan SUCCESS atau PENDING, update status transaksi saja
                    new_status_enum_get = TransactionStatus.PENDING # Default, akan di-override jika ada status final
                    if midtrans_trx_status == 'deny': new_status_enum_get = TransactionStatus.FAILED
                    elif midtrans_trx_status == 'expire': new_status_enum_get = TransactionStatus.EXPIRED
                    elif midtrans_trx_status == 'cancel': new_status_enum_get = TransactionStatus.CANCELLED
                    
                    if new_status_enum_get != transaction.status:
                        current_app.logger.info(f"GET Detail: Status untuk {order_id} diperbarui via cek Midtrans: {transaction.status.value} -> {new_status_enum_get.value}")
                        transaction.status = new_status_enum_get
                        session.commit()
                        current_app.logger.info(f"GET Detail: Status transaksi {order_id} di-commit di DB dari API status GET.")

            except midtransclient.error_midtrans.MidtransAPIError as midtrans_err:
                if midtrans_err.http_status_code == HTTPStatus.NOT_FOUND:
                    current_app.logger.warning(f"GET Detail: Midtrans GET Status API mengembalikan 404 untuk PENDING {order_id}. Transaksi mungkin terlalu lama atau tidak valid. Mempertahankan status PENDING.", exc_info=False)
                else:
                    current_app.logger.error(f"GET Detail: Error saat cek status Midtrans untuk PENDING {order_id}: {midtrans_err.message}", exc_info=True)
            except Exception as e_check_status:
                current_app.logger.error(f"GET Detail: Error tak terduga saat cek status Midtrans untuk PENDING {order_id}: {e_check_status}", exc_info=True)
        
        # Reload transaksi dari DB untuk mendapatkan data ter-update
        session.refresh(transaction)

        # Mengembalikan data JSON yang lengkap
        response_data = {
            "id": str(transaction.id),
            "midtrans_order_id": transaction.midtrans_order_id,
            "midtrans_transaction_id": transaction.midtrans_transaction_id,
            "status": transaction.status.value if transaction.status else TransactionStatus.UNKNOWN.value,
            "amount": float(transaction.amount) if transaction.amount is not None else 0.0,
            "payment_method": transaction.payment_method,
            "payment_time": transaction.payment_time.isoformat() if transaction.payment_time else None,
            "expiry_time": transaction.expiry_time.isoformat() if transaction.expiry_time else None,
            "va_number": transaction.va_number,
            "payment_code": transaction.payment_code,
            "biller_code": getattr(transaction, 'biller_code', None),
            "qr_code_url": transaction.qr_code_url,
            "hotspot_password": transaction.hotspot_password,
            "package": {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "price": float(p.price) if p.price is not None else 0.0,
                "data_quota_gb": float(p.data_quota_gb) if p.data_quota_gb is not None else 0.0,
                "is_unlimited": (p.data_quota_gb == 0) 
            } if (p := transaction.package) else None,
            "user": {
                "id": str(u.id),
                "phone_number": u.phone_number,
                "full_name": u.full_name,
                "quota_expiry_date": u.quota_expiry_date.isoformat() if u.quota_expiry_date else None,
                "is_unlimited_user": u.is_unlimited_user
            } if (u := transaction.user) else None,
        }
        current_app.logger.info(f"GET Detail: Returning details for {order_id}, final status from DB: {transaction.status.value if transaction.status else 'N/A'}.")
        return jsonify(response_data), HTTPStatus.OK
    except SQLAlchemyError as e_main_sql:
        current_app.logger.error(f"GET Detail: DB error getting transaction {order_id}: {e_main_sql}", exc_info=True)
        if session and session.is_active: session.rollback()
        return jsonify({"success": False, "message": "Kesalahan database saat mengambil transaksi."}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e_main_exc:
        status_code_resp = getattr(e_main_exc, 'code', HTTPStatus.INTERNAL_SERVER_ERROR)
        description_resp = getattr(e_main_exc, 'description', "Terjadi kesalahan internal server.")
        if status_code_resp != HTTPStatus.INTERNAL_SERVER_ERROR:
             current_app.logger.warning(f"GET Detail: Request aborted for {order_id}. Code: {status_code_resp}, Desc: {description_resp}")
        else:
             current_app.logger.error(f"GET Detail: Unexpected error processing GET /by-order-id/{order_id}: {e_main_exc}", exc_info=True)
        if session and session.is_active:
            session.rollback()
        return jsonify({'success': False, 'message': description_resp}), status_code_resp
    finally:
        if session:
             session.remove()

# Endpoint /invoice (Lengkap)
@transactions_bp.route('/<string:midtrans_order_id>/invoice', methods=['GET'])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    current_app.logger.info(f"GET /api/transactions/{midtrans_order_id}/invoice requested by user ID: {current_user_id}")
    session = db.session
    if not WEASYPRINT_AVAILABLE or not HTML_MODULE:
        current_app.logger.error("WEASYPRINT IMPORT ERROR: WeasyPrint tidak terinstal atau tidak dapat diimpor. Pembuatan PDF invoice tidak akan berfungsi.")
        return jsonify({"success": False, "message": "Gagal membuat PDF invoice (komponen server tidak tersedia)."}), HTTPStatus.NOT_IMPLEMENTED
    if not (db and hasattr(db, 'session') and User and Transaction and Package and PackageProfile):
        current_app.logger.error("CRITICAL: Database models or session not available for invoice generation.")
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Kesalahan konfigurasi server (model/database).")
    try:
        requesting_user = session.get(User, current_user_id)
        if not requesting_user:
            return jsonify({"success": False, "message": "Pengguna dari token tidak valid."}), HTTPStatus.UNAUTHORIZED

        transaction = session.query(Transaction).options(selectinload(Transaction.user),selectinload(Transaction.package).selectinload(Package.profile)).filter(Transaction.midtrans_order_id == midtrans_order_id).first()
        if not transaction:
            return jsonify({"success": False, "message": f"Transaksi dengan Order ID {midtrans_order_id} tidak ditemukan."}), HTTPStatus.NOT_FOUND

        is_owner = transaction.user_id == current_user_id
        is_admin_role_invoice = requesting_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        if not is_owner and not is_admin_role_invoice:
            current_app.logger.warning(f"Unauthorized attempt to access invoice {midtrans_order_id} by user {current_user_id} (Role: {requesting_user.role.value if requesting_user.role else 'N/A'}).")
            return jsonify({"success": False, "message": "Anda tidak memiliki izin untuk mengakses invoice ini."}), HTTPStatus.FORBIDDEN

        allowed_status_for_invoice = TransactionStatus.SUCCESS
        if transaction.status != allowed_status_for_invoice:
            message = f"Invoice hanya tersedia untuk transaksi dengan status '{allowed_status_for_invoice.value}'. Status saat ini: '{transaction.status.value if transaction.status else 'N/A'}'."
            current_app.logger.info(f"Invoice download denied for {midtrans_order_id}. {message}")
            return jsonify({"success": False, "message": message}), HTTPStatus.BAD_REQUEST

        app_tz_offset = int(current_app.config.get('APP_TIMEZONE_OFFSET', 7))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))

        user_data = transaction.user
        package_data = transaction.package
        package_profile_data = package_data.profile

        if not user_data or not package_data or not package_profile_data:
            current_app.logger.error(f"Invoice generation failed for {midtrans_order_id}: User, Package, or Package Profile data is missing from transaction object.")
            return jsonify({"success": False, "message": "Data pengguna, paket, atau profil paket tidak lengkap untuk generate invoice."}), HTTPStatus.INTERNAL_SERVER_ERROR

        user_blok_display = user_data.blok if user_data.blok else '-'
        user_kamar_display = user_data.kamar if user_data.kamar else '-'
        if user_kamar_display.startswith("Kamar_") and user_kamar_display[6:].isdigit():
            user_kamar_display = user_kamar_display[6:]

        context = {
            'transaction': transaction,
            'user': user_data,
            'package': package_data,
            'package_profile': package_profile_data,
            'user_blok_value': user_blok_display,
            'user_kamar_value': user_kamar_display,
            'business_name': current_app.config.get('BUSINESS_NAME', 'Portal Hotspot XYZ'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Jl. Internet Cepat No. 1, Kota Digital'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', '0812-3456-7890'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'admin@portalhotspot.xyz'),
            'invoice_date_local': datetime.now(app_tz),
            'transaction_time_local': transaction.created_at.astimezone(app_tz) if transaction.created_at else None,
            'payment_time_local': transaction.payment_time.astimezone(app_tz) if transaction.payment_time else None,
        }

        template_path = 'invoice_template.html'
        try:
            current_app.logger.debug(f"Rendering template '{template_path}' for invoice {midtrans_order_id}...")
            html_string = render_template(template_path, **context)
            current_app.logger.debug(f"HTML (length: {len(html_string)}) rendered for invoice {midtrans_order_id}. Generating PDF...")
            pdf_bytes = HTML_MODULE(string=html_string, base_url=request.url_root).write_pdf()

            if not pdf_bytes or len(pdf_bytes) == 0:
                current_app.logger.error(f"Generated PDF bytes are empty for invoice {midtrans_order_id} after write_pdf(). HTML content was (first 500 chars): {html_string[:500]}")
                return jsonify({"success": False, "message": "Gagal menghasilkan file PDF (hasil konversi kosong atau tidak valid)."}), HTTPStatus.INTERNAL_SERVER_ERROR

            current_app.logger.info(f"Invoice {midtrans_order_id}: PDF generated successfully. PDF length: {len(pdf_bytes)} bytes.")
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
            return response

        except Exception as render_err:
            current_app.logger.error(f"Error saat rendering template atau konversi ke PDF untuk invoice {midtrans_order_id}: {render_err}", exc_info=True)
            return jsonify({"success": False, "message": f"Gagal memproses pembuatan invoice: {str(render_err)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e_invoice_main:
        status_code_inv_main = getattr(e_invoice_main, 'code', HTTPStatus.INTERNAL_SERVER_ERROR)
        description_inv_main = getattr(e_invoice_main, 'description', "Terjadi kesalahan internal server saat memproses invoice.")
        if status_code_inv_main != HTTPStatus.INTERNAL_SERVER_ERROR:
             current_app.logger.warning(f"Invoice request for {midtrans_order_id} aborted. Code: {status_code_inv_main}, Desc: {description_inv_main}")
        else:
             current_app.logger.error(f"Unexpected error processing GET /transactions/{midtrans_order_id}/invoice: {e_invoice_main}", exc_info=True)
        if session and session.is_active:
            session.rollback()
        return jsonify({'success': False, 'message': description_inv_main}), status_code_inv_main
    finally:
        if session:
             session.remove()