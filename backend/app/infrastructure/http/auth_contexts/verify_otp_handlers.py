from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Any, Optional, cast
from urllib.parse import quote

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
    normalize_mac,
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
    get_mikrotik_connection,
    has_hotspot_ip_binding_for_user,
    resolve_client_mac,
    send_whatsapp_message,
    whatsapp_available,
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
            if payload_dict.get("confirm_device_takeover") is None:
                candidate_takeover = (
                    payload_dict.get("confirmDeviceTakeover")
                    or payload_dict.get("confirm_takeover")
                    or request.args.get("confirm_device_takeover")
                    or request.args.get("confirmDeviceTakeover")
                    or request.args.get("confirm_takeover")
                )
                if candidate_takeover is not None:
                    payload_dict["confirm_device_takeover"] = candidate_takeover

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
            if used_demo_bypass:
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
        is_production_like = str(current_app.config.get("FLASK_ENV", "")).strip().lower() == "production"
        require_trusted_captive_context = bool(
            current_app.config.get("VERIFY_OTP_REQUIRE_TRUSTED_CAPTIVE_CONTEXT_PRODUCTION", True)
        ) and is_production_like
        allow_raw_client_mac_fallback = bool(current_app.config.get("VERIFY_OTP_ALLOW_RAW_CLIENT_MAC_FALLBACK", False))

        if require_trusted_captive_context and data.hotspot_login_context is True and not (client_ip or client_mac):
            current_app.logger.warning(
                "Verify-OTP rejected: hotspot context without identity in production user_agent=%s",
                user_agent,
            )
            return jsonify(
                AuthErrorResponseSchema(error="Konteks hotspot tidak valid. Silakan login dari halaman captive yang resmi.").model_dump()
            ), HTTPStatus.FORBIDDEN

        login_ip_for_history = client_ip
        hotspot_login_required = is_hotspot_login_required(user_to_login)
        hotspot_binding_active: Optional[bool] = None

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

        authoritative_binding_mac: Optional[str] = None
        resolved_ip = str(binding_context.get("resolved_ip") or "").strip() or None
        incoming_mac = normalize_mac(client_mac) if client_mac else None
        if resolved_ip:
            ok_router_mac, router_mac_raw, router_mac_msg = resolve_client_mac(resolved_ip)
            if not ok_router_mac:
                current_app.logger.warning(
                    "Verify-OTP rejected: gagal verifikasi MAC router ip=%s user=%s msg=%s",
                    resolved_ip,
                    user_to_login.id,
                    router_mac_msg,
                )
                return jsonify(
                    AuthErrorResponseSchema(error="Tidak dapat memverifikasi perangkat dari router.").model_dump()
                ), HTTPStatus.SERVICE_UNAVAILABLE

            authoritative_binding_mac = normalize_mac(router_mac_raw) if router_mac_raw else None
            if not authoritative_binding_mac:
                return jsonify(
                    AuthErrorResponseSchema(error="Perangkat belum terdeteksi di router.").model_dump()
                ), HTTPStatus.UNAUTHORIZED

            if incoming_mac and incoming_mac != authoritative_binding_mac:
                current_app.logger.warning(
                    "Verify-OTP rejected due MAC mismatch: ip=%s incoming_mac=%s router_mac=%s user=%s",
                    resolved_ip,
                    incoming_mac,
                    authoritative_binding_mac,
                    user_to_login.id,
                )
                return jsonify(
                    AuthErrorResponseSchema(error="Identitas perangkat tidak valid.").model_dump()
                ), HTTPStatus.FORBIDDEN

            binding_context["resolved_mac"] = authoritative_binding_mac
            binding_context["mac_source"] = "mikrotik"
            binding_context["mac_message"] = "MAC authoritative dari router"
        elif incoming_mac:
            if allow_raw_client_mac_fallback and not require_trusted_captive_context:
                authoritative_binding_mac = incoming_mac
            else:
                current_app.logger.warning(
                    "Verify-OTP rejected: raw client_mac without authoritative router MAC user=%s incoming_mac=%s",
                    user_to_login.id,
                    incoming_mac,
                )
                return jsonify(
                    AuthErrorResponseSchema(error="Identitas perangkat tidak valid.").model_dump()
                ), HTTPStatus.FORBIDDEN

        if hotspot_login_required:
            username_for_hotspot = format_to_local_phone(user_to_login.phone_number)
            binding_mac = str(authoritative_binding_mac or binding_context.get("resolved_mac") or "").strip() or None
            if username_for_hotspot:
                try:
                    with get_mikrotik_connection() as api_connection:
                        if api_connection:
                            ok_binding_check, has_binding, _ = has_hotspot_ip_binding_for_user(
                                api_connection,
                                username=username_for_hotspot,
                                user_id=str(user_to_login.id),
                                mac_address=binding_mac,
                            )
                            if ok_binding_check:
                                hotspot_binding_active = has_binding
                except Exception as check_err:
                    current_app.logger.warning(
                        "Verify-OTP hotspot ip-binding pre-check failed for user=%s: %s",
                        user_to_login.id,
                        check_err,
                    )

        if (not is_demo_login) and user_to_login.role in [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # OTP valid dari user sendiri -> self-authorize default untuk mencegah deadlock
            # "device belum authorize" pada user baru/perangkat baru.
            # Pengecualian: saat OTP bypass code dipakai, tetap konservatif.
            bypass_explicit = not used_bypass_code
            if used_bypass_code:
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

            trusted_takeover_source = (
                binding_context.get("mac_source") == "mikrotik"
                and bool(binding_context.get("resolved_mac"))
            )
            allow_cross_user_transfer = bool(data.confirm_device_takeover) and trusted_takeover_source and (not used_bypass_code)

            if bool(data.confirm_device_takeover) and not trusted_takeover_source:
                current_app.logger.warning(
                    "Verify-OTP takeover ignored: untrusted MAC source user_id=%s input_mac=%s mac_source=%s",
                    user_to_login.id,
                    client_mac,
                    binding_context.get("mac_source"),
                )

            ok_binding, msg_binding, resolved_ip = apply_device_binding_for_login(
                user_to_login,
                client_ip,
                user_agent,
                authoritative_binding_mac,
                bypass_explicit_auth=bypass_explicit,
                allow_cross_user_transfer=allow_cross_user_transfer,
            )
            if not ok_binding:
                if msg_binding in [
                    "Limit perangkat tercapai",
                    "Perangkat belum diotorisasi",
                    "MAC sudah terdaftar pada user lain. Konfirmasi takeover diperlukan.",
                    "MAC sudah dipakai perangkat user lain (aktif)",
                ]:
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
        update_session_url = None
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

                update_next_path = f"/update?phone={quote(user_to_login.phone_number or '', safe='')}"
                update_session_url = (
                    f"{base_url.rstrip('/')}/session/consume?token={session_token}&next={quote(update_next_path, safe='/?=&')}"
                )

        send_update_link_enabled = bool(current_app.config.get("DB_UPDATE_LINK_WHATSAPP_AFTER_OTP_ENABLED", False))
        if (
            send_update_link_enabled
            and bool(current_app.config.get("PUBLIC_DB_UPDATE_FORM_ENABLED", False))
            and whatsapp_available
            and update_session_url
            and user_to_login.phone_number
            and (not is_demo_login)
        ):
            try:
                message = (
                    "Pemutakhiran data diperlukan. "
                    "Silakan buka link berikut untuk update data Anda: "
                    f"{update_session_url}"
                )
                sent = send_whatsapp_message(user_to_login.phone_number, message)
                if not sent:
                    current_app.logger.warning(
                        "Verify-OTP: gagal kirim link update database via WhatsApp untuk user_id=%s",
                        user_to_login.id,
                    )
            except Exception as wa_err:
                current_app.logger.warning(
                    "Verify-OTP: error kirim link update database via WhatsApp untuk user_id=%s err=%s",
                    user_to_login.id,
                    wa_err,
                )

        hotspot_username: Optional[str] = None
        hotspot_password: Optional[str] = None

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
                hotspot_binding_active=hotspot_binding_active,
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
