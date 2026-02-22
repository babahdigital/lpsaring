# backend/app/infrastructure/http/transactions_routes.py
# VERSI PERBAIKAN FINAL: Menggunakan base URL publik dari konfigurasi dan Celery.

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Dict, Optional

import midtransclient
from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request
import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import selectinload

from app.extensions import db, limiter
from app.infrastructure.db.models import (
    ApprovalStatus,
    Package,
    Transaction,
    TransactionEvent,
    TransactionEventSource,
    TransactionStatus,
    User,
)
from app.services.transaction_service import apply_package_and_sync_to_mikrotik
from app.services.notification_service import (
    generate_temp_invoice_token,
    get_notification_message,
    verify_temp_invoice_token,
)
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection

# from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf # Tidak lagi dipanggil langsung
from app.utils.formatters import format_to_local_phone
from .decorators import token_required
from app.utils.circuit_breaker import record_failure, record_success, should_allow_call
from app.utils.metrics_utils import increment_metric

# Import Celery task
from app.tasks import send_whatsapp_invoice_task  # Import task Celery Anda

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    WEASYPRINT_AVAILABLE = False

transactions_bp = Blueprint(
    "transactions_api",
    __name__,
    url_prefix="/api/transactions",
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../templates"),
)


def _safe_json_dumps(value: object) -> str | None:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def _log_transaction_event(
    *,
    session,
    transaction: Transaction,
    source: TransactionEventSource,
    event_type: str,
    status: TransactionStatus | None = None,
    payload: object | None = None,
) -> None:
    ev = TransactionEvent()
    ev.id = uuid.uuid4()
    ev.transaction_id = transaction.id
    ev.source = source
    ev.event_type = event_type
    ev.status = status
    ev.payload = _safe_json_dumps(payload) if payload is not None else None
    session.add(ev)


# --- FUNGSI HELPER (Tidak ada perubahan) ---
def get_midtrans_core_api_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    client = midtransclient.CoreApi(is_production=is_production, server_key=server_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def get_midtrans_snap_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    client_key = current_app.config.get("MIDTRANS_CLIENT_KEY")
    if not server_key or not client_key:
        raise ValueError("MIDTRANS_SERVER_KEY atau MIDTRANS_CLIENT_KEY configuration is missing.")
    client = midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string:
        return None
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
    specific_fields = [
        "permata_va_number",
        "bca_va_number",
        "bni_va_number",
        "bri_va_number",
        "cimb_va_number",
        "mandiri_bill_key",
        "bill_key",
        "payment_code",
        "va_number",
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


def _build_webhook_idempotency_key(payload: Dict[str, Any]) -> Optional[str]:
    order_id = payload.get("order_id")
    status_code = payload.get("status_code")
    transaction_status = payload.get("transaction_status")
    transaction_id = payload.get("transaction_id")
    if not order_id or not status_code or not transaction_status:
        return None
    token = transaction_id or "no_trx_id"
    return f"midtrans:webhook:{order_id}:{transaction_status}:{status_code}:{token}"


def _is_duplicate_webhook(payload: Dict[str, Any]) -> bool:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return False
    key = _build_webhook_idempotency_key(payload)
    if not key:
        return False
    try:
        ttl_seconds = int(current_app.config.get("MIDTRANS_WEBHOOK_IDEMPOTENCY_TTL_SECONDS", 86400))
    except Exception:
        ttl_seconds = 86400
    try:
        inserted = redis_client.set(key, "1", ex=ttl_seconds, nx=True)
        return inserted is None
    except Exception:
        return False


# --- JINJA FILTERS (Tidak ada perubahan) ---
def format_datetime_short(value: datetime) -> str:
    if not isinstance(value, datetime):
        return ""
    try:
        app_tz_offset = int(current_app.config.get("APP_TIMEZONE_OFFSET", 8))
        app_tz = dt_timezone(timedelta(hours=app_tz_offset))
        local_dt = value.astimezone(app_tz)
        return local_dt.strftime("%d %b %Y, %H:%M WITA")
    except Exception:
        return "Invalid Date"


def format_currency(value: Any) -> str:
    if value is None:
        return "Rp 0"
    try:
        decimal_value = Decimal(value)
        return f"Rp {decimal_value:,.0f}".replace(",", ".")
    except Exception:
        return "Rp Error"


def format_number(value: Any) -> str:
    if value is None:
        return "0"
    try:
        decimal_value = Decimal(value)
        return f"{decimal_value:,.0f}".replace(",", ".")
    except Exception:
        try:
            return str(value)
        except Exception:
            return "0"


def format_status(value: str) -> str:
    if not isinstance(value, str):
        return value
    return value.replace("_", " ").title()


@transactions_bp.app_template_filter("format_datetime_short")
def _format_datetime_short_filter(value):
    return format_datetime_short(value)


@transactions_bp.app_template_filter("format_currency")
def _format_currency_filter(value):
    return format_currency(value)


@transactions_bp.app_template_filter("format_number")
def _format_number_filter(value):
    return format_number(value)


@transactions_bp.app_template_filter("format_status")
def _format_status_filter(value):
    return format_status(value)


# --- Skema Pydantic ---
class _InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID


class _InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = Field(None, alias="snap_token")
    transaction_id: uuid.UUID = Field(..., alias="id")
    order_id: str = Field(..., alias="midtrans_order_id")
    redirect_url: Optional[str] = Field(None, alias="snap_redirect_url")

    model_config = ConfigDict(from_attributes=True)


# --- ENDPOINTS ---
@transactions_bp.route("/initiate", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("INITIATE_TRANSACTION_RATE_LIMIT", "10 per minute"))
@token_required
def initiate_transaction(current_user_id: uuid.UUID):
    req_data_dict = request.get_json(silent=True) or {}
    try:
        req_data = _InitiateTransactionRequestSchema.model_validate(req_data_dict)
    except ValidationError as e:
        return jsonify(
            {"success": False, "message": "Input tidak valid.", "details": e.errors()}
        ), HTTPStatus.UNPROCESSABLE_ENTITY

    session = db.session
    try:
        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        package = session.query(Package).get(req_data.package_id)
        if not package or not package.is_active:
            abort(HTTPStatus.BAD_REQUEST, description="Paket tidak valid atau tidak aktif.")

        gross_amount = int(package.price or 0)

        now_utc = datetime.now(dt_timezone.utc)

        # Reuse existing active transaction to avoid creating many expired rows
        # due to repeated clicks/refreshes.
        existing_tx = (
            session.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .filter(Transaction.package_id == package.id)
            .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
            .filter(
                sa.or_(
                    Transaction.expiry_time.is_(None),
                    Transaction.expiry_time > now_utc,
                )
            )
            .order_by(Transaction.created_at.desc())
            .first()
        )
        if existing_tx and (existing_tx.snap_token or existing_tx.snap_redirect_url):
            _log_transaction_event(
                session=session,
                transaction=existing_tx,
                source=TransactionEventSource.APP,
                event_type="INITIATE_REUSED_EXISTING",
                status=existing_tx.status,
                payload={
                    "order_id": existing_tx.midtrans_order_id,
                    "package_id": str(existing_tx.package_id),
                    "amount": int(existing_tx.amount or 0),
                    "expiry_time": existing_tx.expiry_time.isoformat() if existing_tx.expiry_time else None,
                    "snap_token_present": bool(existing_tx.snap_token),
                    "redirect_url": existing_tx.snap_redirect_url,
                    "reason": "existing_active_transaction",
                },
            )
            session.commit()
            response_data = _InitiateTransactionResponseSchema.model_validate(existing_tx, from_attributes=True)
            return jsonify(response_data.model_dump(by_alias=False, exclude_none=True)), HTTPStatus.OK

        order_id = f"HS-{uuid.uuid4().hex[:12].upper()}"

        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        local_expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        # SQLAlchemy model init menerima keyword args, tetapi type-checker (Pylance)
        # tidak mengenali signature dinamis tersebut. Gunakan assignment eksplisit.
        new_transaction = Transaction()
        new_transaction.id = uuid.uuid4()
        new_transaction.user_id = user.id
        new_transaction.package_id = package.id
        new_transaction.midtrans_order_id = order_id
        new_transaction.amount = gross_amount
        new_transaction.status = TransactionStatus.UNKNOWN
        new_transaction.expiry_time = local_expiry_time

        # PERBAIKAN: Gunakan base URL publik jika tersedia, jika tidak fallback ke frontend URL
        # Ini untuk callback finish yang dilihat oleh browser pengguna.
        base_callback_url = (
            current_app.config.get("APP_PUBLIC_BASE_URL")
            or current_app.config.get("FRONTEND_URL")
            or current_app.config.get("APP_LINK_USER")
        )
        if not base_callback_url:
            current_app.logger.error("APP_PUBLIC_BASE_URL/FRONTEND_URL/APP_LINK_USER belum dikonfigurasi.")
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="APP_PUBLIC_BASE_URL belum dikonfigurasi.")
        # Jangan hardcode status=pending: status final harus berdasarkan callback Snap atau webhook.
        finish_url = f"{base_callback_url.rstrip('/')}/payment/finish?order_id={order_id}"

        snap_params = {
            "transaction_details": {"order_id": order_id, "gross_amount": gross_amount},
            "item_details": [{"id": str(package.id), "price": gross_amount, "quantity": 1, "name": package.name[:100]}],
            "customer_details": {
                "first_name": user.full_name or "Pengguna",
                "phone": format_to_local_phone(user.phone_number),
            },
            "callbacks": {"finish": finish_url},
        }

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Midtrans sementara tidak tersedia.")

        snap = get_midtrans_snap_client()
        snap_response = snap.create_transaction(snap_params)
        record_success("midtrans")

        snap_token = snap_response.get("token")
        redirect_url = snap_response.get("redirect_url")
        if not snap_token and not redirect_url:
            raise ValueError("Respons Midtrans tidak valid.")

        new_transaction.snap_token = snap_token
        new_transaction.snap_redirect_url = redirect_url

        _log_transaction_event(
            session=session,
            transaction=new_transaction,
            source=TransactionEventSource.APP,
            event_type="INITIATED",
            status=new_transaction.status,
            payload={
                "order_id": order_id,
                "package_id": str(package.id),
                "amount": gross_amount,
                "expiry_time": new_transaction.expiry_time.isoformat() if new_transaction.expiry_time else None,
                "snap_token_present": bool(snap_token),
                "redirect_url": redirect_url,
                "finish_url": finish_url,
            },
        )

        session.add(new_transaction)
        session.commit()

        response_data = _InitiateTransactionResponseSchema.model_validate(new_transaction, from_attributes=True)
        return jsonify(response_data.model_dump(by_alias=False, exclude_none=True)), HTTPStatus.OK

    except Exception as e:
        record_failure("midtrans")
        db.session.rollback()
        current_app.logger.error(f"Error di initiate_transaction: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
    finally:
        db.session.remove()


@transactions_bp.route("/notification", methods=["POST"])
def handle_notification():
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
    gross_amount_str = notification_payload.get("gross_amount", "0")
    gross_amount_str_for_hash = gross_amount_str if "." in gross_amount_str else gross_amount_str + ".00"
    string_to_hash = f"{order_id}{notification_payload.get('status_code')}{gross_amount_str_for_hash}{server_key}"
    calculated_signature = hashlib.sha512(string_to_hash.encode("utf-8")).hexdigest()
    if calculated_signature != notification_payload.get("signature_key") and current_app.config.get(
        "MIDTRANS_IS_PRODUCTION", False
    ):
        return jsonify({"status": "error", "message": "Signature tidak valid"}), HTTPStatus.FORBIDDEN

    if _is_duplicate_webhook(notification_payload):
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

        # Simpan payload mentah agar admin bisa audit lengkap seperti data contoh.
        try:
            transaction.midtrans_notification_payload = json.dumps(notification_payload, ensure_ascii=False)
        except Exception:
            transaction.midtrans_notification_payload = None

        midtrans_status_raw = notification_payload.get("transaction_status")
        midtrans_status = str(midtrans_status_raw).strip().lower() if isinstance(midtrans_status_raw, str) else ""
        fraud_status_raw = notification_payload.get("fraud_status")
        fraud_status = str(fraud_status_raw).strip().lower() if isinstance(fraud_status_raw, str) else None
        # settlement umumnya final sukses; capture butuh fraud accept (untuk kartu) namun bisa None untuk metode lain.
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

        _log_transaction_event(
            session=session,
            transaction=transaction,
            source=TransactionEventSource.MIDTRANS_WEBHOOK,
            event_type="NOTIFICATION",
            status=transaction.status,
            payload=notification_payload,
        )
        if notification_payload.get("transaction_id"):
            transaction.midtrans_transaction_id = notification_payload.get("transaction_id")

        # Enrich kolom transaksi dari payload (baik pending maupun final) agar tabel admin lengkap.
        if notification_payload.get("payment_type"):
            transaction.payment_method = notification_payload.get("payment_type")

        if parsed_expiry := safe_parse_midtrans_datetime(notification_payload.get("expiry_time")):
            transaction.expiry_time = parsed_expiry

        # Informasi pembayaran yang bisa dipakai di finish page.
        transaction.va_number = extract_va_number(notification_payload) or transaction.va_number
        if notification_payload.get("payment_code"):
            transaction.payment_code = notification_payload.get("payment_code")
        if notification_payload.get("biller_code"):
            transaction.biller_code = notification_payload.get("biller_code")
        transaction.qr_code_url = extract_qr_code_url(notification_payload) or transaction.qr_code_url

        if payment_success:
            # set payment time jika tersedia
            transaction.payment_time = (
                safe_parse_midtrans_datetime(notification_payload.get("settlement_time"))
                or safe_parse_midtrans_datetime(notification_payload.get("transaction_time"))
                or transaction.payment_time
            )

        if payment_success:
            with get_mikrotik_connection() as mikrotik_api:
                is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                if is_success:
                    _log_transaction_event(
                        session=session,
                        transaction=transaction,
                        source=TransactionEventSource.APP,
                        event_type="MIKROTIK_APPLY_SUCCESS",
                        status=transaction.status,
                        payload={"message": message},
                    )
                    session.commit()  # Commit transaksi DULU
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

                        # --- PERUBAHAN KRUSIAL DI SINI: Tambahkan .pdf ke URL ---
                        # Ini akan membuat URL yang berakhir dengan .pdf, membantu Fonnte mengidentifikasi formatnya.
                        temp_invoice_url = f"{base_url.rstrip('/')}/api/transactions/invoice/temp/{temp_token}.pdf"
                        # --- AKHIR PERUBAHAN ---

                        msg_context = {
                            "full_name": user.full_name,
                            "order_id": transaction.midtrans_order_id,
                            "package_name": package.name,
                            "package_price": format_currency(package.price),
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
                        current_app.logger.info(f"Task pengiriman WhatsApp invoice untuk {order_id} dikirim ke Celery.")

                    except Exception as e_notif:
                        current_app.logger.error(
                            f"WEBHOOK: Gagal kirim notif WhatsApp {order_id}: {e_notif}", exc_info=True
                        )
                else:
                    session.rollback()  # Rollback jika Mikrotik gagal
                    try:
                        transaction_after = (
                            session.query(Transaction)
                            .filter(Transaction.midtrans_order_id == order_id)
                            .with_for_update()
                            .first()
                        )
                        if transaction_after is not None:
                            _log_transaction_event(
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
            session.commit()  # Commit status transaksi yang berubah (pending, deny, expire, cancel)
            current_app.logger.info(f"WEBHOOK: Status transaksi {order_id} diupdate ke {transaction.status.value}.")
            if transaction.status in [TransactionStatus.FAILED, TransactionStatus.CANCELLED, TransactionStatus.EXPIRED]:
                increment_metric("payment.failed")

        return jsonify({"status": "ok"}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"WEBHOOK Error {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        db.session.remove()


@transactions_bp.route("/by-order-id/<string:order_id>", methods=["GET"])
@token_required
def get_transaction_by_order_id(current_user_id: uuid.UUID, order_id: str):
    session = db.session
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
                # Throttle Midtrans status checks to avoid spamming Core API during frontend polling.
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
                            # Skip calling Midtrans; return current DB state.
                            raise StopIteration
                    except StopIteration:
                        raise
                    except Exception:
                        # If Redis fails, continue without throttle.
                        pass

                if not should_allow_call("midtrans"):
                    abort(HTTPStatus.SERVICE_UNAVAILABLE, "Midtrans sementara tidak tersedia.")

                core_api = get_midtrans_core_api_client()
                midtrans_status_response = core_api.transactions.status(order_id)
                record_success("midtrans")

                # Log Midtrans status check only when we actually call Core API (throttled above).
                _log_transaction_event(
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

                if midtrans_status_response.get("payment_type"):
                    transaction.payment_method = midtrans_status_response.get("payment_type")
                if parsed_expiry := safe_parse_midtrans_datetime(midtrans_status_response.get("expiry_time")):
                    transaction.expiry_time = parsed_expiry
                transaction.va_number = extract_va_number(midtrans_status_response) or transaction.va_number
                transaction.qr_code_url = extract_qr_code_url(midtrans_status_response) or transaction.qr_code_url

                if payment_success:
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.midtrans_transaction_id = midtrans_status_response.get("transaction_id")
                    transaction.payment_time = safe_parse_midtrans_datetime(
                        midtrans_status_response.get("settlement_time")
                    ) or datetime.now(dt_timezone.utc)
                    transaction.payment_code = midtrans_status_response.get("payment_code") or transaction.payment_code
                    transaction.biller_code = midtrans_status_response.get("biller_code") or transaction.biller_code

                    with get_mikrotik_connection() as mikrotik_api:
                        if not mikrotik_api:
                            abort(HTTPStatus.SERVICE_UNAVAILABLE, "Gagal koneksi ke sistem hotspot untuk sinkronisasi.")
                        is_success, message = apply_package_and_sync_to_mikrotik(transaction, mikrotik_api)
                        if is_success:
                            _log_transaction_event(
                                session=session,
                                transaction=transaction,
                                source=TransactionEventSource.APP,
                                event_type="MIKROTIK_APPLY_SUCCESS",
                                status=transaction.status,
                                payload={"message": message},
                            )
                            session.commit()
                        else:
                            session.rollback()
                            try:
                                transaction_after = (
                                    session.query(Transaction)
                                    .filter(Transaction.midtrans_order_id == order_id)
                                    .with_for_update()
                                    .first()
                                )
                                if transaction_after is not None:
                                    _log_transaction_event(
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
                    _log_transaction_event(
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
        response_data = {
            "id": str(transaction.id),
            "midtrans_order_id": transaction.midtrans_order_id,
            "midtrans_transaction_id": transaction.midtrans_transaction_id,
            "status": transaction.status.value,
            "amount": float(transaction.amount or 0.0),
            "payment_method": transaction.payment_method,
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
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Kesalahan tak terduga saat mengambil detail transaksi: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga: {e}")
    finally:
        if session:
            session.remove()


@transactions_bp.route("/<string:order_id>/cancel", methods=["POST"])
@token_required
def cancel_transaction(current_user_id: uuid.UUID, order_id: str):
    session = db.session
    try:
        transaction = (
            session.query(Transaction).filter(Transaction.midtrans_order_id == order_id).with_for_update().first()
        )
        if not transaction:
            abort(HTTPStatus.NOT_FOUND, description=f"Transaksi dengan Order ID {order_id} tidak ditemukan.")

        requesting_user = session.get(User, current_user_id)
        if not requesting_user or (transaction.user_id != current_user_id and not requesting_user.is_admin_role):
            abort(HTTPStatus.FORBIDDEN, description="Anda tidak diizinkan membatalkan transaksi ini.")

        if transaction.status == TransactionStatus.SUCCESS:
            return jsonify(
                {"success": False, "message": "Transaksi sudah sukses dan tidak bisa dibatalkan."}
            ), HTTPStatus.BAD_REQUEST

        if transaction.status in (TransactionStatus.UNKNOWN, TransactionStatus.PENDING):
            transaction.status = TransactionStatus.CANCELLED
            _log_transaction_event(
                session=session,
                transaction=transaction,
                source=TransactionEventSource.APP,
                event_type="CANCELLED_BY_USER",
                status=transaction.status,
                payload={"order_id": order_id},
            )
            session.commit()
        return jsonify({"success": True, "status": transaction.status.value}), HTTPStatus.OK
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Gagal membatalkan transaksi {order_id}: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal membatalkan transaksi.")
    finally:
        session.remove()


@transactions_bp.route("/<string:midtrans_order_id>/invoice", methods=["GET"])
@token_required
def get_transaction_invoice(current_user_id: uuid.UUID, midtrans_order_id: str):
    if not WEASYPRINT_AVAILABLE:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")
    assert HTML is not None
    session = db.session
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
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()

        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menghasilkan file PDF.")
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{midtrans_order_id}.pdf"'
        return response
    except Exception as e:
        if session.is_active:
            session.rollback()
        current_app.logger.error(f"Error saat membuat invoice PDF untuk {midtrans_order_id}: {e}", exc_info=True)
        if isinstance(e, (HTTPStatus, midtransclient.error_midtrans.MidtransAPIError)):
            raise e
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan tak terduga saat membuat invoice: {e}")
    finally:
        if session:
            session.remove()


@transactions_bp.route("/invoice/temp/<string:token>", methods=["GET"])
# Tambahkan route baru untuk URL yang diakhiri dengan .pdf
@transactions_bp.route("/invoice/temp/<string:token>.pdf", methods=["GET"])
def get_temp_transaction_invoice(token: str):
    if not WEASYPRINT_AVAILABLE or HTML is None:
        abort(HTTPStatus.NOT_IMPLEMENTED, "Komponen PDF server tidak tersedia.")

    transaction_id = verify_temp_invoice_token(token, max_age_seconds=3600)
    if not transaction_id:
        abort(HTTPStatus.FORBIDDEN, description="Akses tidak valid atau link telah kedaluwarsa.")

    session = db.session
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

        # PERBAIKAN: Gunakan base URL publik untuk merender PDF agar path aset (jika ada) benar
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("invoice_template.html", **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="invoice-{transaction.midtrans_order_id}.pdf"'

        return response
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat membuat invoice sementara PDF: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Kesalahan tak terduga saat membuat invoice.")
    finally:
        db.session.remove()
