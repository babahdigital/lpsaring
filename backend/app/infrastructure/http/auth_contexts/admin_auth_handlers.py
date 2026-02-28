from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Any, cast

from flask import jsonify


def admin_login_impl(
    *,
    request,
    db,
    User,
    ApprovalStatus,
    UserLoginHistory,
    verify_password,
    increment_metric,
    get_client_ip,
    format_to_local_phone,
    format_datetime_to_wita,
    settings_service,
    get_notification_message,
    send_whatsapp_message,
    whatsapp_available,
    create_access_token,
    issue_refresh_token_for_user,
    set_auth_cookie,
    set_refresh_cookie,
    VerifyOtpResponseSchema,
    get_phone_number_variations,
    validate_phone_number,
):
    if not request.is_json:
        return jsonify({"message": "Request body must be JSON."}), HTTPStatus.BAD_REQUEST
    data = request.get_json()
    username_input = data.get("username")
    password = data.get("password")
    if isinstance(username_input, str):
        username_input = username_input.strip()
    if not username_input or not password:
        return jsonify({"message": "Username and password are required."}), HTTPStatus.BAD_REQUEST

    try:
        normalized_phone = validate_phone_number(username_input)
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST

    phone_variations = get_phone_number_variations(normalized_phone)
    user_to_login = db.session.execute(
        db.select(User).filter(User.phone_number.in_(phone_variations))
    ).scalar_one_or_none()

    if (
        not user_to_login
        or not user_to_login.is_admin_role
        or not user_to_login.is_active
        or user_to_login.approval_status != ApprovalStatus.APPROVED
        or not user_to_login.password_hash
        or not verify_password(user_to_login.password_hash, password)
    ):
        increment_metric("admin.login.failed")
        return jsonify({"message": "Invalid username or password."}), HTTPStatus.UNAUTHORIZED

    user_to_login.last_login_at = datetime.now(dt_timezone.utc)
    new_login_entry = cast(Any, UserLoginHistory)(
        user_id=user_to_login.id, ip_address=get_client_ip(), user_agent_string=request.headers.get("User-Agent")
    )
    db.session.add(new_login_entry)
    db.session.commit()

    try:
        if whatsapp_available and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            context = {
                "phone_number": format_to_local_phone(user_to_login.phone_number),
                "login_time": format_datetime_to_wita(user_to_login.last_login_at),
            }
            message_body = get_notification_message("admin_login_notification", context)
            send_whatsapp_message(user_to_login.phone_number, message_body)
    except Exception:
        pass

    jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
    access_token = create_access_token(data=jwt_payload)
    refresh_token = issue_refresh_token_for_user(user_to_login.id, user_agent=request.headers.get("User-Agent"))
    increment_metric("admin.login.success")
    response = jsonify(VerifyOtpResponseSchema(access_token=access_token).model_dump())
    set_auth_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    return response, HTTPStatus.OK


def refresh_access_token_impl(
    *,
    request,
    current_app,
    db,
    User,
    ApprovalStatus,
    AuthErrorResponseSchema,
    rotate_refresh_token,
    create_access_token,
    set_auth_cookie,
    set_refresh_cookie,
    build_status_error,
):
    refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
    raw_refresh = request.cookies.get(refresh_cookie_name)
    if not raw_refresh:
        return jsonify(AuthErrorResponseSchema(error="Refresh token missing.").model_dump()), HTTPStatus.UNAUTHORIZED

    user_agent = request.headers.get("User-Agent")
    rotated = rotate_refresh_token(raw_refresh, user_agent=user_agent)
    if not rotated:
        return jsonify(
            AuthErrorResponseSchema(error="Refresh token invalid or expired.").model_dump()
        ), HTTPStatus.UNAUTHORIZED

    try:
        user_id = uuid.UUID(rotated.user_id)
    except Exception:
        return jsonify(AuthErrorResponseSchema(error="Refresh token invalid.").model_dump()), HTTPStatus.UNAUTHORIZED

    user = db.session.get(User, user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.UNAUTHORIZED
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        return build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
    if getattr(user, "is_blocked", False):
        return build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

    jwt_payload = {"sub": str(user.id), "rl": user.role.value}
    access_token = create_access_token(data=jwt_payload)
    response = jsonify({"access_token": access_token, "token_type": "bearer"})
    set_auth_cookie(response, access_token)
    set_refresh_cookie(response, rotated.new_refresh_token)
    return response, HTTPStatus.OK


def logout_user_impl(
    *,
    current_user_id,
    request,
    current_app,
    db,
    User,
    revoke_refresh_token,
    clear_auth_cookie,
    clear_refresh_cookie,
    cleanup_user_network_on_logout,
):
    current_app.logger.info(f"User {current_user_id} initiated logout.")

    try:
        user = db.session.get(User, current_user_id)
    except Exception:
        user = None

    if user is not None and cleanup_user_network_on_logout is not None:
        try:
            cleanup_summary = cleanup_user_network_on_logout(user)
            current_app.logger.info(
                "Logout network reset summary user=%s: %s",
                current_user_id,
                cleanup_summary,
            )
        except Exception as e:
            current_app.logger.warning(
                "Logout network reset gagal untuk user=%s: %s",
                current_user_id,
                e,
            )

    refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
    raw_refresh = request.cookies.get(refresh_cookie_name)
    if raw_refresh:
        try:
            revoke_refresh_token(raw_refresh)
        except Exception:
            pass

    response = jsonify({"message": "Logout successful"})
    clear_auth_cookie(response)
    clear_refresh_cookie(response)
    return response, HTTPStatus.OK


def reset_login_user_impl(
    *,
    current_user_id,
    current_app,
    db,
    User,
    cleanup_user_network_on_logout,
):
    current_app.logger.info(f"User {current_user_id} initiated reset-login.")

    try:
        user = db.session.get(User, current_user_id)
    except Exception:
        user = None

    if user is None:
        return jsonify({"message": "User tidak ditemukan."}), HTTPStatus.NOT_FOUND

    cleanup_summary: dict[str, Any] = {}
    if cleanup_user_network_on_logout is not None:
        try:
            cleanup_summary = cleanup_user_network_on_logout(user)
            current_app.logger.info(
                "Reset-login network summary user=%s: %s",
                current_user_id,
                cleanup_summary,
            )
        except Exception as e:
            current_app.logger.warning(
                "Reset-login gagal untuk user=%s: %s",
                current_user_id,
                e,
            )
            return jsonify({"message": "Reset login gagal. Silakan coba lagi."}), HTTPStatus.INTERNAL_SERVER_ERROR

    return (
        jsonify(
            {
                "message": "Reset login berhasil. Silakan login hotspot ulang jika diperlukan.",
                "network_reset": cleanup_summary,
            }
        ),
        HTTPStatus.OK,
    )
