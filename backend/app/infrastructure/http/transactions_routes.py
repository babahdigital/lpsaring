# backend/app/infrastructure/http/transactions_routes.py
# VERSI FINAL: Disesuaikan dengan Model A (Paket Fleksibel) dan perbaikan logika.
# PERBAIKAN: Penanganan blok/kamar di invoice generation untuk konsistensi string.

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
from http import HTTPStatus # Pastikan HTTPStatus diimpor

from app.extensions import db
from app.infrastructure.db.models import Package, PackageProfile, Transaction, TransactionStatus, User, UserRole, ApprovalStatus, UserBlok, UserKamar # Import UserBlok, UserKamar
from .decorators import token_required
from app.services.notification_service import get_notification_message

# --- Ketersediaan Klien (Gateway) ---
# Impor modul Mikrotik dan WhatsApp, serta sediakan placeholder jika tidak tersedia
try:
    from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user, format_to_local_phone
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    MIKROTIK_CLIENT_AVAILABLE = False
    # Placeholder functions untuk menghindari NameError jika import gagal
    def get_mikrotik_connection(): return None # type: ignore
    def activate_or_update_hotspot_user(api_connection, user_mikrotik_username: str, mikrotik_profile_name: str, hotspot_password: str, comment:str="", limit_bytes_total:Optional[int]=None, session_timeout_seconds:Optional[int]=None, force_update_profile: bool = False): return False, "Not implemented (Mikrotik client not available)" # type: ignore
    def format_to_local_phone(phone): return phone # type: ignore

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    # Placeholder function jika import gagal
    def send_whatsapp_message(to, body): return False # type: ignore

# Optional import for WeasyPrint for invoice generation
WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML, CSS
    HTML_MODULE = HTML
    CSS_MODULE = CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML_MODULE = None
    CSS_MODULE = None
    pass # Log warning in the invoice endpoint itself

transactions_bp = Blueprint('transactions_api', __name__, url_prefix='/api/transactions')

# --- Helper Functions ---
def format_quota_display(mb_value: Optional[int]) -> str:
    """Format nilai kuota dari MB ke GB atau MB."""
    if mb_value is None or mb_value < 0:
        return "0 MB"
    gb_threshold = 1024
    if mb_value >= gb_threshold:
        gb_value = mb_value / gb_threshold
        # Tampilkan sebagai integer GB jika tidak ada desimal, jika ada tampilkan 2 desimal
        if gb_value == int(gb_value):
            return f"{int(gb_value)} GB"
        return f"{gb_value:.2f} GB".replace('.', ',') # Gunakan koma untuk desimal
    else:
        return f"{mb_value} MB"

def get_midtrans_core_api_client() -> midtransclient.CoreApi:
    """Menginisialisasi klien Midtrans Core API. Akses current_app di dalam fungsi."""
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    if not server_key:
        current_app.logger.critical("FATAL: MIDTRANS_SERVER_KEY configuration is missing!")
        raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    return midtransclient.CoreApi(is_production=is_production, server_key=server_key)


def get_midtrans_snap_client() -> midtransclient.Snap:
    """Menginisialisasi klien Midtrans Snap API. Akses current_app di dalam fungsi."""
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    client_key = current_app.config.get('MIDTRANS_CLIENT_KEY')
    if not server_key or not client_key:
        current_app.logger.critical("FATAL: MIDTRANS_SERVER_KEY or MIDTRANS_CLIENT_KEY configuration is missing!")
        raise ValueError("MIDTRANS_SERVER_KEY or MIDTRANS_CLIENT_KEY configuration is missing.")
    return midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)

def safe_parse_midtrans_datetime(dt_string: Optional[str]) -> Optional[datetime]:
    """Menguraikan string datetime dari Midtrans ke objek datetime UTC. Akses current_app di dalam fungsi."""
    if not dt_string or not isinstance(dt_string, str): return None
    try:
        naive_dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
        # Asumsi Midtrans mengembalikan waktu dalam zona waktu UTC+7 (WIB).
        # Konversi ke UTC untuk konsistensi database.
        offset_hours = int(current_app.config.get('MIDTRANS_DATETIME_INPUT_OFFSET_HOURS', 7))
        local_tz = dt_timezone(timedelta(hours=offset_hours))
        aware_dt_local = naive_dt.replace(tzinfo=local_tz)
        return aware_dt_local.astimezone(dt_timezone.utc)
    except (ValueError, TypeError) as e:
        current_app.logger.warning(f"Failed to parse Midtrans datetime string '{dt_string}': {e}", exc_info=False)
        return None

def extract_va_number(response_data: Dict[str, Any]) -> Optional[str]:
    """Mengekstrak nomor VA dari respons Midtrans."""
    va_numbers = response_data.get('va_numbers')
    if isinstance(va_numbers, list) and len(va_numbers) > 0:
        for va_info in va_numbers:
            if isinstance(va_info, dict) and va_info.get('va_number'):
                 return str(va_info.get('va_number')).strip()
    # Field khusus untuk bank tertentu atau metode lain
    specific_fields = [
        'permata_va_number', 'bca_va_number', 'bni_va_number', 'bri_va_number',
        'cimb_va_number', 'mandiri_bill_key', 'bill_key', 'payment_code', 'va_number' # 'va_number' general field
    ]
    for field in specific_fields:
        if field_value := response_data.get(field):
            return str(field_value).strip()
    return None

def extract_qr_code_url(response_data: Dict[str, Any]) -> Optional[str]:
    """Mengekstrak URL QR code dari respons Midtrans."""
    actions = response_data.get('actions')
    if isinstance(actions, list):
        for action in actions:
            action_name = action.get('name', '').lower()
            qr_url = action.get('url')
            if qr_url and isinstance(qr_url, str):
                # Cari action yang relevan untuk QR
                if 'generate-qris-string' in action_name or 'generate-qr-code' in action_name or 'qris' in action_name:
                    return qr_url
    # Beberapa pembayaran QR mungkin memiliki URL di tingkat atas
    if qr_top_level := response_data.get('qr_code_url'):
         return qr_top_level
    return None

def generate_random_password(length: int = 6) -> str:
    """Menghasilkan password acak hanya angka."""
    if length < 6: length = 6
    characters = string.digits
    password = ''.join(secrets.choice(characters) for _ in range(length))
    return password

# --- Schemas (Pydantic) ---
from pydantic import BaseModel, Field, ValidationError # Pydantic imports added for completeness

class _InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID

class _InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = None
    transaction_id: str
    order_id: str
    redirect_url: Optional[str] = None
    
    class Config:
        from_attributes = True


# --- Endpoints ---

@transactions_bp.route('/initiate', methods=['POST'])
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    """Memulai transaksi baru dengan Midtrans."""
    current_app.logger.info(f"POST /api/transactions/initiate - Authenticated user ID: {current_user_id}")

    # Memastikan bahwa semua objek yang dibutuhkan (db, model, dan fungsi gateway) sudah ada
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
        
        # Memuat package dengan profilnya
        package = session.query(Package).options(selectinload(Package.profile)).get(req_data.package_id)

        if not package: 
            abort(HTTPStatus.NOT_FOUND, description=f"Paket ID {req_data.package_id} tidak ditemukan.")
        if not package.is_active: 
            abort(HTTPStatus.BAD_REQUEST, description=f"Paket '{package.name}' tidak aktif.")
        
        # Pastikan package memiliki profile yang valid
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
        gross_amount = int(package.price) # Menggunakan int untuk harga, sesuaikan jika perlu Decimal

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
        
        # Coba buat transaksi Midtrans
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
        session.remove() # Pastikan sesi dihapus

@transactions_bp.route('/notification', methods=['POST'])
def handle_notification():
    """Menangani notifikasi pembayaran dari Midtrans."""
    notification_payload = request.get_json(silent=True) or {}
    order_id = notification_payload.get('order_id')
    
    current_app.logger.info(f"WEBHOOK: Received for Order ID: {order_id}, Midtrans Status: {notification_payload.get('transaction_status')}, Type: {notification_payload.get('payment_type')}, Code: {notification_payload.get('status_code')}")
    current_app.logger.debug(f"WEBHOOK: Full payload for {order_id}: {notification_payload}")

    if not all([order_id, notification_payload.get('transaction_status'), notification_payload.get('status_code'), notification_payload.get('gross_amount')]):
        current_app.logger.error(f"WEBHOOK: Incomplete payload for {order_id or 'Unknown Order'}. Missing required fields.")
        return jsonify({"status": "ok", "message": "Incomplete payload, notification acknowledged"}), HTTPStatus.OK

    # Validasi signature Midtrans
    signature_key_payload = notification_payload.get('signature_key')
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY')
    is_production = current_app.config.get('MIDTRANS_IS_PRODUCTION', False)
    gross_amount_str = notification_payload.get('gross_amount')
    gross_amount_str_for_hash = gross_amount_str if '.' in gross_amount_str else gross_amount_str + '.00'
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_payload_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode('utf-8')).hexdigest()

    if calculated_signature != signature_key_payload:
        current_app.logger.error(f"WEBHOOK: Invalid signature for {order_id}. Calculated: {calculated_signature}, Received: {signature_key_payload}")
        if is_production: return jsonify({"status": "error", "message": "Invalid signature"}), HTTPStatus.FORBIDDEN
        else: current_app.logger.warning(f"WEBHOOK: Signature mismatch for {order_id} in non-production. Processing anyway...")
    else: current_app.logger.info(f"WEBHOOK: Signature verified successfully for {order_id}")

    session = db.session
    try:
        # Load transaction with user and package (including profile) for atomic update
        transaction = session.query(Transaction)\
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.package).selectinload(Package.profile)
            )\
            .filter(Transaction.midtrans_order_id == order_id)\
            .with_for_update(of=[Transaction])\
            .first()

        if not transaction:
            current_app.logger.warning(f"WEBHOOK: Transaction {order_id} not found in DB. Ignoring.")
            session.commit() # Release lock if acquired
            return jsonify({"status": "ok", "message": "Transaction not found, notification acknowledged."}), HTTPStatus.OK

        # Cek apakah transaksi sudah dalam status final
        final_statuses = [TransactionStatus.SUCCESS, TransactionStatus.FAILED, TransactionStatus.EXPIRED, TransactionStatus.CANCELLED]
        if transaction.status in final_statuses:
            current_app.logger.info(f"WEBHOOK: Transaction {order_id} (ID: {transaction.id}) already in final state ({transaction.status.value}). Ignoring new notification.")
            session.commit() # Release lock
            return jsonify({"status": "ok", "message": f"Transaction already {transaction.status.value}"}), HTTPStatus.OK

        # Tentukan status transaksi baru berdasarkan notifikasi Midtrans
        new_status_enum = transaction.status # Default to current status
        payment_success = False
        fraud_status = notification_payload.get('fraud_status')
        midtrans_transaction_status = notification_payload.get('transaction_status')
        midtrans_trx_id = notification_payload.get('transaction_id')
        payment_type_notif = notification_payload.get('payment_type')

        # Logic to determine new_status_enum and payment_success based on Midtrans notification
        if midtrans_transaction_status == 'capture':
            if fraud_status == 'accept': new_status_enum, payment_success = TransactionStatus.SUCCESS, True
            elif fraud_status == 'challenge': new_status_enum = TransactionStatus.PENDING # Perlu diverifikasi admin
            elif fraud_status == 'deny': new_status_enum = TransactionStatus.FAILED
        elif midtrans_transaction_status == 'settlement': new_status_enum, payment_success = TransactionStatus.SUCCESS, True
        elif midtrans_transaction_status == 'pending': new_status_enum = TransactionStatus.PENDING
        elif midtrans_transaction_status == 'deny': new_status_enum = TransactionStatus.FAILED
        elif midtrans_transaction_status == 'expire': new_status_enum = TransactionStatus.EXPIRED
        elif midtrans_transaction_status == 'cancel': new_status_enum = TransactionStatus.CANCELLED
        else:
            current_app.logger.warning(f"WEBHOOK: Unhandled Midtrans status '{midtrans_transaction_status}' for {order_id}. Keeping current status: {transaction.status.value}.")

        # Check if status has changed OR if it's a pending notification with new transaction ID
        status_changed = new_status_enum != transaction.status

        # If payment is successful AND the transaction was not already success (to prevent double processing)
        if payment_success and transaction.status != TransactionStatus.SUCCESS:
            current_app.logger.info(f"WEBHOOK: Payment success for {order_id}. Processing user and package data.")
            
            # Update transaction status to SUCCESS
            transaction.status = new_status_enum # Should be TransactionStatus.SUCCESS
            transaction.payment_method = payment_type_notif # Update payment method
            transaction.midtrans_transaction_id = midtrans_trx_id # Update Midtrans transaction ID
            payment_timestamp_str = notification_payload.get('settlement_time') or notification_payload.get('transaction_time')
            transaction.payment_time = safe_parse_midtrans_datetime(payment_timestamp_str) or datetime.now(dt_timezone.utc)

            # Update detail pembayaran jika ada
            if not transaction.va_number: transaction.va_number = extract_va_number(notification_payload)
            if not transaction.payment_code: transaction.payment_code = notification_payload.get('payment_code') or notification_payload.get('bill_key')
            if hasattr(transaction, 'biller_code') and not transaction.biller_code: transaction.biller_code = notification_payload.get('biller_code')
            if not transaction.qr_code_url: transaction.qr_code_url = extract_qr_code_url(notification_payload)

            # Essential checks for user and package before updating quota/Mikrotik
            if not transaction.user or not transaction.package:
                current_app.logger.error(f"WEBHOOK: Missing User or Package data for TX {order_id}. Cannot update quota/Mikrotik.")
                session.commit()
                return jsonify({"status":"ok","message":"Success, but missing user/package data."}), HTTPStatus.OK

            user = transaction.user
            package = transaction.package
            
            # Pastikan package memiliki profile yang valid
            if not package.profile:
                current_app.logger.error(f"WEBHOOK: Package {package.id} ('{package.name}') has no associated profile for TX {order_id}. Cannot update Mikrotik.")
                session.commit()
                return jsonify({"status":"ok","message":"Success, but package profile missing."}), HTTPStatus.OK
            
            package_profile = package.profile # Ambil profile dari package untuk digunakan di Mikrotik

            old_total_quota_purchased_mb = user.total_quota_purchased_mb or 0
            
            # --- LOGIKA UTAMA MODEL A: Kuota dan durasi diambil langsung dari `package` ---
            if package.data_quota_gb is not None and package.data_quota_gb > 0:
                added_quota_mb = int(float(package.data_quota_gb) * 1024)
                user.total_quota_purchased_mb = old_total_quota_purchased_mb + added_quota_mb
            else:
                added_quota_mb = 0 # Jika kuota 0 atau None, tidak ada penambahan

            if package.duration_days is not None and package.duration_days > 0:
                new_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=package.duration_days)
                # Jika ada masa berlaku sebelumnya yang masih aktif, tambahkan ke masa berlaku tersebut
                if user.quota_expiry_date and user.quota_expiry_date > datetime.now(dt_timezone.utc):
                    user.quota_expiry_date += timedelta(days=package.duration_days)
                else:
                    user.quota_expiry_date = new_expiry_date
            else:
                user.quota_expiry_date = None # Jika durasi 0 atau None, tidak ada masa berlaku
            
            user.is_unlimited_user = (package.data_quota_gb == 0)
            # --- AKHIR LOGIKA MODEL A ---

            total_kuota_sebelumnya_display = format_quota_display(old_total_quota_purchased_mb)
            total_kuota_saat_ini_display = format_quota_display(user.total_quota_purchased_mb)
            current_app.logger.info(
                f"WEBHOOK: User quota updated for user ID: {user.id}. "
                f"Old total_quota_purchased_mb: {total_kuota_sebelumnya_display}, "
                f"Added: {format_quota_display(added_quota_mb)}, "
                f"New total_quota_purchased_mb: {total_kuota_saat_ini_display}."
            )

            # Mikrotik & WhatsApp hanya diproses jika user sudah aktif dan disetujui
            if user.is_active and user.approval_status == ApprovalStatus.APPROVED:
                current_app.logger.info(f"WEBHOOK: User {user.id} is APPROVED and ACTIVE. Proceeding with Mikrotik password check & activation for TX {order_id}.")
                
                hotspot_username_for_mt = format_to_local_phone(user.phone_number)
                if not hotspot_username_for_mt:
                     current_app.logger.error(f"WEBHOOK: Failed to format phone {user.phone_number} for user {user.id} on TX {order_id}. Mikrotik activation skipped.")
                else:
                    # Generate atau gunakan kembali password Mikrotik
                    password_untuk_mikrotik_dan_wa = user.mikrotik_password
                    pesan_wa_sertakan_password_baru = False
                    # Hasilkan password baru jika belum ada atau tidak valid (misal: bukan 6 digit angka)
                    # PERBAIKAN: Gunakan generate_random_password yang menghasilkan 6 digit angka
                    if not password_untuk_mikrotik_dan_wa or not (len(password_untuk_mikrotik_dan_wa) == 6 and password_untuk_mikrotik_dan_wa.isdigit()):
                        password_untuk_mikrotik_dan_wa = generate_random_password(length=6) # Panggil helper lokal
                        user.mikrotik_password = password_untuk_mikrotik_dan_wa
                        pesan_wa_sertakan_password_baru = True
                        current_app.logger.info(f"WEBHOOK: Generated new 6-digit numeric Mikrotik password for user {user.id} ({hotspot_username_for_mt}).")
                    
                    transaction.hotspot_password = password_untuk_mikrotik_dan_wa # Simpan password ke transaksi juga

                    # Logika sinkronisasi Mikrotik
                    success_mt = False # Initialize success_mt for Mikrotik operation
                    if MIKROTIK_CLIENT_AVAILABLE:
                        try:
                            with get_mikrotik_connection() as api_conn: 
                                if api_conn:
                                    limit_bytes_total = int(max(0, (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)) * 1024 * 1024) # Konversi MB ke bytes
                                    
                                    session_timeout_seconds = 0
                                    if user.quota_expiry_date:
                                        time_remaining = (user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()
                                        session_timeout_seconds = max(0, int(time_remaining)) # Pastikan tidak negatif

                                    success_mt, message_mt = activate_or_update_hotspot_user(
                                        api_connection=api_conn,
                                        user_mikrotik_username=hotspot_username_for_mt,
                                        mikrotik_profile_name=package_profile.profile_name, # Menggunakan nama profil dari paket
                                        hotspot_password=password_untuk_mikrotik_dan_wa,
                                        comment=f"Order:{order_id};Pkg:{package.name[:10]}",
                                        limit_bytes_total=limit_bytes_total,
                                        session_timeout_seconds=session_timeout_seconds,
                                        force_update_profile=True # Tambahkan ini agar profile di Mikrotik terupdate juga
                                    )

                                    if success_mt:
                                        current_app.logger.info(f"WEBHOOK: Mikrotik user {hotspot_username_for_mt} activated/updated successfully for {order_id}. Message: {message_mt}")
                                    else:
                                        current_app.logger.error(f"WEBHOOK: Failed to activate/update Mikrotik user {hotspot_username_for_mt} for {order_id}. Message: {message_mt}")
                                    
                                else:
                                    current_app.logger.error(f"WEBHOOK: Failed to get Mikrotik connection pool for TX {order_id}.")
                                    success_mt = False # Set flag ke False jika koneksi gagal

                        except Exception as activation_err:
                            current_app.logger.error(f"WEBHOOK: Exception during Mikrotik update for user {hotspot_username_for_mt} on {order_id}: {activation_err}", exc_info=True)
                            success_mt = False
                    else:
                        current_app.logger.warning(f"WEBHOOK: Mikrotik client not available. Mikrotik update skipped for {order_id}.")

                # Logika Notifikasi WhatsApp
                enable_whatsapp = current_app.config.get('ENABLE_WHATSAPP_NOTIFICATIONS', False) # Default to False if not set

                current_app.logger.info(f"WEBHOOK: Checking conditions for WhatsApp. ENABLE_WHATSAPP_NOTIFICATIONS: {enable_whatsapp}, User Phone: {user.phone_number is not None}, Mikrotik Success: {success_mt}")
                if success_mt and enable_whatsapp and user.phone_number: # Kirim WA hanya jika Mikrotik berhasil dan WA diaktifkan
                    local_phone_wa = format_to_local_phone(user.phone_number)
                    if local_phone_wa:
                        message_wa_parts = [
                            f"Terima Kasih, {user.full_name or 'Pelanggan'},",
                            f"Pembelian {package.name} telah BERHASIL.",
                            f"Invoice: {order_id}",
                            f"Kuota sebelumnya adalah {total_kuota_sebelumnya_display}.",
                            f"Total kuota anda saat ini adalah {total_kuota_saat_ini_display}."
                        ]
                        if pesan_wa_sertakan_password_baru:
                            message_wa_parts.extend([
                                "\nAkun Hotspot Anda:",
                                f"Username: {hotspot_username_for_mt}",
                                f"Password: {password_untuk_mikrotik_dan_wa}"
                            ])
                        message_wa_parts.append("\nTerima kasih telah menggunakan layanan kami.")
                        message_wa = "\n".join(message_wa_parts)
                        current_app.logger.info(f"WEBHOOK: Attempting to send WhatsApp to {user.phone_number} for {order_id}.")
                        try:
                            wa_sent = send_whatsapp_message(user.phone_number, message_wa)
                            if wa_sent:
                                current_app.logger.info(f"WEBHOOK: WhatsApp notification sent successfully to {user.phone_number} for {order_id}.")
                            else:
                                current_app.logger.error(f"WEBHOOK: send_whatsapp_message returned False for {user.phone_number}, order {order_id}.")
                        except Exception as wa_err:
                            current_app.logger.error(f"WEBHOOK: Failed to send WhatsApp to {user.phone_number} for {order_id}: {wa_err}", exc_info=True)
                    else:
                        current_app.logger.warning(f"WEBHOOK: Cannot send WhatsApp for {order_id}, invalid local phone format for WA: {user.phone_number}")
                elif not success_mt:
                    current_app.logger.warning(f"WEBHOOK: WhatsApp not sent for {order_id} because Mikrotik update was not successful.")
                elif not enable_whatsapp:
                    current_app.logger.warning(f"WEBHOOK: WhatsApp not sent for {order_id} because ENABLE_WHATSAPP_NOTIFICATIONS is False.")
                elif not user.phone_number:
                    current_app.logger.warning(f"WEBHOOK: WhatsApp not sent for {order_id} because user phone number is missing.")
            else:
                current_app.logger.info(f"WEBHOOK: Payment success for {order_id}, but user {user.id} is NOT YET APPROVED/ACTIVE (Status: {user.approval_status.value if user.approval_status else 'N/A'}, Active: {user.is_active}). Mikrotik activation and WhatsApp SKIPPED. Quota update still applied if package has quota.")
        elif status_changed or (new_status_enum == TransactionStatus.PENDING and midtrans_trx_id): # This block handles status changes that are not SUCCESS or pending updates
            current_app.logger.info(f"WEBHOOK: Updating DB status for {order_id} (ID: {transaction.id}) from {transaction.status.value} to {new_status_enum.value}")
            transaction.status = new_status_enum
            if payment_type_notif: transaction.payment_method = payment_type_notif
            if midtrans_trx_id: transaction.midtrans_transaction_id = midtrans_trx_id
            
            if new_status_enum == TransactionStatus.SUCCESS and not transaction.payment_time: # For settlement notifications that update status to SUCCESS
                payment_timestamp_str = notification_payload.get('settlement_time') or notification_payload.get('transaction_time')
                transaction.payment_time = safe_parse_midtrans_datetime(payment_timestamp_str) or datetime.now(dt_timezone.utc)

            # Update detail pembayaran jika ada
            if not transaction.va_number: transaction.va_number = extract_va_number(notification_payload)
            if not transaction.payment_code: transaction.payment_code = notification_payload.get('payment_code') or notification_payload.get('bill_key')
            if hasattr(transaction, 'biller_code') and not transaction.biller_code: transaction.biller_code = notification_payload.get('biller_code')
            if not transaction.qr_code_url: transaction.qr_code_url = extract_qr_code_url(notification_payload)
        else: # No relevant status change or payment success
            current_app.logger.info(f"WEBHOOK: No status change or relevant update needed for {order_id} (ID: {transaction.id}) (DB: {transaction.status.value if transaction.status else 'N/A'}, Midtrans: {midtrans_transaction_status}). Ignoring update, releasing lock.")

        try:
            session.commit()
            current_app.logger.info(f"WEBHOOK: DB commit success for {order_id} (ID: {transaction.id}) with final status {transaction.status.value}. User data (quota, mikrotik_password) and transaction data (hotspot_password) might have been updated.")
        except SQLAlchemyError as db_err:
            session.rollback()
            current_app.logger.error(f"WEBHOOK: DB error committing final state for {order_id} (ID: {transaction.id}): {db_err}", exc_info=True)
            return jsonify({"status":"error","message":"DB commit error"}), HTTPStatus.INTERNAL_SERVER_ERROR

        return jsonify({"status": "ok", "message": "Notification processed successfully."}), HTTPStatus.OK

    except Exception as e:
        if session and session.is_active : session.rollback()
        error_msg = f"WEBHOOK: Unexpected top-level error processing notification"
        if order_id: error_msg += f" for {order_id}"
        current_app.logger.error(error_msg + f". Error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error processing notification."}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        if session:
             session.remove()

@transactions_bp.route('/by-order-id/<string:order_id>', methods=['GET'])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    """Mengambil detail transaksi berdasarkan Order ID."""
    if not current_user_id: abort(HTTPStatus.UNAUTHORIZED, description="ID User tidak valid.")
    current_app.logger.info(f"GET /api/transactions/by-order-id/{order_id} requested by user ID: {current_user_id}.")
    if not order_id: abort(HTTPStatus.BAD_REQUEST, description="Order ID diperlukan.")

    # Cek ketersediaan model dan database session
    if not (db and hasattr(db, 'session') and User and Transaction and Package and PackageProfile):
        current_app.logger.error("CRITICAL: Database models or session not available for transaction details.")
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Kesalahan konfigurasi server (model/database).")

    session = db.session
    try:
        requesting_user = session.get(User, current_user_id)
        if not requesting_user: abort(HTTPStatus.UNAUTHORIZED, description="Pengguna peminta tidak ditemukan.")

        # Memuat transaction dengan user dan package, serta profile dari package
        transaction = session.query(Transaction)\
                          .filter(Transaction.midtrans_order_id == order_id)\
                          .options(
                                selectinload(Transaction.user),
                                selectinload(Transaction.package).selectinload(Package.profile)
                          )\
                          .first()

        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        is_owner = transaction.user_id == current_user_id
        is_admin_role = requesting_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

        if not is_owner and not is_admin_role:
             current_app.logger.warning(f"Unauthorized attempt to access transaction {order_id} by user {current_user_id} (Role: {requesting_user.role.value if requesting_user.role else 'N/A'}).")
             abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan melihat detail transaksi ini.")

        # Jika transaksi masih PENDING, cek status terbaru ke Midtrans
        if transaction.status == TransactionStatus.PENDING:
            current_app.logger.info(f"GET Detail: Transaction {order_id} is PENDING in DB, checking status with Midtrans...")
            try:
                core_api = get_midtrans_core_api_client()
                midtrans_status_response: Dict[str, Any] = core_api.status(order_id)
                current_app.logger.debug(f"GET Detail: Midtrans GET Status response for {order_id}: {midtrans_status_response}")

                midtrans_transaction_status_resp = midtrans_status_response.get('transaction_status')
                midtrans_fraud_status = midtrans_status_response.get('fraud_status')
                payment_type_from_status = midtrans_status_response.get('payment_type')
                midtrans_trx_id_resp = midtrans_status_response.get('transaction_id')

                current_db_status = transaction.status
                new_status_enum_get = current_db_status
                payment_success_get = False

                if midtrans_transaction_status_resp == 'capture':
                    if midtrans_fraud_status == 'accept': new_status_enum_get, payment_success_get = TransactionStatus.SUCCESS, True
                    elif midtrans_fraud_status == 'challenge': new_status_enum_get = TransactionStatus.PENDING
                    elif midtrans_fraud_status == 'deny': new_status_enum_get = TransactionStatus.FAILED
                elif midtrans_transaction_status_resp == 'settlement': new_status_enum_get, payment_success_get = TransactionStatus.SUCCESS, True
                elif midtrans_transaction_status_resp == 'pending': new_status_enum_get = TransactionStatus.PENDING
                elif midtrans_transaction_status_resp == 'deny': new_status_enum_get = TransactionStatus.FAILED
                elif midtrans_transaction_status_resp == 'expire': new_status_enum_get = TransactionStatus.EXPIRED
                elif midtrans_transaction_status_resp == 'cancel': new_status_enum_get = TransactionStatus.CANCELLED

                update_db_needed = False
                if new_status_enum_get != current_db_status:
                    current_app.logger.info(f"GET Detail: Status for {order_id} updated via Midtrans check: {current_db_status.value} -> {new_status_enum_get.value}")
                    transaction.status = new_status_enum_get
                    update_db_needed = True

                    if payment_type_from_status: transaction.payment_method = payment_type_from_status
                    if midtrans_trx_id_resp: transaction.midtrans_transaction_id = midtrans_trx_id_resp

                    if payment_success_get and not transaction.payment_time:
                        payment_timestamp_str_get = midtrans_status_response.get('settlement_time') or midtrans_status_response.get('transaction_time')
                        transaction.payment_time = safe_parse_midtrans_datetime(payment_timestamp_str_get) or datetime.now(dt_timezone.utc)

                    if not transaction.va_number: transaction.va_number = extract_va_number(midtrans_status_response)
                    if not transaction.payment_code: transaction.payment_code = midtrans_status_response.get('payment_code') or midtrans_status_response.get('bill_key')
                    if hasattr(transaction, 'biller_code') and not transaction.biller_code: transaction.biller_code = midtrans_status_response.get('biller_code')
                    if not transaction.qr_code_url: transaction.qr_code_url = extract_qr_code_url(midtrans_status_response)

                elif new_status_enum_get == TransactionStatus.PENDING:
                    current_app.logger.debug(f"GET Detail: Still PENDING for {order_id}. Checking for updated payment details from Midtrans API.")
                    details_to_check_and_update = {
                        'expiry_time': safe_parse_midtrans_datetime(midtrans_status_response.get('expiry_time')),
                        'va_number': extract_va_number(midtrans_status_response),
                        'payment_code': midtrans_status_response.get('payment_code') or midtrans_status_response.get('bill_key'),
                        'biller_code': midtrans_status_response.get('biller_code'),
                        'qr_code_url': extract_qr_code_url(midtrans_status_response)
                    }
                    for attr, new_value_from_api in details_to_check_and_update.items():
                        if hasattr(transaction, attr):
                            current_db_value = getattr(transaction, attr)
                            if (new_value_from_api is not None and new_value_from_api != "" and new_value_from_api != current_db_value) or \
                               (current_db_value is None and new_value_from_api is not None and new_value_from_api != ""):
                                setattr(transaction, attr, new_value_from_api)
                                update_db_needed = True
                                current_app.logger.info(f"GET Detail: Updated '{attr}' for PENDING transaction {order_id} from Midtrans API. Old: '{current_db_value}', New: '{new_value_from_api}'")

                if update_db_needed:
                    try:
                        session.commit()
                        current_app.logger.info(f"GET Detail: Transaction {order_id} status/details updated in DB from GET Status API.")
                    except SQLAlchemyError as db_err_commit:
                        session.rollback()
                        current_app.logger.error(f"GET Detail: DB error committing status/details update for {order_id}: {db_err_commit}", exc_info=True)
            
            except midtransclient.error_midtrans.MidtransAPIError as midtrans_err:
                 if midtrans_err.http_status_code == HTTPStatus.NOT_FOUND:
                      current_app.logger.warning(f"GET Detail: Midtrans GET Status API returned 404 for PENDING {order_id}. Transaction might be too old or invalid. Keeping status PENDING.", exc_info=False)
                 else:
                      current_app.logger.error(f"GET Detail: Error checking Midtrans status for PENDING {order_id}: {midtrans_err.message}", exc_info=True)
            except Exception as e_check_status:
                 current_app.logger.error(f"GET Detail: Unexpected error checking Midtrans status for PENDING {order_id}: {e_check_status}", exc_info=True)

        response_data = {
            "orderId": transaction.midtrans_order_id,
            "transactionId": str(transaction.id),
            "status": transaction.status.value if transaction.status else TransactionStatus.UNKNOWN.value,
            "amount": float(transaction.amount) if transaction.amount is not None else 0.0,
            "paymentMethod": transaction.payment_method,
            "transactionTime": transaction.created_at.isoformat() if transaction.created_at else None,
            "paymentTime": transaction.payment_time.isoformat() if transaction.payment_time else None,
            "expiryTime": transaction.expiry_time.isoformat() if transaction.expiry_time else None,
            "midtransTransactionId": transaction.midtrans_transaction_id,
            "snapToken": transaction.snap_token,
            "snapRedirectUrl": transaction.snap_redirect_url,
            "package": {
                "id": str(p.id), 
                "name": p.name, 
                "description": p.description,
                "price": float(p.price) if p.price is not None else 0.0,
                # Mengambil data kuota dan durasi langsung dari `p` (paket)
                "data_quota_gb": float(p.data_quota_gb) if p.data_quota_gb is not None else 0.0,
                "duration_days": p.duration_days if p.duration_days is not None else 0,
                "mikrotik_profile_name": p.profile.profile_name if p.profile else None, # Nama profil Mikrotik masih dari profile
            } if (p := transaction.package) else None,
            "user": {
                "id": str(u.id), 
                "phone_number": u.phone_number,
                "name": u.full_name,
                # PERBAIKAN: Ambil langsung string dari properti model, lalu normalisasi
                "blok": u.blok if u.blok else None,
                "kamar": u.kamar if u.kamar else None,
                "is_unlimited_user": u.is_unlimited_user,
                "quota_expiry_date": u.quota_expiry_date.isoformat() if u.quota_expiry_date else None
            } if (u := transaction.user) else None,
            "vaNumber": transaction.va_number,
            "paymentCode": transaction.payment_code,
            "billerCode": getattr(transaction, 'biller_code', None),
            "qrCodeUrl": transaction.qr_code_url,
            "hotspotUsername": format_to_local_phone(transaction.user.phone_number) if transaction.user and transaction.status == TransactionStatus.SUCCESS else None,
            "hotspotPassword": transaction.hotspot_password if transaction.user and transaction.status == TransactionStatus.SUCCESS else None,
        }
        # PERBAIKAN: Lakukan normalisasi Kamar_X ke X untuk output API
        if response_data['user'] and response_data['user']['kamar'] and isinstance(response_data['user']['kamar'], str) and response_data['user']['kamar'].startswith("Kamar_") and response_data['user']['kamar'][6:].isdigit():
            response_data['user']['kamar'] = response_data['user']['kamar'][6:]

        current_app.logger.info(f"GET Detail: Returning details for {order_id}, final status from DB: {transaction.status.value if transaction.status else 'N/A'}.")
        return jsonify(response_data), HTTPStatus.OK

    except SQLAlchemyError as e_main_sql:
        current_app.logger.error(f"GET Detail: DB error getting transaction {order_id}: {e_main_sql}", exc_info=True)
        if session and session.is_active: session.rollback()
        return jsonify({"success": False, "message": "Kesalahan database saat mengambil transaksi."}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e_main_exc:
        status_code_resp = getattr(e_main_exc, 'code', HTTPStatus.INTERNAL_SERVER_ERROR)
        description_resp = getattr(e_main_exc, 'description', "Kesalahan internal server.")
        
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

@transactions_bp.route('/<string:midtrans_order_id>/invoice', methods=['GET'])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    """Mengambil invoice transaksi dalam format PDF."""
    current_app.logger.info(f"GET /api/transactions/{midtrans_order_id}/invoice requested by user ID: {current_user_id}")
    session = db.session

    if not WEASYPRINT_AVAILABLE or not HTML_MODULE: # Menggunakan variabel global yang sudah diatur
        current_app.logger.error("WEASYPRINT IMPORT ERROR: WeasyPrint tidak terinstal atau tidak dapat diimpor. Pembuatan PDF invoice tidak akan berfungsi.")
        return jsonify({"success": False, "message": "Gagal membuat PDF invoice (komponen server tidak tersedia)."}), HTTPStatus.NOT_IMPLEMENTED


    # Cek ketersediaan model dan database session
    if not (db and hasattr(db, 'session') and User and Transaction and Package and PackageProfile):
        current_app.logger.error("CRITICAL: Database models or session not available for invoice generation.")
        abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Kesalahan konfigurasi server (model/database).")

    try:
        requesting_user = session.get(User, current_user_id)
        if not requesting_user:
            return jsonify({"success": False, "message": "Pengguna dari token tidak valid."}), HTTPStatus.UNAUTHORIZED

        # Memuat transaction dengan user dan package, serta profile dari package
        transaction = session.query(Transaction)\
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.package).selectinload(Package.profile) # Muat juga package.profile
            )\
            .filter(Transaction.midtrans_order_id == midtrans_order_id)\
            .first()

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

        # Ambil offset zona waktu aplikasi dari konfigurasi
        app_tz_offset = int(current_app.config.get('APP_TIMEZONE_OFFSET', 7))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))

        user_data = transaction.user
        package_data = transaction.package
        package_profile_data = package_data.profile # Ambil profile dari package

        # Cek data esensial untuk invoice
        if not user_data or not package_data or not package_profile_data:
            current_app.logger.error(f"Invoice generation failed for {midtrans_order_id}: User, Package, or Package Profile data is missing from transaction object.")
            return jsonify({"success": False, "message": "Data pengguna, paket, atau profil paket tidak lengkap untuk generate invoice."}), HTTPStatus.INTERNAL_SERVER_ERROR

        # PERBAIKAN: Ambil langsung string dari atribut model, lalu normalisasi untuk display
        user_blok_display = user_data.blok if user_data.blok else '-'
        user_kamar_display = user_data.kamar if user_data.kamar else '-'
        # Normalisasi Kamar_X ke X untuk tampilan
        if user_kamar_display.startswith("Kamar_") and user_kamar_display[6:].isdigit():
            user_kamar_display = user_kamar_display[6:]

        context = {
            'transaction': transaction,
            'user': user_data,
            'package': package_data,
            'package_profile': package_profile_data, # Teruskan package_profile ke konteks template
            'user_blok_value': user_blok_display,
            'user_kamar_value': user_kamar_display,
            # Data bisnis dari konfigurasi aplikasi
            'business_name': current_app.config.get('BUSINESS_NAME', 'Portal Hotspot XYZ'),
            'business_address': current_app.config.get('BUSINESS_ADDRESS', 'Jl. Internet Cepat No. 1, Kota Digital'),
            'business_phone': current_app.config.get('BUSINESS_PHONE', '0812-3456-7890'),
            'business_email': current_app.config.get('BUSINESS_EMAIL', 'admin@portalhotspot.xyz'),
            'invoice_date_local': datetime.now(app_tz),
            'transaction_time_local': transaction.created_at.astimezone(app_tz) if transaction.created_at else None,
            'payment_time_local': transaction.payment_time.astimezone(app_tz) if transaction.payment_time else None,
        }
        
        template_path = 'invoice_template.html'
        
        # Menggunakan HTML_MODULE yang sudah diimpor dan diperiksa
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