# backend/app/infrastructure/http/komandan/komandan_routes.py
# PENYEMPURNAAN: Beralih ke Flask-JWT-Extended untuk autentikasi.
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false

import json
import uuid
from flask import Blueprint, request, jsonify, current_app
from http import HTTPStatus
from pydantic import ValidationError
from sqlalchemy import select, desc, asc
from sqlalchemy.orm import joinedload
from flask_jwt_extended import jwt_required, get_current_user # [PERBAIKAN] Impor baru

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, QuotaRequest, RequestStatus, NotificationRecipient, NotificationType, RequestType
# [DIHAPUS] Impor decorator lama tidak diperlukan lagi.
# from app.infrastructure.http.decorators import token_required
from .schemas import QuotaRequestCreateSchema, QuotaRequestResponseSchema
from app.services import settings_service
from app.services.notification_service import get_notification_message

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False

komandan_bp = Blueprint('komandan_api', __name__)

@komandan_bp.route('/requests', methods=['POST'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def create_quota_request():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()
    
    if current_user.role != UserRole.KOMANDAN:
        return jsonify({"message": "Hanya Komandan yang dapat mengakses fitur ini."}), HTTPStatus.FORBIDDEN

    if not request.is_json:
        return jsonify({"message": "Request body harus JSON."}), HTTPStatus.BAD_REQUEST

    try:
        data_input = QuotaRequestCreateSchema.model_validate(request.json)

        existing_pending_request = db.session.scalar(
            select(QuotaRequest).where(
                QuotaRequest.requester_id == current_user.id,
                QuotaRequest.status == RequestStatus.PENDING
            )
        )
        if existing_pending_request:
            return jsonify({"message": "Anda sudah memiliki permintaan yang sedang diproses. Mohon tunggu hingga permintaan sebelumnya selesai."}), HTTPStatus.CONFLICT

        new_request = QuotaRequest(
            requester_id=current_user.id,
            status=RequestStatus.PENDING,
            request_type=data_input.request_type,
            request_details=json.dumps({
                "requested_mb": data_input.requested_mb,
                "requested_duration_days": data_input.requested_duration_days
            }) if data_input.request_type == RequestType.QUOTA else None
        )

        db.session.add(new_request)
        db.session.commit()
        db.session.refresh(new_request)

        try:
            if WHATSAPP_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
                recipients_query = select(User).join(
                    NotificationRecipient, User.id == NotificationRecipient.admin_user_id
                ).where(
                    NotificationRecipient.notification_type == NotificationType.NEW_KOMANDAN_REQUEST,
                    User.is_active == True
                )
                recipients = db.session.scalars(recipients_query).all()

                if recipients:
                    request_details_text = f"{data_input.requested_mb} MB / {data_input.requested_duration_days} hari" if new_request.request_type == RequestType.QUOTA else "Akses Unlimited"
                    admin_context = {
                        "komandan_name": current_user.full_name,
                        "request_type": new_request.request_type.value,
                        "details": request_details_text
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
            message="Permintaan Anda telah berhasil dikirim dan sedang menunggu persetujuan Admin."
        )
        
        return jsonify(response.model_dump(mode='json')), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify({"message": "Input tidak valid.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tak terduga saat membuat permintaan kuota: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@komandan_bp.route('/requests/history', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_requests_history():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    if current_user.role != UserRole.KOMANDAN:
        return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 50)
        
        sort_by = request.args.get('sortBy')
        sort_order = request.args.get('sortOrder', 'desc').lower()
        
        sortable_columns = {
            'created_at': QuotaRequest.created_at,
            'status': QuotaRequest.status,
        }
        
        order_column = sortable_columns.get(sort_by, QuotaRequest.created_at)
        order_expression = desc(order_column) if sort_order == 'desc' else asc(order_column)

        query = (
            select(QuotaRequest)
            .options(
                joinedload(QuotaRequest.processed_by).load_only(User.full_name)
            )
            .where(QuotaRequest.requester_id == current_user.id)
            .order_by(order_expression)
        )

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

        results = []
        for req in pagination.items:
            details = json.loads(req.request_details) if req.request_details else {}
            results.append({
                "id": str(req.id),
                "created_at": req.created_at.isoformat(),
                "request_type": req.request_type.value,
                "status": req.status.value,
                "requested_mb": details.get("requested_mb"),
                "requested_duration_days": details.get("requested_duration_days"),
                "processed_at": req.processed_at.isoformat() if req.processed_at else None,
                "rejection_reason": req.rejection_reason,
                "processed_by_admin": req.processed_by.full_name if req.processed_by else None,
            })

        return jsonify({
            "items": results,
            "totalItems": pagination.total
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error mengambil riwayat permintaan untuk komandan {current_user.id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat riwayat permintaan."}), HTTPStatus.INTERNAL_SERVER_ERROR