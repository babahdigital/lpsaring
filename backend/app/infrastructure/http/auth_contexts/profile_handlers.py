from __future__ import annotations

from http import HTTPStatus

from flask import current_app, jsonify
from pydantic import ValidationError


def get_current_user_impl(
    *,
    current_user_id,
    db,
    User,
    UserMeResponseSchema,
    AuthErrorResponseSchema,
    is_demo_phone_allowed,
    build_status_error,
    create_access_token,
    set_auth_cookie,
    validation_error_details,
):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not user.is_active:
        return build_status_error("inactive", "User account is not active."), HTTPStatus.FORBIDDEN
    if getattr(user, "is_blocked", False):
        return build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN
    try:
        payload = UserMeResponseSchema.model_validate(user).model_dump(mode="json")
        payload["is_demo_user"] = is_demo_phone_allowed(str(user.phone_number or ""))
        response = jsonify(payload)
        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        refreshed_access_token = create_access_token(data=jwt_payload)
        set_auth_cookie(response, refreshed_access_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        current_app.logger.error(f"[/me] Pydantic validation FAILED for user {user.id}: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(
                error="User data on server is invalid.", details=validation_error_details(e)
            ).model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


def update_user_profile_impl(
    *,
    current_user_id,
    db,
    User,
    UserRole,
    ApprovalStatus,
    request,
    UserProfileUpdateRequestSchema,
    UserMeResponseSchema,
    AuthErrorResponseSchema,
    is_demo_phone_allowed,
    validation_error_details,
):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return jsonify(
            AuthErrorResponseSchema(error="Your account is not active or approved to update profile.").model_dump()
        ), HTTPStatus.FORBIDDEN

    try:
        update_data = UserProfileUpdateRequestSchema.model_validate(request.get_json())
        user.full_name = update_data.full_name
        if user.role == UserRole.USER:
            user.blok = update_data.blok
            user.kamar = update_data.kamar
        db.session.commit()
        payload = UserMeResponseSchema.model_validate(user).model_dump(mode="json")
        payload["is_demo_user"] = is_demo_phone_allowed(str(user.phone_number or ""))
        return jsonify(payload), HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update user profile {user.id}: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An internal error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR
