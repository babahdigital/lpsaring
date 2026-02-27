from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus


def get_my_telegram_status_impl(*, current_user_id, db, User):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    chat_id = getattr(user, "telegram_chat_id", None)
    username = getattr(user, "telegram_username", None)
    linked_at = getattr(user, "telegram_linked_at", None)

    return jsonify(
        {
            "linked": bool(chat_id),
            "chat_id": chat_id,
            "username": username,
            "linked_at": linked_at.isoformat() if linked_at else None,
        }
    ), HTTPStatus.OK


def unlink_my_telegram_impl(*, current_user_id, db, User):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    user.telegram_chat_id = None
    user.telegram_username = None
    user.telegram_linked_at = None
    db.session.commit()
    return jsonify({"message": "Telegram berhasil diputus."}), HTTPStatus.OK


def create_my_telegram_link_token_impl(*, current_user_id, db, User, settings_service, generate_user_link_token, current_app):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    bot_username = str(settings_service.get_setting("TELEGRAM_BOT_USERNAME", "") or "").strip().lstrip("@")
    if not bot_username:
        return jsonify(
            {
                "message": "TELEGRAM_BOT_USERNAME belum disetel oleh admin.",
            }
        ), HTTPStatus.BAD_REQUEST

    token = generate_user_link_token(user_id=str(user.id))
    link_url = f"https://t.me/{bot_username}?start={token}"
    max_age = int(current_app.config.get("TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS", 600))

    return jsonify(
        {
            "token": token,
            "link_url": link_url,
            "expires_in_seconds": max_age,
            "bot_username": bot_username,
        }
    ), HTTPStatus.OK


def reset_hotspot_password_impl(
    *,
    current_user_id,
    db,
    User,
    ApprovalStatus,
    WHATSAPP_AVAILABLE,
    settings_service,
    _generate_password,
    format_to_local_phone,
    _handle_mikrotik_operation,
    activate_or_update_hotspot_user,
    get_notification_message,
    send_whatsapp_message,
    error_response,
    current_app,
):
    current_user = db.session.get(User, current_user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND
    if current_user.is_admin_role:
        return jsonify({"message": "Access denied. This feature is not for admin roles."}), HTTPStatus.FORBIDDEN
    if not current_user.is_active or current_user.approval_status != ApprovalStatus.APPROVED:
        return jsonify(
            {"message": "Your account is not active or approved. Cannot reset password."}
        ), HTTPStatus.FORBIDDEN

    try:
        new_mikrotik_password = _generate_password(length=6, numeric_only=True)
        mikrotik_username = format_to_local_phone(current_user.phone_number)

        mikrotik_success, mikrotik_message = _handle_mikrotik_operation(
            activate_or_update_hotspot_user,
            user_mikrotik_username=mikrotik_username,
            hotspot_password=new_mikrotik_password,
            mikrotik_profile_name=current_user.mikrotik_profile_name,
            server=current_user.mikrotik_server_name,
            comment="Password reset by user via Portal",
        )

        if not mikrotik_success:
            return jsonify(
                {"success": False, "message": f"Gagal mereset password di Mikrotik. Error: {mikrotik_message}"}
            ), HTTPStatus.INTERNAL_SERVER_ERROR

        current_user.mikrotik_password = new_mikrotik_password
        db.session.commit()

        if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            context = {
                "full_name": current_user.full_name,
                "hotspot_username": mikrotik_username,
                "hotspot_password": new_mikrotik_password,
            }
            message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
            send_whatsapp_message(current_user.phone_number, message_body)

        return jsonify(
            {"success": True, "message": "Password hotspot baru berhasil dibuat dan dikirim via WhatsApp."}
        ), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            "Internal error while resetting hotspot password for user %s: %s",
            current_user.id,
            e,
            exc_info=True,
        )
        return error_response("An internal error occurred.", status_code=HTTPStatus.INTERNAL_SERVER_ERROR)


def change_my_password_impl(
    *,
    current_user_id,
    request,
    db,
    User,
    ChangePasswordRequestSchema,
    ValidationError,
    check_password_hash,
    generate_password_hash,
    WHATSAPP_AVAILABLE,
    settings_service,
    format_datetime_to_wita,
    get_notification_message,
    send_whatsapp_message,
    current_app,
):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"message": "User not found."}), HTTPStatus.NOT_FOUND

    if not user.is_admin_role:
        return jsonify({"message": "This feature is for Admins only."}), HTTPStatus.FORBIDDEN

    data = request.get_json()
    try:
        validated_data = ChangePasswordRequestSchema.model_validate(data)
    except ValidationError as e:
        return jsonify({"message": "Invalid input.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    if not user.password_hash or not check_password_hash(user.password_hash, validated_data.current_password):
        return jsonify({"message": "Current password is incorrect."}), HTTPStatus.UNAUTHORIZED

    user.password_hash = generate_password_hash(validated_data.new_password)
    db.session.commit()

    try:
        if WHATSAPP_AVAILABLE and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
            change_time_wita = format_datetime_to_wita(datetime.now(dt_timezone.utc))
            context = {"phone_number": user.phone_number, "change_time": change_time_wita}
            message_body = get_notification_message("password_change_notification", context)
            send_whatsapp_message(user.phone_number, message_body)
    except Exception as e_notif:
        current_app.logger.error(
            "Failed to send password change notification for admin %s: %s", user.id, e_notif, exc_info=True
        )

    return jsonify({"message": "Password changed successfully."}), HTTPStatus.OK


from flask import jsonify
