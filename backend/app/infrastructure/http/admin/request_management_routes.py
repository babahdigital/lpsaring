# backend/app/infrastructure/http/admin/request_management_routes.py

import json
import os
import uuid
from flask import Blueprint, jsonify, request, current_app
from http import HTTPStatus
from pydantic import ValidationError
from sqlalchemy import select, desc, asc
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.extensions import db
from app.infrastructure.db.models import User, QuotaRequest, RequestStatus, RequestType, AdminActionLog, AdminActionType
from app.infrastructure.http.decorators import admin_required

# [PENYEMPURNAAN] Mengimpor skema yang telah diperbarui
from .schemas import RequestApprovalSchema, QuotaRequestListItemSchema, RequestApprovalAction
from app.services.notification_service import get_notification_message
from app.services import settings_service
from app.utils.formatters import format_to_local_phone, get_app_local_datetime

try:
    from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user

    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    MIKROTIK_CLIENT_AVAILABLE = False

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message

    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False

request_mgmt_bp = Blueprint("request_management_api", __name__)


def _is_mikrotik_operations_enabled() -> bool:
    raw = settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True")
    return str(raw or "").strip().lower() in {"true", "1", "t", "yes"}


def _handle_mikrotik_operation(operation_func, **kwargs):
    if not _is_mikrotik_operations_enabled():
        current_app.logger.info("Mikrotik operations disabled by setting. Skipping Mikrotik operation.")
        return True, "Mikrotik operations disabled."
    if not MIKROTIK_CLIENT_AVAILABLE:
        current_app.logger.warning("Mikrotik client not available. Skipping Mikrotik operation.")
        return False, "Mikrotik client not available."
    try:
        with get_mikrotik_connection() as api_conn:
            if api_conn:
                return operation_func(api_connection=api_conn, **kwargs)
            else:
                return False, "Failed to get Mikrotik connection."
    except Exception as e:
        current_app.logger.error(f"Exception during Mikrotik operation {operation_func.__name__}: {e}", exc_info=True)
        return False, f"Mikrotik Error: {str(e)}"


def _log_admin_action(admin: User, target_user_id: uuid.UUID, action_type: AdminActionType, details: dict):
    disable_super_admin_logs = str(os.getenv("DISABLE_SUPER_ADMIN_ACTION_LOGS", "false") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if disable_super_admin_logs and getattr(admin, "is_super_admin_role", False):
        return
    try:
        from flask import has_request_context, g

        if has_request_context():
            g.admin_action_logged = True
    except Exception:
        pass
    # NOTE: Hindari keyword-args pada declarative model agar Pylance tidak memunculkan
    # `reportCallIssue` (model SQLAlchemy tidak selalu terinferensi memiliki __init__(**kwargs)).
    log_entry = AdminActionLog()
    log_entry.admin_id = admin.id
    log_entry.target_user_id = target_user_id
    log_entry.action_type = action_type
    log_entry.details = json.dumps(details, default=str)
    db.session.add(log_entry)


@request_mgmt_bp.route("/quota-requests", methods=["GET"])
@admin_required
def get_all_requests(current_admin: User):
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("itemsPerPage", 10, type=int), 100)
        status_filter = request.args.get("status", type=str)
        sort_by_list = request.args.getlist("sortBy")
        sort_order_list = request.args.getlist("sortOrder")
        sort_by = sort_by_list[0] if sort_by_list else "created_at"
        sort_order = sort_order_list[0] if sort_order_list else "desc"

        base_query = db.select(QuotaRequest).options(
            selectinload(QuotaRequest.requester).load_only(User.id, User.full_name, User.phone_number),
            selectinload(QuotaRequest.processed_by).load_only(User.full_name),
        )

        if status_filter and status_filter.upper() in RequestStatus.__members__:
            base_query = base_query.where(QuotaRequest.status == RequestStatus[status_filter.upper()])

        sortable_columns = {
            "created_at": QuotaRequest.created_at,
            "requester.full_name": User.full_name,
            "status": QuotaRequest.status,
            "request_type": QuotaRequest.request_type,
        }
        if sort_by == "requester.full_name":
            base_query = base_query.join(User, QuotaRequest.requester_id == User.id)
        sort_column = sortable_columns.get(sort_by, QuotaRequest.created_at)
        if sort_order.lower() == "desc":
            final_query = base_query.order_by(desc(sort_column))
        else:
            final_query = base_query.order_by(asc(sort_column))

        pagination = db.paginate(final_query, page=page, per_page=per_page, error_out=False)

        results = []
        for req in pagination.items:
            req_data = QuotaRequestListItemSchema.model_validate(req, from_attributes=True).model_dump(mode="json")
            req_data["processed_by"] = {"full_name": req.processed_by.full_name} if req.processed_by else None
            req_data["granted_details"] = json.loads(req.granted_details) if req.granted_details else None
            results.append(req_data)

        return jsonify({"items": results, "totalItems": pagination.total}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error mengambil data permintaan kuota: {e}", exc_info=True)
        return jsonify(
            {"message": "Terjadi kesalahan internal saat mengambil data permintaan."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@request_mgmt_bp.route("/quota-requests/<uuid:request_id>/process", methods=["POST"])
@admin_required
def process_quota_request(current_admin: User, request_id: uuid.UUID):
    if not request.is_json:
        return jsonify({"message": "Request body harus JSON."}), HTTPStatus.BAD_REQUEST

    req_to_process = db.session.scalar(
        select(QuotaRequest).where(QuotaRequest.id == request_id).options(joinedload(QuotaRequest.requester))
    )
    if not req_to_process:
        return jsonify({"message": "Permintaan tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if req_to_process.status != RequestStatus.PENDING:
        return jsonify(
            {"message": f"Permintaan ini sudah diproses dengan status: {req_to_process.status.name}"}
        ), HTTPStatus.CONFLICT

    target_user = req_to_process.requester
    mikrotik_ops_enabled = _is_mikrotik_operations_enabled()
    if not target_user or (mikrotik_ops_enabled and not target_user.mikrotik_password):
        return jsonify(
            {"message": "Pengguna pemohon atau password hotspot tidak ditemukan. Setujui pengguna terlebih dahulu."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR

    try:
        data_input = RequestApprovalSchema.model_validate(request.json)
    except ValidationError as e:
        return jsonify({"message": "Input tidak valid.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    action_details = {}
    notification_template_key = ""
    notification_context = {}
    mikrotik_username = format_to_local_phone(target_user.phone_number)
    now_utc = datetime.now(timezone.utc)
    now_local = get_app_local_datetime()
    max_unlimited_days = settings_service.get_setting_as_int("KOMANDAN_MAX_UNLIMITED_DAYS", 30)
    max_quota_mb = settings_service.get_setting_as_int("KOMANDAN_MAX_QUOTA_MB", 51200)
    max_quota_days = settings_service.get_setting_as_int("KOMANDAN_MAX_QUOTA_DAYS", 30)
    admin_action_type: Optional[AdminActionType] = None

    if data_input.action == RequestApprovalAction.APPROVE:
        admin_action_type = AdminActionType.PROCESS_QUOTA_REQUEST_APPROVE

        # [PERBAIKAN UTAMA] Logika baru untuk approve UNLIMITED
        if req_to_process.request_type == RequestType.UNLIMITED:
            if not data_input.unlimited_duration_days:
                return jsonify({"message": "Durasi hari untuk akses unlimited wajib diisi."}), HTTPStatus.BAD_REQUEST

            if data_input.unlimited_duration_days > max_unlimited_days:
                return jsonify({"message": "Durasi unlimited melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST

            days_to_add = data_input.unlimited_duration_days
            new_expiry_date = now_local + timedelta(days=days_to_add)

            req_to_process.status = RequestStatus.APPROVED
            target_user.is_unlimited_user = True
            target_user.total_quota_purchased_mb = 0
            target_user.total_quota_used_mb = 0
            target_user.quota_expiry_date = new_expiry_date

            action_details = {"status": "APPROVED", "result": f"Unlimited access granted for {days_to_add} days."}
            notification_template_key = "komandan_request_unlimited_approved"
            notification_context = {"days_added": days_to_add}  # Konteks baru untuk notifikasi

            # [PERBAIKAN] Menggunakan profil unlimited dari settings
            unlimited_profile = settings_service.get_setting("MIKROTIK_UNLIMITED_PROFILE", "unlimited")
            # [PERBAIKAN] Menghitung session timeout dan menghapus limit bytes
            timeout_seconds = int((new_expiry_date - now_local).total_seconds())

            success, msg = _handle_mikrotik_operation(
                activate_or_update_hotspot_user,
                user_mikrotik_username=mikrotik_username,
                # [PERBAIKAN] Set profil ke 'unlimited'
                mikrotik_profile_name=unlimited_profile,
                hotspot_password=target_user.mikrotik_password,
                comment=f"UNLIMITED for {days_to_add}d Approved by {current_admin.full_name}",
                # [PERBAIKAN] Hapus limit kuota dan set timeout
                limit_bytes_total=0,
                session_timeout_seconds=max(0, timeout_seconds),
                server=target_user.mikrotik_server_name,
                force_update_profile=True,
            )
            if mikrotik_ops_enabled and not success:
                db.session.rollback()
                return jsonify({"message": f"Gagal sinkronisasi Mikrotik: {msg}"}), HTTPStatus.INTERNAL_SERVER_ERROR

        else:  # QUOTA (logika tidak berubah)
            req_to_process.status = RequestStatus.APPROVED
            details = json.loads(req_to_process.request_details or "{}")
            mb_to_add = details.get("requested_mb", 0)
            days_to_add = details.get("requested_duration_days", 0)

            if mb_to_add > max_quota_mb:
                return jsonify({"message": "Permintaan kuota melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST
            if days_to_add > max_quota_days:
                return jsonify({"message": "Durasi kuota melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST

            target_user.is_unlimited_user = False
            target_user.total_quota_purchased_mb = (target_user.total_quota_purchased_mb or 0) + mb_to_add
            current_expiry = target_user.quota_expiry_date
            new_expiry_date = (
                current_expiry if current_expiry and current_expiry > now_local else now_local
            ) + timedelta(days=days_to_add)
            target_user.quota_expiry_date = new_expiry_date

            gb_added = round(mb_to_add / 1024, 2)
            result_text = f"Kuota {gb_added} GB untuk {days_to_add} hari telah ditambahkan."
            action_details = {"status": "APPROVED", "result": result_text}

            notification_template_key = "komandan_request_quota_approved"
            notification_context = {"gb_added": gb_added, "days_added": days_to_add}

            remaining_quota_mb = max(0, target_user.total_quota_purchased_mb - (target_user.total_quota_used_mb or 0))
            limit_bytes = int(remaining_quota_mb * 1024 * 1024)
            timeout_seconds = int((new_expiry_date - now_local).total_seconds())

            komandan_profile = settings_service.get_setting("MIKROTIK_KOMANDAN_PROFILE", "komandan")
            success, msg = _handle_mikrotik_operation(
                activate_or_update_hotspot_user,
                user_mikrotik_username=mikrotik_username,
                mikrotik_profile_name=komandan_profile,
                hotspot_password=target_user.mikrotik_password,
                comment=f"QUOTA {gb_added}GB/{days_to_add}d added by {current_admin.full_name}",
                limit_bytes_total=max(1, limit_bytes),
                session_timeout_seconds=max(0, timeout_seconds),
                server=target_user.mikrotik_server_name,
            )
            if mikrotik_ops_enabled and not success:
                db.session.rollback()
                return jsonify({"message": f"Gagal sinkronisasi Mikrotik: {msg}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    elif data_input.action == RequestApprovalAction.REJECT:
        # Logika reject tidak berubah
        admin_action_type = AdminActionType.PROCESS_QUOTA_REQUEST_REJECT
        req_to_process.status = RequestStatus.REJECTED
        req_to_process.rejection_reason = data_input.rejection_reason
        action_details = {"status": "REJECTED", "reason": data_input.rejection_reason}
        notification_template_key = "komandan_request_rejected"
        notification_context = {
            "request_type": req_to_process.request_type.value,
            "reason": data_input.rejection_reason,
        }

    elif data_input.action == RequestApprovalAction.REJECT_AND_GRANT_QUOTA:
        # Logika grant partial tidak berubah
        admin_action_type = AdminActionType.PROCESS_QUOTA_REQUEST_PARTIALLY_APPROVED
        req_to_process.status = RequestStatus.PARTIALLY_APPROVED
        req_to_process.rejection_reason = data_input.rejection_reason

        mb_to_add = data_input.granted_quota_mb or 0
        days_to_add = data_input.granted_duration_days or 0

        if mb_to_add > max_quota_mb:
            return jsonify({"message": "Kuota parsial melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST
        if days_to_add > max_quota_days:
            return jsonify({"message": "Durasi parsial melebihi batas maksimum."}), HTTPStatus.BAD_REQUEST

        req_to_process.granted_details = json.dumps({"granted_mb": mb_to_add, "granted_duration_days": days_to_add})

        target_user.is_unlimited_user = False
        target_user.total_quota_purchased_mb = (target_user.total_quota_purchased_mb or 0) + mb_to_add
        current_expiry = target_user.quota_expiry_date
        new_expiry_date = (current_expiry if current_expiry and current_expiry > now_local else now_local) + timedelta(
            days=days_to_add
        )
        target_user.quota_expiry_date = new_expiry_date

        granted_gb = round(mb_to_add / 1024, 2)
        result_text = f"Anda diberikan kuota {granted_gb} GB untuk {days_to_add} hari."
        action_details = {"status": "PARTIALLY_APPROVED", "reason": data_input.rejection_reason, "result": result_text}

        notification_template_key = "komandan_request_quota_partially_approved"
        notification_context = {
            "reason": data_input.rejection_reason,
            "granted_gb": granted_gb,
            "granted_days": days_to_add,
        }

        remaining_quota_mb = max(0, target_user.total_quota_purchased_mb - (target_user.total_quota_used_mb or 0))
        limit_bytes = int(remaining_quota_mb * 1024 * 1024)
        timeout_seconds = int((new_expiry_date - now_local).total_seconds())

        komandan_profile = settings_service.get_setting("MIKROTIK_KOMANDAN_PROFILE", "komandan")
        success, msg = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=mikrotik_username,
            mikrotik_profile_name=komandan_profile,
            hotspot_password=target_user.mikrotik_password,
            comment=f"Partial Grant {granted_gb}GB/{days_to_add}d by {current_admin.full_name}",
            limit_bytes_total=max(1, limit_bytes),
            session_timeout_seconds=max(0, timeout_seconds),
            server=target_user.mikrotik_server_name,
        )
        if mikrotik_ops_enabled and not success:
            db.session.rollback()
            return jsonify({"message": f"Gagal sinkronisasi Mikrotik: {msg}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    req_to_process.processed_by_id = current_admin.id
    req_to_process.processed_at = now_utc
    if admin_action_type:
        _log_admin_action(current_admin, target_user.id, admin_action_type, action_details)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyimpan ke DB saat memproses permintaan: {e}", exc_info=True)
        return jsonify(
            {"message": f"Gagal menyimpan perubahan ke database. Error: {str(e)}"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR

    try:
        if WHATSAPP_AVAILABLE and notification_template_key:
            message_body = get_notification_message(notification_template_key, notification_context)
            send_whatsapp_message(target_user.phone_number, message_body)
    except Exception as e_notify:
        current_app.logger.error(
            f"Gagal mengirim notifikasi hasil proses permintaan kepada Komandan {target_user.id}: {e_notify}",
            exc_info=True,
        )

    return jsonify(
        {"message": "Permintaan berhasil diproses.", "new_status": req_to_process.status.name}
    ), HTTPStatus.OK
