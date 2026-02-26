from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Any, Optional, cast

from flask import current_app, jsonify
from pydantic import ValidationError
from sqlalchemy import select


def verify_otp_impl(
    *,
    payload,
    request,
    db,
    User,
    UserRole,
    ApprovalStatus,
    UserDevice,
    UserLoginHistory,
    VerifyOtpRequestSchema,
    VerifyOtpResponseSchema,
    AuthErrorResponseSchema,
    normalize_to_e164,
    get_phone_number_variations,
    is_demo_phone_allowed,
    get_otp_fail_count,
    increment_otp_fail_count,
    clear_otp_fail_count,
    increment_metric,
    verify_otp_from_redis,
    create_access_token,
    issue_refresh_token_for_user,
    store_session_token,
    format_to_local_phone,
    is_hotspot_login_required,
    resolve_binding_context,
    apply_device_binding_for_login,
    sync_address_list_for_single_user,
    build_status_error,
    validation_error_details,
    set_auth_cookie,
    set_refresh_cookie,
    settings_service,
    generate_password_hash,
    secrets_module,
):
    try:
        if not payload:
            return jsonify(
                AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        payload_dict: dict[str, Any] = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
        if payload_dict:
            if not payload_dict.get("client_ip"):
                candidate_ip = (
                    payload_dict.get("clientIp")
                    or payload_dict.get("ip")
                    or payload_dict.get("client-ip")
                    or request.args.get("client_ip")
                    or request.args.get("ip")
                    or request.args.get("client-ip")
                )
                if candidate_ip is not None:
                    payload_dict["client_ip"] = candidate_ip
            if not payload_dict.get("client_mac"):
                candidate_mac = (
                    payload_dict.get("clientMac")
                    or payload_dict.get("mac")
                    or payload_dict.get("mac-address")
                    or payload_dict.get("client-mac")
                    or request.args.get("client_mac")
                    or request.args.get("mac")
                    or request.args.get("mac-address")
                    or request.args.get("client-mac")
                )
                if candidate_mac is not None:
                    payload_dict["client_mac"] = candidate_mac
            if payload_dict.get("hotspot_login_context") is None:
                candidate_ctx = (
                    payload_dict.get("hotspotLoginContext")
                    or request.args.get("hotspot_login_context")
                    or request.args.get("hotspotLoginContext")
                )
                if candidate_ctx is not None:
                    payload_dict["hotspot_login_context"] = candidate_ctx

        data = VerifyOtpRequestSchema.model_validate(payload_dict)

        try:
            phone_e164 = normalize_to_e164(data.phone_number)
        except ValueError as e:
            increment_metric("otp.verify.failed")
            return jsonify(AuthErrorResponseSchema(error=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY

        fail_count = get_otp_fail_count(phone_e164)
        max_attempts = int(current_app.config.get("OTP_VERIFY_MAX_ATTEMPTS", 5))
        if fail_count >= max_attempts:
            increment_metric("otp.verify.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Terlalu banyak percobaan OTP. Silakan coba lagi nanti.").model_dump()
            ), HTTPStatus.TOO_MANY_REQUESTS

        otp_bypass_code = str(current_app.config.get("OTP_BYPASS_CODE", "000000") or "000000")
        bypass_allowed = current_app.config.get("OTP_ALLOW_BYPASS", False)
        demo_bypass_code = str(current_app.config.get("DEMO_BYPASS_OTP_CODE", "000000") or "000000")
        demo_bypass_allowed = is_demo_phone_allowed(phone_e164)
        used_bypass_code = False
        used_demo_bypass = False

        otp_ok = verify_otp_from_redis(phone_e164, data.otp)
        if not otp_ok:
            if bypass_allowed and data.otp == otp_bypass_code:
                current_app.logger.warning("OTP bypass global digunakan untuk login.")
                otp_ok = True
                used_bypass_code = True
            elif demo_bypass_allowed and data.otp == demo_bypass_code:
                current_app.logger.warning("OTP bypass demo digunakan untuk nomor whitelist demo.")
                otp_ok = True
                used_bypass_code = True
                used_demo_bypass = True

        if not otp_ok:
            increment_otp_fail_count(phone_e164)
            increment_metric("otp.verify.failed")
            return jsonify(
                AuthErrorResponseSchema(error="Invalid or expired OTP code.").model_dump()
            ), HTTPStatus.UNAUTHORIZED

        clear_otp_fail_count(phone_e164)
        increment_metric("otp.verify.success")

        phone_variations = get_phone_number_variations(phone_e164)
        user_to_login = db.session.execute(
            select(User).where(User.phone_number.in_(phone_variations))
        ).scalar_one_or_none()

        if not user_to_login:
            if used_demo_bypass and current_app.config.get("DEMO_MODE_ENABLED", False):
                return jsonify(
                    AuthErrorResponseSchema(error="Nomor demo belum disiapkan oleh sistem.").model_dump()
                ), HTTPStatus.FORBIDDEN
            return jsonify(
                AuthErrorResponseSchema(error="User not found after OTP verification.").model_dump()
            ), HTTPStatus.INTERNAL_SERVER_ERROR
        if not user_to_login.is_active or user_to_login.approval_status != ApprovalStatus.APPROVED:
            return build_status_error("inactive", "Account is not active or approved."), HTTPStatus.FORBIDDEN
        if getattr(user_to_login, "is_blocked", False):
            return build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        is_demo_login = bool(is_demo_phone_allowed(phone_e164))

        client_ip = data.client_ip
        client_mac = data.client_mac
        user_agent = request.headers.get("User-Agent")

        login_ip_for_history = client_ip

        binding_context = resolve_binding_context(user_to_login, client_ip, client_mac)
        if current_app.config.get("LOG_BINDING_DEBUG", False) or not client_ip:
            current_app.logger.info(
                "Verify-OTP binding context: "
                "input_ip=%s input_mac=%s resolved_ip=%s ip_source=%s ip_msg=%s "
                "resolved_mac=%s mac_source=%s mac_msg=%s",
                binding_context.get("input_ip"),
                binding_context.get("input_mac"),
                binding_context.get("resolved_ip"),
                binding_context.get("ip_source"),
                binding_context.get("ip_message"),
                binding_context.get("resolved_mac"),
                binding_context.get("mac_source"),
                binding_context.get("mac_message"),
            )

        if (not is_demo_login) and user_to_login.role in [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            otp_auto_authorize = current_app.config.get("OTP_AUTO_AUTHORIZE_DEVICE", True)
            bypass_explicit = bool(otp_auto_authorize) and (not used_bypass_code)

            if not bypass_explicit:
                bypass_explicit = True
                try:
                    require_explicit = settings_service.get_setting("REQUIRE_EXPLICIT_DEVICE_AUTH", "False") == "True"
                    if require_explicit and user_to_login.role in [UserRole.USER, UserRole.KOMANDAN]:
                        has_any_authorized_device = (
                            db.session.scalar(
                                select(UserDevice.id)
                                .where(
                                    UserDevice.user_id == user_to_login.id,
                                    UserDevice.is_authorized.is_(True),
                                )
                                .limit(1)
                            )
                            is not None
                        )
                        bypass_explicit = not has_any_authorized_device
                except Exception:
                    bypass_explicit = True

            ok_binding, msg_binding, resolved_ip = apply_device_binding_for_login(
                user_to_login,
                client_ip,
                user_agent,
                client_mac,
                bypass_explicit_auth=bypass_explicit,
            )
            if not ok_binding:
                if msg_binding in ["Limit perangkat tercapai", "Perangkat belum diotorisasi"]:
                    current_app.logger.warning(
                        "Verify-OTP denied by device binding policy: user_id=%s phone=%s ip=%s mac=%s msg=%s",
                        user_to_login.id,
                        user_to_login.phone_number,
                        client_ip,
                        client_mac,
                        msg_binding,
                    )
                    return jsonify(AuthErrorResponseSchema(error=msg_binding).model_dump()), HTTPStatus.FORBIDDEN
                current_app.logger.warning(f"IP binding di-skip untuk user {user_to_login.id}: {msg_binding}")

            if current_app.config.get("SYNC_ADDRESS_LIST_ON_LOGIN", True):
                try:
                    sync_address_list_for_single_user(user_to_login, client_ip=resolved_ip)
                except Exception as e_sync:
                    current_app.logger.warning(f"Gagal sync address-list saat login: {e_sync}")

            if resolved_ip:
                login_ip_for_history = resolved_ip
            else:
                try:
                    from app.services.device_management_service import _is_client_ip_allowed  # type: ignore

                    if not _is_client_ip_allowed(client_ip):
                        login_ip_for_history = None
                except Exception:
                    pass
        elif is_demo_login:
            current_app.logger.info(
                "Verify-OTP demo payment-only: skip device binding/address-list sync for user_id=%s",
                user_to_login.id,
            )

        user_to_login.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = cast(Any, UserLoginHistory)(
            user_id=user_to_login.id, ip_address=login_ip_for_history, user_agent_string=user_agent
        )
        db.session.add(new_login_entry)

        db.session.commit()

        jwt_payload = {"sub": str(user_to_login.id), "rl": user_to_login.role.value}
        access_token = create_access_token(data=jwt_payload)

        refresh_token = issue_refresh_token_for_user(user_to_login.id, user_agent=user_agent)

        session_token = store_session_token(user_to_login.id)
        session_url = None
        if session_token:
            base_url = (
                current_app.config.get("APP_PUBLIC_BASE_URL")
                or current_app.config.get("FRONTEND_URL")
                or current_app.config.get("APP_LINK_USER")
            )
            if base_url:
                next_path = "/dashboard"
                if data.hotspot_login_context is True:
                    next_path = "/captive/terhubung"
                session_url = f"{base_url.rstrip('/')}/session/consume?token={session_token}&next={next_path}"

        hotspot_username: Optional[str] = None
        hotspot_password: Optional[str] = None
        hotspot_login_required = is_hotspot_login_required(user_to_login)
        allow_hotspot_credentials = bool(data.client_ip or data.client_mac)
        if not allow_hotspot_credentials and data.hotspot_login_context is True:
            allow_hotspot_credentials = True
            current_app.logger.info(
                "Hotspot credentials allowed via captive context without client_ip/client_mac for user=%s",
                user_to_login.id,
            )
        if hotspot_login_required and allow_hotspot_credentials:
            hotspot_username = format_to_local_phone(user_to_login.phone_number)
            hotspot_password = user_to_login.mikrotik_password

        response = jsonify(
            VerifyOtpResponseSchema(
                access_token=access_token,
                hotspot_username=hotspot_username,
                hotspot_password=hotspot_password,
                session_token=session_token,
                session_url=session_url,
                hotspot_login_required=hotspot_login_required,
            ).model_dump()
        )
        set_auth_cookie(response, access_token)
        set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except ValidationError as e:
        return jsonify(
            AuthErrorResponseSchema(error="Invalid input.", details=validation_error_details(e)).model_dump()
        ), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /verify-otp: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR
