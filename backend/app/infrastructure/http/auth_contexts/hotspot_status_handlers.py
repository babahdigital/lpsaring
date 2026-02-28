from __future__ import annotations

from http import HTTPStatus

from flask import current_app, jsonify


def get_hotspot_session_status_impl(
    *,
    current_user_id,
    db,
    User,
    AuthErrorResponseSchema,
    query_args,
    format_to_local_phone,
    normalize_mac,
    resolve_client_mac,
    is_hotspot_login_required,
    get_mikrotik_connection,
    has_hotspot_ip_binding_for_user,
    get_hotspot_user_ip,
):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND

    hotspot_login_required = bool(is_hotspot_login_required(user))
    hotspot_binding_active = None
    hotspot_hint_applied = False
    binding_lookup_mode = "none"
    fallback_attempted = False
    fallback_applied = False

    def _first_non_empty(*keys):
        for key in keys:
            value = query_args.get(key) if query_args is not None else None
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    if hotspot_login_required:
        username_for_hotspot = format_to_local_phone(getattr(user, "phone_number", None) or "")
        if username_for_hotspot:
            client_ip_hint = _first_non_empty("client_ip", "ip", "client-ip")
            client_mac_hint = _first_non_empty("client_mac", "mac", "mac-address", "client-mac")
            incoming_mac = normalize_mac(client_mac_hint) if client_mac_hint else None
            binding_mac = incoming_mac
            allow_user_level_fallback = True
            try:
                allow_user_level_fallback = (
                    str(current_app.config.get("HOTSPOT_SESSION_STATUS_ALLOW_USER_LEVEL_FALLBACK", "False")).strip().lower()
                    in {"1", "true", "yes", "on"}
                )
            except Exception:
                allow_user_level_fallback = False

            if client_ip_hint:
                ok_router_mac, router_mac_raw, _router_msg = resolve_client_mac(client_ip_hint)
                if ok_router_mac and router_mac_raw:
                    router_mac = normalize_mac(router_mac_raw)
                    if router_mac:
                        hotspot_hint_applied = True
                        binding_mac = router_mac
                        binding_lookup_mode = "router-mac"
                        if incoming_mac and incoming_mac != router_mac:
                            hotspot_binding_active = False
                            current_app.logger.info(
                                "hotspot_session_status_decision user_id=%s username=%s input_ip=%s input_mac=%s resolved_mac=%s binding_active=%s lookup_mode=%s fallback_attempted=%s fallback_applied=%s reason=mac_hint_mismatch",
                                user.id,
                                username_for_hotspot,
                                client_ip_hint,
                                incoming_mac,
                                router_mac,
                                hotspot_binding_active,
                                binding_lookup_mode,
                                fallback_attempted,
                                fallback_applied,
                            )
                            return (
                                jsonify(
                                    {
                                        "hotspot_login_required": hotspot_login_required,
                                        "hotspot_binding_active": hotspot_binding_active,
                                        "hotspot_hint_applied": hotspot_hint_applied,
                                    }
                                ),
                                HTTPStatus.OK,
                            )
            if binding_lookup_mode == "none":
                binding_lookup_mode = "hint-or-user"

            try:
                with get_mikrotik_connection() as api_connection:
                    if api_connection:
                        ok_binding_check, has_binding, _ = has_hotspot_ip_binding_for_user(
                            api_connection,
                            username=username_for_hotspot,
                            user_id=str(user.id),
                            mac_address=binding_mac,
                        )
                        if ok_binding_check:
                            hotspot_binding_active = bool(has_binding)

                        if allow_user_level_fallback and hotspot_binding_active is not True:
                            should_try_user_level_fallback = False
                            if client_ip_hint:
                                ok_user_ip, hotspot_user_ip, _ = get_hotspot_user_ip(api_connection, username_for_hotspot)
                                if ok_user_ip and hotspot_user_ip and str(hotspot_user_ip).strip() == str(client_ip_hint).strip():
                                    should_try_user_level_fallback = True

                            if should_try_user_level_fallback:
                                fallback_attempted = True
                                ok_fallback, has_fallback_binding, _ = has_hotspot_ip_binding_for_user(
                                    api_connection,
                                    username=username_for_hotspot,
                                    user_id=str(user.id),
                                    mac_address=None,
                                )
                                if ok_fallback:
                                    hotspot_binding_active = bool(has_fallback_binding)
                                    fallback_applied = True
                                    binding_lookup_mode = "user-fallback"
            except Exception:
                hotspot_binding_active = None

    current_app.logger.info(
        "hotspot_session_status_decision user_id=%s username=%s input_ip=%s input_mac=%s binding_active=%s login_required=%s hint_applied=%s lookup_mode=%s fallback_attempted=%s fallback_applied=%s",
        user.id,
        format_to_local_phone(getattr(user, "phone_number", None) or ""),
        _first_non_empty("client_ip", "ip", "client-ip"),
        normalize_mac(_first_non_empty("client_mac", "mac", "mac-address", "client-mac") or ""),
        hotspot_binding_active,
        hotspot_login_required,
        hotspot_hint_applied,
        binding_lookup_mode,
        fallback_attempted,
        fallback_applied,
    )

    return (
        jsonify(
            {
                "hotspot_login_required": hotspot_login_required,
                "hotspot_binding_active": hotspot_binding_active,
                "hotspot_hint_applied": hotspot_hint_applied,
            }
        ),
        HTTPStatus.OK,
    )
