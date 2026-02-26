from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import current_app, jsonify
from pydantic import ValidationError
from sqlalchemy import select

from app.infrastructure.db.models import ApprovalStatus, User


def request_otp_impl(
    *,
    payload: dict[str, Any] | None,
    db,
    RequestOtpRequestSchema,
    RequestOtpResponseSchema,
    AuthErrorResponseSchema,
    normalize_to_e164,
    increment_metric,
    is_otp_cooldown_active,
    is_demo_phone_allowed,
    get_phone_number_variations,
    set_otp_cooldown,
    build_status_error,
    generate_otp,
    store_otp_in_redis,
    send_otp_whatsapp,
    validation_error_details,
):
    try:
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST
        data = RequestOtpRequestSchema.model_validate(payload)

        try:
            phone_e164 = normalize_to_e164(data.phone_number)
        except ValueError as e:
            increment_metric("otp.request.failed")
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        if is_otp_cooldown_active(phone_e164):
            return jsonify(
                AuthErrorResponseSchema(
                    error="Terlalu sering meminta OTP. Silakan coba beberapa saat lagi."
                ).model_dump()
            ), HTTPStatus.TOO_MANY_REQUESTS

        demo_phone_allowed = is_demo_phone_allowed(phone_e164)
        phone_variations = get_phone_number_variations(phone_e164)
        user_for_otp = db.session.execute(
            select(User).where(User.phone_number.in_(phone_variations))
        ).scalar_one_or_none()
        if not user_for_otp:
            if demo_phone_allowed:
                set_otp_cooldown(phone_e164)
                increment_metric("otp.request.success")
                current_app.logger.warning("OTP request demo accepted for non-registered phone: %s", phone_e164)
                return jsonify(
                    RequestOtpResponseSchema(message="Kode OTP berhasil diproses. Silakan lanjut verifikasi.").model_dump()
                ), HTTPStatus.OK

            increment_metric("otp.request.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Phone number is not registered.").model_dump()
            ), HTTPStatus.NOT_FOUND

        if not user_for_otp.is_active or user_for_otp.approval_status != ApprovalStatus.APPROVED:
            increment_metric("otp.request.failed")
            return build_status_error(
                "inactive", "Login failed. Your account is not active or approved yet."
            ), HTTPStatus.FORBIDDEN

        otp_generated = generate_otp()
        if not store_otp_in_redis(phone_e164, otp_generated):
            if current_app.config.get("OTP_ALLOW_BYPASS", False):
                current_app.logger.warning("Redis OTP unavailable; bypass mode enabled.")
            else:
                increment_metric("otp.request.failed")
                return jsonify(
                    AuthErrorResponseSchema(error="Failed to process OTP request.").model_dump()
                ), HTTPStatus.INTERNAL_SERVER_ERROR

        send_otp_whatsapp(phone_e164, otp_generated)
        set_otp_cooldown(phone_e164)
        increment_metric("otp.request.success")

        return jsonify(RequestOtpResponseSchema().model_dump()), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /request-otp: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR
