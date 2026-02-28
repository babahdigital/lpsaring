from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Any, cast

from flask import current_app, jsonify


def auto_login_impl(
    *,
    payload,
    request,
    db,
    User,
    UserDevice,
    ApprovalStatus,
    UserRole,
    UserLoginHistory,
    AuthErrorResponseSchema,
    VerifyOtpResponseSchema,
    get_client_ip,
    normalize_mac,
    resolve_client_mac,
    get_phone_number_variations,
    get_mikrotik_connection,
    get_hotspot_active_session_by_ip,
    apply_device_binding_for_login,
    sync_address_list_for_single_user,
    create_access_token,
    issue_refresh_token_for_user,
    set_auth_cookie,
    set_refresh_cookie,
    build_status_error,
):
    try:
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

        client_ip = payload_dict.get("client_ip")
        client_mac = payload_dict.get("client_mac")
        if not client_ip:
            client_ip = get_client_ip()
        if not client_ip:
            return jsonify(
                AuthErrorResponseSchema(error="IP klien tidak ditemukan.").model_dump()
            ), HTTPStatus.BAD_REQUEST

        from app.services.device_management_service import _is_client_ip_allowed  # type: ignore

        if not _is_client_ip_allowed(client_ip):
            return jsonify(
                AuthErrorResponseSchema(error="IP klien di luar jaringan hotspot yang diizinkan.").model_dump()
            ), HTTPStatus.FORBIDDEN

        login_ip_for_history = client_ip
        user_agent = request.headers.get("User-Agent")

        ok_mac, router_mac, mac_msg = resolve_client_mac(client_ip)
        if not ok_mac:
            current_app.logger.warning("Auto-login: gagal verifikasi MAC dari router untuk ip=%s: %s", client_ip, mac_msg)
            return jsonify(
                AuthErrorResponseSchema(error="Tidak dapat memverifikasi perangkat dari router.").model_dump()
            ), HTTPStatus.SERVICE_UNAVAILABLE

        resolved_mac = normalize_mac(router_mac) if router_mac else None
        if not resolved_mac:
            return jsonify(
                AuthErrorResponseSchema(error="Perangkat belum terdeteksi di router.").model_dump()
            ), HTTPStatus.UNAUTHORIZED

        if client_mac:
            incoming_mac = normalize_mac(client_mac)
            if incoming_mac and incoming_mac != resolved_mac:
                current_app.logger.warning(
                    "Auto-login rejected due MAC mismatch: ip=%s incoming_mac=%s router_mac=%s",
                    client_ip,
                    incoming_mac,
                    resolved_mac,
                )
                return jsonify(
                    AuthErrorResponseSchema(error="Identitas perangkat tidak valid.").model_dump()
                ), HTTPStatus.FORBIDDEN

        device_query = (
            db.session.query(UserDevice)
            .join(User)
            .filter(
                UserDevice.is_authorized.is_(True),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        )

        device = None
        if resolved_mac:
            device = device_query.filter(UserDevice.mac_address == resolved_mac).first()
        # Security: do not use IP-only identity lookup for auto-login.
        # IP can be reused by DHCP; trusted identity must remain MAC-based.

        user = device.user if (device and getattr(device, "user", None)) else None

        if not user:
            return jsonify(
                AuthErrorResponseSchema(error="Perangkat belum terdaftar atau belum diotorisasi.").model_dump()
            ), HTTPStatus.UNAUTHORIZED
        if getattr(user, "is_blocked", False):
            return build_status_error("blocked", "Akun Anda diblokir oleh Admin."), HTTPStatus.FORBIDDEN

        if user.role in [UserRole.USER, UserRole.KOMANDAN, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            trusted_auto_authorize = bool(resolved_mac)
            ok_binding, msg_binding, resolved_ip = apply_device_binding_for_login(
                user,
                client_ip,
                user_agent,
                resolved_mac,
                bypass_explicit_auth=trusted_auto_authorize,
            )
            if not ok_binding:
                if msg_binding in ["Limit perangkat tercapai", "Perangkat belum diotorisasi"]:
                    return jsonify(AuthErrorResponseSchema(error=msg_binding).model_dump()), HTTPStatus.FORBIDDEN
                current_app.logger.warning(f"Auto-login: IP binding di-skip untuk user {user.id}: {msg_binding}")

            if current_app.config.get("SYNC_ADDRESS_LIST_ON_LOGIN", True):
                try:
                    sync_address_list_for_single_user(user, client_ip=resolved_ip)
                except Exception as e_sync:
                    current_app.logger.warning(f"Auto-login: gagal sync address-list: {e_sync}")

            if resolved_ip:
                login_ip_for_history = resolved_ip
            else:
                try:
                    from app.services.device_management_service import _is_client_ip_allowed  # type: ignore

                    if not _is_client_ip_allowed(client_ip):
                        login_ip_for_history = None
                except Exception:
                    pass

        user.last_login_at = datetime.now(dt_timezone.utc)
        new_login_entry = cast(Any, UserLoginHistory)(
            user_id=user.id, ip_address=login_ip_for_history, user_agent_string=user_agent
        )
        db.session.add(new_login_entry)
        db.session.commit()

        jwt_payload = {"sub": str(user.id), "rl": user.role.value}
        access_token = create_access_token(data=jwt_payload)
        refresh_token = issue_refresh_token_for_user(user.id, user_agent=user_agent)

        hotspot_username = None
        hotspot_password = None
        hotspot_login_required = False

        response = jsonify(
            VerifyOtpResponseSchema(
                access_token=access_token,
                hotspot_username=hotspot_username,
                hotspot_password=hotspot_password,
                hotspot_login_required=hotspot_login_required,
            ).model_dump()
        )
        set_auth_cookie(response, access_token)
        set_refresh_cookie(response, refresh_token)
        return response, HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in /auto-login: {e}", exc_info=True)
        return jsonify(
            AuthErrorResponseSchema(error="An unexpected error occurred.").model_dump()
        ), HTTPStatus.INTERNAL_SERVER_ERROR
