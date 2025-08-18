# backend/app/infrastructure/http/public_user_routes.py
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportAssignmentType=false

import requests
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus
from app.extensions import db
from app.infrastructure.db.models import User

# --- SKEMA Pydantic ---
from .schemas.user_schemas import (
    PhoneCheckRequest,
    PhoneCheckResponse,
    WhatsappValidationRequest,
)

# --- HELPER BARU ---
from .helpers.request_parsers import parse_json_and_validate

public_user_bp = Blueprint("public_user_api", __name__)


# ------------------------------------------------------------------- #
# 1. /check-or-register
# ------------------------------------------------------------------- #
@public_user_bp.route("/check-or-register", methods=["POST"])
def check_or_register_phone():
    current_app.logger.info("POST /api/users/check-or-register")

    parsed = parse_json_and_validate(PhoneCheckRequest, log_prefix="[Check Phone] ")
    if isinstance(parsed, tuple):          # -> (response, status)
        return parsed
    req_data: PhoneCheckRequest = parsed
    phone_number, full_name = req_data.phone_number, req_data.full_name

    try:
        user = db.session.execute(
            select(User).filter_by(phone_number=phone_number)
        ).scalar_one_or_none()

        if not user:
            current_app.logger.info(f"[Check Phone] {phone_number} belum terdaftar")
            return (
                jsonify(
                    PhoneCheckResponse(
                        user_exists=False,
                        message="Nomor telepon belum terdaftar.",
                    ).model_dump()
                ),
                HTTPStatus.OK,
            )

        # User ditemukan – opsional update nama
        if not user.full_name and full_name:
            try:
                user.full_name = full_name
                db.session.commit()
            except SQLAlchemyError as ex:
                db.session.rollback()
                current_app.logger.error(
                    f"[Check Phone] Gagal update nama user {user.id}: {ex}",
                    exc_info=True,
                )

        return (
            jsonify(
                PhoneCheckResponse(user_exists=True, user_id=user.id).model_dump()
            ),
            HTTPStatus.OK,
        )

    except SQLAlchemyError as ex:
        db.session.rollback()
        current_app.logger.error(
            f"[Check Phone] DB error untuk {phone_number}: {ex}", exc_info=True
        )
        return (
            jsonify(
                {"success": False, "message": "Gagal proses database (check-or-register)."}
            ),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------- #
# 2. /validate-whatsapp
# ------------------------------------------------------------------- #
@public_user_bp.route("/validate-whatsapp", methods=["POST"])
def validate_whatsapp_number():
    """
    1. Pastikan nomor **belum** ada di DB.
    2. Panggil Fonnte utk cek status WhatsApp.
    """
    current_app.logger.info("POST /api/users/validate-whatsapp")

    parsed = parse_json_and_validate(
        WhatsappValidationRequest,
        aliases={"phoneNumber": "phone_number"},
        log_prefix="[Validate WA] ",
    )
    if isinstance(parsed, tuple):
        return parsed
    req_data: WhatsappValidationRequest = parsed
    phone_number_e164 = req_data.phone_number

    # -- LANGKAH 1: Cek DB --------------------------------------------------
    try:
        exists = db.session.scalar(
            select(User.id).filter_by(phone_number=phone_number_e164)
        )
        if exists:
            return (
                jsonify(
                    {"isValid": False, "message": "Nomor telepon ini sudah terdaftar di sistem"}
                ),
                HTTPStatus.OK,
            )
    except SQLAlchemyError as ex:
        current_app.logger.error(f"[Validate WA] DB error: {ex}", exc_info=True)
        return (
            jsonify({"isValid": False, "message": "Gagal memeriksa database"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    # -- LANGKAH 2: Panggil Fonnte -----------------------------------------
    token = current_app.config.get("WHATSAPP_API_KEY")
    if not token:
        current_app.logger.error("[Validate WA] WHATSAPP_API_KEY unset")
        return (
            jsonify({"isValid": False, "message": "Layanan validasi tidak terkonfigurasi"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    target = phone_number_e164.lstrip("+")
    try:
        r = requests.post(
            "https://api.fonnte.com/validate",
            headers={"Authorization": token},
            data={"target": target},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.error(f"Fonnte error {r.status_code}: {r.text[:120]}")
            return (
                jsonify({"isValid": False, "message": "Layanan validasi sementara tidak tersedia"}),
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

        data = r.json()
        if data.get("status") is True:
            registered = data.get("registered", [])
            if target in registered:
                return jsonify({"isValid": True}), HTTPStatus.OK
            return (
                jsonify({"isValid": False, "message": "Nomor tidak aktif di WhatsApp"}),
                HTTPStatus.OK,
            )

        reason = data.get("reason", "alasan tidak diketahui")
        return (
            jsonify({"isValid": False, "message": f"Validasi gagal: {reason}"}),
            HTTPStatus.BAD_REQUEST,
        )

    except requests.exceptions.Timeout:
        return (
            jsonify({"isValid": False, "message": "Timeout menghubungi layanan validasi"}),
            HTTPStatus.GATEWAY_TIMEOUT,
        )
    except requests.exceptions.RequestException as ex:
        current_app.logger.error(f"Fonnte koneksi error: {ex}", exc_info=True)
        return (
            jsonify({"isValid": False, "message": "Tidak dapat menghubungi layanan validasi"}),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except Exception as ex:
        current_app.logger.error(f"Unexpected error: {ex}", exc_info=True)
        return (
            jsonify(
                {"isValid": False, "message": "Terjadi kesalahan internal saat validasi"}
            ),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )