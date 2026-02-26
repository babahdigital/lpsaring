from __future__ import annotations

from http import HTTPStatus

from flask import current_app, jsonify
from pydantic import ValidationError


def consume_session_token_impl(
    *,
    payload,
    db,
    User,
    ApprovalStatus,
    SessionTokenRequestSchema,
    VerifyOtpResponseSchema,
    AuthErrorResponseSchema,
    consume_session_token,
    build_status_error,
    create_access_token,
    issue_refresh_token_for_user,
    set_auth_cookie,
    set_refresh_cookie,
    validation_error_details,
    user_agent,
):
    try:
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        data = SessionTokenRequestSchema.model_validate(payload)
        user_id = consume_session_token(data.token)
        if not user_id:
            return jsonify(
                AuthErrorResponseSchema(error="Session token tidak valid atau kedaluwarsa.").model_dump()
            ), HTTPStatus.UNAUTHORIZED

        user = db.session.get(User, user_id)
        if not user:
            return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
        if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            return build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
        if getattr(user, "is_blocked", False):
            return build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        access_token = create_access_token(data=jwt_payload)

        refresh_token = issue_refresh_token_for_user(user.id, user_agent=user_agent)
        response = jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump())
        set_auth_cookie(response, access_token)
        set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /session/consume: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR
