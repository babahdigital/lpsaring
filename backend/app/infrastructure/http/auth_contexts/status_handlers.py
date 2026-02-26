from __future__ import annotations

import uuid
from http import HTTPStatus

from flask import current_app, jsonify
from pydantic import ValidationError
from sqlalchemy import select


def verify_status_token_impl(*, payload, StatusTokenVerifyRequestSchema, AuthErrorResponseSchema, verify_status_token, validation_error_details):
    try:
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        data = StatusTokenVerifyRequestSchema.model_validate(payload)
        is_valid = verify_status_token(data.token, data.status)
        return jsonify({"valid": is_valid}), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /status-token/verify: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


def debug_binding_impl(*, payload, db, User, AuthErrorResponseSchema, get_phone_number_variations, resolve_binding_context):
    if current_app.config.get("FLASK_ENV") == "production":
        return jsonify(AuthErrorResponseSchema(error="Endpoint tidak tersedia.").model_dump()), HTTPStatus.NOT_FOUND

    if not payload or not isinstance(payload, dict):
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    user_id_raw = payload.get("user_id")
    phone_number = payload.get("phone_number")
    client_ip = payload.get("client_ip")
    client_mac = payload.get("client_mac")

    user = None
    if user_id_raw:
        try:
            user = db.session.get(User, uuid.UUID(str(user_id_raw)))
        except (ValueError, TypeError):
            return jsonify(AuthErrorResponseSchema(error="user_id tidak valid.").model_dump()), HTTPStatus.BAD_REQUEST
    elif phone_number:
        variations = get_phone_number_variations(str(phone_number))
        user = db.session.execute(select(User).where(User.phone_number.in_(variations))).scalar_one_or_none()
    else:
        return jsonify(
            AuthErrorResponseSchema(error="user_id atau phone_number wajib diisi.").model_dump()
        ), HTTPStatus.BAD_REQUEST

    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND

    context = resolve_binding_context(user, client_ip, client_mac)
    mac_only = (
        (not context.get("input_ip")) and bool(context.get("input_mac")) and context.get("ip_source") == "device_mac"
    )
    return jsonify(
        {
            "user_id": str(user.id),
            "phone_number": user.phone_number,
            "binding": context,
            "mac_only": mac_only,
        }
    ), HTTPStatus.OK
