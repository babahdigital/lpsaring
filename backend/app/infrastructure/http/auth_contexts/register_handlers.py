from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from http import HTTPStatus

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from user_agents import parse as parse_user_agent


def register_user_impl(
    *,
    request,
    db,
    User,
    UserRole,
    ApprovalStatus,
    NotificationRecipient,
    NotificationType,
    UserRegisterRequestSchema,
    UserRegisterResponseSchema,
    AuthErrorResponseSchema,
    normalize_to_e164,
    get_phone_number_variations,
    settings_service,
    get_active_registration_bonus,
    get_notification_message,
    send_whatsapp_message,
    whatsapp_available: bool,
    validation_error_details,
):
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        try:
            normalized_phone_number = normalize_to_e164(data_input.phone_number)
        except ValueError as e:
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        phone_variations = get_phone_number_variations(normalized_phone_number)
        if db.session.execute(select(User.id).where(User.phone_number.in_(phone_variations))).scalar_one_or_none():
            return jsonify(
                AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()
            ), HTTPStatus.CONFLICT

        ua_string = request.headers.get("User-Agent")
        device_brand, device_model, raw_ua = None, None, None
        if ua_string:
            raw_ua = ua_string[:1024]
            ua_info = parse_user_agent(ua_string)
            device_brand = getattr(ua_info.device, "brand", None)
            device_model = getattr(ua_info.device, "model", None)

        new_user_obj = User(
            phone_number=normalized_phone_number,
            full_name=data_input.full_name,
            approval_status=ApprovalStatus.PENDING_APPROVAL,
            is_active=False,
            is_tamping=data_input.is_tamping,
            tamping_type=data_input.tamping_type,
            device_brand=device_brand,
            device_model=device_model,
            raw_user_agent=raw_ua,
            is_unlimited_user=False,
        )

        default_user_server = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_USER", "srv-user")
        default_komandan_server = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_KOMANDAN", "srv-komandan")

        if data_input.register_as_komandan:
            new_user_obj.role = UserRole.KOMANDAN
            new_user_obj.mikrotik_server_name = default_komandan_server
        else:
            new_user_obj.role = UserRole.USER
            new_user_obj.mikrotik_server_name = default_user_server
            if data_input.is_tamping:
                new_user_obj.blok = None
                new_user_obj.kamar = None
            else:
                new_user_obj.blok = data_input.blok
                new_user_obj.kamar = data_input.kamar

        inactive_profile = settings_service.get_setting(
            "MIKROTIK_INACTIVE_PROFILE", None
        ) or settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
        new_user_obj.mikrotik_profile_name = inactive_profile

        active_bonus = get_active_registration_bonus()
        if active_bonus and active_bonus.bonus_value_mb and active_bonus.bonus_duration_days:
            current_app.logger.info(
                "Menerapkan bonus registrasi '%s' untuk pendaftar baru %s",
                active_bonus.name,
                new_user_obj.full_name,
            )
            new_user_obj.total_quota_purchased_mb = active_bonus.bonus_value_mb
            new_user_obj.quota_expiry_date = datetime.now(dt_timezone.utc) + timedelta(days=active_bonus.bonus_duration_days)
        else:
            new_user_obj.total_quota_purchased_mb = 0
            new_user_obj.quota_expiry_date = None

        db.session.add(new_user_obj)
        db.session.commit()
        db.session.refresh(new_user_obj)

        try:
            if whatsapp_available and settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "False") == "True":
                user_context = {"full_name": new_user_obj.full_name}
                user_message = get_notification_message("user_self_register_pending", user_context)
                send_whatsapp_message(new_user_obj.phone_number, user_message)

                recipients_query = (
                    select(User)
                    .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
                    .where(
                        NotificationRecipient.notification_type == NotificationType.NEW_USER_REGISTRATION,
                        User.is_active,
                    )
                )
                recipients = db.session.scalars(recipients_query).all()
                if recipients:
                    admin_context = {
                        "full_name": new_user_obj.full_name,
                        "phone_number": new_user_obj.phone_number,
                        "blok": new_user_obj.blok if new_user_obj.blok else "N/A",
                        "kamar": new_user_obj.kamar if new_user_obj.kamar else "N/A",
                        "role": new_user_obj.role.value,
                    }
                    admin_message = get_notification_message("new_user_registration_to_admin", admin_context)
                    for admin in recipients:
                        send_whatsapp_message(admin.phone_number, admin_message)
        except Exception as e_notify:
            current_app.logger.error("Failed to send new user registration notifications: %s", e_notify, exc_info=True)

        return jsonify(
            UserRegisterResponseSchema(
                message="Registration successful. Your account is awaiting Admin approval.",
                user_id=new_user_obj.id,
                phone_number=new_user_obj.phone_number,
            ).model_dump()
        ), HTTPStatus.CREATED
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            AuthErrorResponseSchema(error="Phone number is already registered.").model_dump()
        ), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Unexpected error in /register: %s", e, exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred during registration.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR


from flask import current_app, jsonify
