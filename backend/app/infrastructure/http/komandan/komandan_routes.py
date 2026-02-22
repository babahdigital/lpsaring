# backend/app/infrastructure/http/komandan/komandan_routes.py

import json
import uuid
from datetime import timedelta
from flask import Blueprint, request, jsonify, current_app
from http import HTTPStatus
from pydantic import ValidationError

# --- [PERBAIKAN KUNCI DI SINI] ---
# Memastikan semua fungsi yang dibutuhkan dari SQLAlchemy diimpor.
from sqlalchemy import select, desc, asc
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.infrastructure.db.models import (
    User,
    UserRole,
    QuotaRequest,
    RequestStatus,
    NotificationRecipient,
    NotificationType,
    RequestType,
)
from app.infrastructure.http.decorators import token_required
from .schemas import QuotaRequestCreateSchema, QuotaRequestResponseSchema
from app.services import settings_service
from app.services.notification_service import get_notification_message
from app.utils.formatters import get_app_local_datetime

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message

    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False

komandan_bp = Blueprint("komandan_api", __name__, url_prefix="/api/komandan")


# Fungsi create_quota_request tidak ada perubahan, tetap sama
@komandan_bp.route("/requests", methods=["POST"])
@token_required
def create_quota_request(current_user_id: uuid.UUID):
    current_user = db.session.get(User, current_user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), HTTPStatus.UNAUTHORIZED

    if current_user.role != UserRole.KOMANDAN:
        return jsonify({"message": "Hanya Komandan yang dapat mengakses fitur ini."}), HTTPStatus.FORBIDDEN

    if not request.is_json:
        return jsonify({"message": "Request body harus JSON."}), HTTPStatus.BAD_REQUEST

    try:
        data_input = QuotaRequestCreateSchema.model_validate(request.json)

        existing_pending_request = db.session.scalar(
            select(QuotaRequest).where(
                QuotaRequest.requester_id == current_user.id, QuotaRequest.status == RequestStatus.PENDING
            )
        )
        if existing_pending_request:
            return jsonify(
                {
                    "message": "Anda sudah memiliki permintaan yang sedang diproses. Mohon tunggu hingga permintaan sebelumnya selesai."
                }
            ), HTTPStatus.CONFLICT

        if data_input.request_type == RequestType.UNLIMITED:
            allow_unlimited = settings_service.get_setting("KOMANDAN_ALLOW_UNLIMITED_REQUEST", "True") == "True"
            if not allow_unlimited:
                return jsonify({"message": "Permintaan unlimited tidak diizinkan saat ini."}), HTTPStatus.FORBIDDEN

        now_local = get_app_local_datetime()
        window_hours = settings_service.get_setting_as_int("KOMANDAN_REQUEST_WINDOW_HOURS", 24)
        max_per_window = settings_service.get_setting_as_int("KOMANDAN_REQUEST_MAX_PER_WINDOW", 1)
        cooldown_hours = settings_service.get_setting_as_int("KOMANDAN_REQUEST_COOLDOWN_HOURS", 6)

        if window_hours > 0 and max_per_window > 0:
            window_start = now_local - timedelta(hours=window_hours)
            recent_count = (
                db.session.scalar(
                    select(db.func.count(QuotaRequest.id)).where(
                        QuotaRequest.requester_id == current_user.id, QuotaRequest.created_at >= window_start
                    )
                )
                or 0
            )
            if recent_count >= max_per_window:
                oldest_in_window = db.session.scalar(
                    select(QuotaRequest.created_at)
                    .where(QuotaRequest.requester_id == current_user.id, QuotaRequest.created_at >= window_start)
                    .order_by(QuotaRequest.created_at.asc())
                )
                retry_at = None
                retry_after_seconds = None
                if oldest_in_window:
                    oldest_local = get_app_local_datetime(oldest_in_window)
                    retry_at = oldest_local + timedelta(hours=window_hours)
                    retry_after_seconds = max(0, int((retry_at - now_local).total_seconds()))
                return jsonify(
                    {
                        "message": "Batas permintaan dalam periode saat ini sudah tercapai.",
                        "retry_at": retry_at.isoformat() if retry_at else None,
                        "retry_after_seconds": retry_after_seconds,
                    }
                ), HTTPStatus.TOO_MANY_REQUESTS

        if cooldown_hours > 0:
            last_request = db.session.scalar(
                select(QuotaRequest)
                .where(QuotaRequest.requester_id == current_user.id)
                .order_by(QuotaRequest.created_at.desc())
            )
            if last_request:
                last_request_local = get_app_local_datetime(last_request.created_at)
                next_allowed = last_request_local + timedelta(hours=cooldown_hours)
                if now_local < next_allowed:
                    return jsonify(
                        {
                            "message": "Silakan tunggu sebelum mengajukan permintaan berikutnya.",
                            "retry_at": next_allowed.isoformat(),
                            "retry_after_seconds": max(0, int((next_allowed - now_local).total_seconds())),
                        }
                    ), HTTPStatus.TOO_MANY_REQUESTS

        if data_input.request_type == RequestType.QUOTA:
            max_mb = settings_service.get_setting_as_int("KOMANDAN_MAX_QUOTA_MB", 51200)
            max_days = settings_service.get_setting_as_int("KOMANDAN_MAX_QUOTA_DAYS", 30)
            if data_input.requested_mb and data_input.requested_mb > max_mb:
                return jsonify({"message": "Permintaan kuota melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST
            if data_input.requested_duration_days and data_input.requested_duration_days > max_days:
                return jsonify({"message": "Durasi kuota melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST

        new_request = QuotaRequest()
        new_request.requester_id = current_user.id
        new_request.status = RequestStatus.PENDING
        new_request.request_type = data_input.request_type
        new_request.request_details = (
            json.dumps(
                {"requested_mb": data_input.requested_mb, "requested_duration_days": data_input.requested_duration_days}
            )
            if data_input.request_type == RequestType.QUOTA
            else None
        )

        db.session.add(new_request)
        db.session.commit()
        db.session.refresh(new_request)

        try:
            if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
                recipients_query = (
                    select(User)
                    .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
                    .where(
                        NotificationRecipient.notification_type == NotificationType.NEW_KOMANDAN_REQUEST, User.is_active
                    )
                )
                recipients = db.session.scalars(recipients_query).all()

                if recipients:
                    request_details_text = (
                        f"{data_input.requested_mb} MB / {data_input.requested_duration_days} hari"
                        if new_request.request_type == RequestType.QUOTA
                        else "Akses Unlimited"
                    )
                    admin_context = {
                        "komandan_name": current_user.full_name,
                        "request_type": new_request.request_type.value,
                        "details": request_details_text,
                    }
                    admin_message = get_notification_message("new_komandan_request_to_admin", admin_context)
                    for admin in recipients:
                        send_whatsapp_message(admin.phone_number, admin_message)
        except Exception as e_notify:
            current_app.logger.error(f"Gagal mengirim notifikasi permintaan Komandan: {e_notify}", exc_info=True)

        response = QuotaRequestResponseSchema(
            id=new_request.id,
            status=new_request.status,
            request_type=new_request.request_type,
            message="Permintaan Anda telah berhasil dikirim dan sedang menunggu persetujuan Admin.",
        )

        return jsonify(response.model_dump(mode="json")), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify({"message": "Input tidak valid.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tak terduga saat membuat permintaan kuota: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


# Fungsi get_my_requests_history juga tidak ada perubahan logika, hanya memastikan impor di atas sudah benar
@komandan_bp.route("/requests/history", methods=["GET"])
@token_required
def get_my_requests_history(current_user_id: uuid.UUID):
    """Mengambil riwayat permintaan yang diajukan oleh Komandan yang sedang login."""
    current_user = db.session.get(User, current_user_id)
    if not current_user or current_user.role != UserRole.KOMANDAN:
        return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("itemsPerPage", 10, type=int), 50)

        sort_by = request.args.get("sortBy") or "created_at"
        sort_order = request.args.get("sortOrder", "desc").lower()

        sortable_columns = {
            "created_at": QuotaRequest.created_at,
            "status": QuotaRequest.status,
        }

        order_column = sortable_columns.get(str(sort_by), QuotaRequest.created_at)
        order_expression = desc(order_column) if sort_order == "desc" else asc(order_column)

        query = (
            select(QuotaRequest)
            .options(joinedload(QuotaRequest.processed_by).load_only(User.full_name))
            .where(QuotaRequest.requester_id == current_user_id)
            .order_by(order_expression)
        )

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

        results = []
        for req in pagination.items:
            details = json.loads(req.request_details) if req.request_details else {}
            granted_details = None
            if req.granted_details:
                try:
                    granted_details = json.loads(req.granted_details)
                except json.JSONDecodeError:
                    granted_details = None
            results.append(
                {
                    "id": str(req.id),
                    "created_at": req.created_at.isoformat(),
                    "request_type": req.request_type.value,
                    "status": req.status.value,
                    "requested_mb": details.get("requested_mb"),
                    "requested_duration_days": details.get("requested_duration_days"),
                    "granted_details": granted_details,
                    "processed_at": req.processed_at.isoformat() if req.processed_at else None,
                    "rejection_reason": req.rejection_reason,
                    "processed_by_admin": req.processed_by.full_name if req.processed_by else None,
                }
            )

        return jsonify({"items": results, "totalItems": pagination.total}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(
            f"Error mengambil riwayat permintaan untuk komandan {current_user_id}: {e}", exc_info=True
        )
        return jsonify({"message": "Gagal memuat riwayat permintaan."}), HTTPStatus.INTERNAL_SERVER_ERROR
