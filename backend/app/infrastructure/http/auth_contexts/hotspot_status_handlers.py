from __future__ import annotations

from http import HTTPStatus

from flask import jsonify


def get_hotspot_session_status_impl(
    *,
    current_user_id,
    db,
    User,
    AuthErrorResponseSchema,
    format_to_local_phone,
    is_hotspot_login_required,
    get_mikrotik_connection,
    has_hotspot_ip_binding_for_user,
):
    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify(AuthErrorResponseSchema(error="User not found.").model_dump()), HTTPStatus.NOT_FOUND

    hotspot_login_required = bool(is_hotspot_login_required(user))
    hotspot_session_active = None

    if hotspot_login_required:
        username_for_hotspot = format_to_local_phone(getattr(user, "phone_number", None) or "")
        if username_for_hotspot:
            try:
                with get_mikrotik_connection() as api_connection:
                    if api_connection:
                        ok_binding_check, has_binding, _ = has_hotspot_ip_binding_for_user(
                            api_connection,
                            username=username_for_hotspot,
                            user_id=str(user.id),
                            mac_address=None,
                        )
                        if ok_binding_check:
                            hotspot_session_active = bool(has_binding)
            except Exception:
                hotspot_session_active = None

    return (
        jsonify(
            {
                "hotspot_login_required": hotspot_login_required,
                "hotspot_session_active": hotspot_session_active,
            }
        ),
        HTTPStatus.OK,
    )
