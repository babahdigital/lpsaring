# backend/app/infrastructure/http/decorators.py
# VERSI DIPERBARUI: Penambahan decorator @super_admin_required

from functools import wraps
import ipaddress
from flask import request, current_app, g, make_response
from http import HTTPStatus
import uuid
import json
import os
import sqlalchemy as sa
from jose import jwt, JWTError, ExpiredSignatureError

from app.extensions import db
from app.infrastructure.db.models import User, AdminActionType
from app.infrastructure.http.error_envelope import error_response
from app.utils.csrf_utils import is_trusted_origin
from app.utils.request_utils import get_client_ip
from app.services.refresh_token_service import rotate_refresh_token
from app.services.jwt_token_service import create_access_token
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations, normalize_to_e164


def _auth_error(message: str, status: HTTPStatus, code: str):
    return error_response(message, status_code=status, code=code)


def _is_demo_user_by_phone(phone_number: str | None) -> bool:
    demo_mode_enabled = settings_service.get_setting_as_bool(
        "DEMO_MODE_ENABLED",
        bool(current_app.config.get("DEMO_MODE_ENABLED", False)),
    )
    if not demo_mode_enabled:
        return False

    raw_phone = str(phone_number or "").strip()
    if raw_phone == "":
        return False

    allowed_raw = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(allowed_raw, list) or len(allowed_raw) == 0:
        return False

    try:
        normalized_user = normalize_to_e164(raw_phone)
    except Exception:
        return False

    user_variants = set(get_phone_number_variations(normalized_user))
    for candidate in allowed_raw:
        candidate_raw = str(candidate or "").strip()
        if candidate_raw == "":
            continue
        try:
            normalized_candidate = normalize_to_e164(candidate_raw)
        except Exception:
            continue

        candidate_variants = set(get_phone_number_variations(normalized_candidate))
        if user_variants.intersection(candidate_variants):
            return True

    return False


def _is_demo_path_allowed(path: str) -> bool:
    allowed_prefixes = (
        "/api/transactions",
        "/api/packages",
        "/api/auth/me",
        "/api/auth/logout",
    )
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in allowed_prefixes)


def _get_trusted_origins() -> list[str]:
    configured = current_app.config.get("CSRF_TRUSTED_ORIGINS")
    if isinstance(configured, (list, tuple)) and configured:
        return [str(item) for item in configured if item]

    fallback = [
        current_app.config.get("FRONTEND_URL"),
        current_app.config.get("APP_PUBLIC_BASE_URL"),
        current_app.config.get("APP_LINK_USER"),
    ]
    extra = current_app.config.get("CORS_ADDITIONAL_ORIGINS", [])
    if isinstance(extra, (list, tuple)):
        fallback.extend(extra)
    return [item for item in fallback if item]


def _get_no_origin_allowed_ips() -> set[str]:
    configured = current_app.config.get("CSRF_NO_ORIGIN_ALLOWED_IPS")
    if isinstance(configured, (list, tuple)):
        return {str(item).strip() for item in configured if str(item).strip()}
    if isinstance(configured, str) and configured.strip():
        return {item.strip() for item in configured.split(",") if item.strip()}
    return set()


def _is_no_origin_ip_allowed(client_ip: str, allowed_entries: set[str]) -> bool:
    if not client_ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for entry in allowed_entries:
        if "/" in entry:
            try:
                if ip_obj in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        else:
            if client_ip == entry:
                return True
    return False


def _passes_csrf_guard() -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    if not current_app.config.get("CSRF_PROTECT_ENABLED", True):
        return True

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    trusted = _get_trusted_origins()
    if origin and is_trusted_origin(origin, trusted):
        return True
    if referer and is_trusted_origin(referer, trusted):
        return True

    if not origin and not referer:
        if not current_app.config.get("CSRF_STRICT_NO_ORIGIN", False):
            return True
        client_ip = get_client_ip()
        allowed_ips = _get_no_origin_allowed_ips()
        if client_ip and _is_no_origin_ip_allowed(client_ip, allowed_ips):
            return True
        current_app.logger.warning(
            "CSRF guard blocked no-origin request: ip=%s method=%s path=%s",
            client_ip or "unknown",
            request.method,
            request.path,
        )
        return False
    return False


def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_logout_path = request.path == "/api/auth/logout"
        token = None
        token_source = None
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if parts[0].lower() != "bearer" or len(parts) != 2:
                return _auth_error("Invalid token header format.", HTTPStatus.UNAUTHORIZED, "AUTH_HEADER_INVALID")
            token = parts[1]
            token_source = "header"

        if not token:
            cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "auth_token")
            cookie_token = request.cookies.get(cookie_name)
            if cookie_token:
                token = cookie_token
                token_source = "cookie"

        if not token:
            # Jika access token tidak ada, coba fallback ke refresh token (cookie) untuk UX persisten.
            refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
            raw_refresh = request.cookies.get(refresh_cookie_name)
            if raw_refresh and not _passes_csrf_guard():
                return _auth_error("Invalid origin.", HTTPStatus.FORBIDDEN, "AUTH_ORIGIN_INVALID")

            if raw_refresh:
                rotated = rotate_refresh_token(raw_refresh, user_agent=request.headers.get("User-Agent"))
                if rotated:
                    try:
                        user_uuid_from_token = uuid.UUID(rotated.user_id)
                    except Exception:
                        return _auth_error("Unauthorized", HTTPStatus.UNAUTHORIZED, "AUTH_UNAUTHORIZED")

                    user_from_token = db.session.get(User, user_uuid_from_token)
                    if not user_from_token:
                        return _auth_error(
                            "User associated with token not found.",
                            HTTPStatus.UNAUTHORIZED,
                            "AUTH_USER_NOT_FOUND",
                        )

                    if not user_from_token.is_active:
                        return _auth_error("User account is inactive.", HTTPStatus.FORBIDDEN, "AUTH_USER_INACTIVE")
                    if not user_from_token.is_approved:
                        return _auth_error("User account is not approved.", HTTPStatus.FORBIDDEN, "AUTH_USER_UNAPPROVED")

                    if _is_demo_user_by_phone(getattr(user_from_token, "phone_number", None)) and not _is_demo_path_allowed(
                        request.path
                    ):
                        return _auth_error(
                            "Akun demo hanya diizinkan mengakses alur pembayaran.",
                            HTTPStatus.FORBIDDEN,
                            "AUTH_DEMO_SCOPE_RESTRICTED",
                        )

                    if not is_logout_path:
                        jwt_payload = {"sub": str(user_from_token.id), "rl": user_from_token.role.value}
                        new_access = create_access_token(data=jwt_payload)
                        g.new_access_token = new_access
                        g.new_refresh_token = rotated.new_refresh_token

                    return f(current_user_id=user_uuid_from_token, *args, **kwargs)

            return _auth_error("Unauthorized", HTTPStatus.UNAUTHORIZED, "AUTH_UNAUTHORIZED")

        if token_source == "cookie" and not _passes_csrf_guard():
            return _auth_error("Invalid origin.", HTTPStatus.FORBIDDEN, "AUTH_ORIGIN_INVALID")
        try:
            payload = jwt.decode(
                token, current_app.config["JWT_SECRET_KEY"], algorithms=[current_app.config["JWT_ALGORITHM"]]
            )
            user_uuid_from_token = uuid.UUID(payload.get("sub"))
            user_from_token = db.session.get(User, user_uuid_from_token)

            if not user_from_token:
                return _auth_error("User associated with token not found.", HTTPStatus.UNAUTHORIZED, "AUTH_USER_NOT_FOUND")

            if not user_from_token.is_active:
                return _auth_error("User account is inactive.", HTTPStatus.FORBIDDEN, "AUTH_USER_INACTIVE")
            if not user_from_token.is_approved:
                return _auth_error("User account is not approved.", HTTPStatus.FORBIDDEN, "AUTH_USER_UNAPPROVED")

            if _is_demo_user_by_phone(getattr(user_from_token, "phone_number", None)) and not _is_demo_path_allowed(
                request.path
            ):
                return _auth_error(
                    "Akun demo hanya diizinkan mengakses alur pembayaran.",
                    HTTPStatus.FORBIDDEN,
                    "AUTH_DEMO_SCOPE_RESTRICTED",
                )

        except ExpiredSignatureError:
            # Jika access token expired dan token berasal dari cookie, coba refresh.
            if token_source != "cookie":
                return _auth_error("Token has expired.", HTTPStatus.UNAUTHORIZED, "AUTH_TOKEN_EXPIRED")

            refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
            raw_refresh = request.cookies.get(refresh_cookie_name)
            if not raw_refresh:
                return _auth_error("Token has expired.", HTTPStatus.UNAUTHORIZED, "AUTH_TOKEN_EXPIRED")

            if not _passes_csrf_guard():
                return _auth_error("Invalid origin.", HTTPStatus.FORBIDDEN, "AUTH_ORIGIN_INVALID")

            rotated = rotate_refresh_token(raw_refresh, user_agent=request.headers.get("User-Agent"))
            if not rotated:
                return _auth_error("Token has expired.", HTTPStatus.UNAUTHORIZED, "AUTH_TOKEN_EXPIRED")

            try:
                user_uuid_from_token = uuid.UUID(rotated.user_id)
            except Exception:
                return _auth_error("Token has expired.", HTTPStatus.UNAUTHORIZED, "AUTH_TOKEN_EXPIRED")

            user_from_token = db.session.get(User, user_uuid_from_token)
            if not user_from_token:
                return _auth_error("User associated with token not found.", HTTPStatus.UNAUTHORIZED, "AUTH_USER_NOT_FOUND")

            if not user_from_token.is_active:
                return _auth_error("User account is inactive.", HTTPStatus.FORBIDDEN, "AUTH_USER_INACTIVE")
            if not user_from_token.is_approved:
                return _auth_error("User account is not approved.", HTTPStatus.FORBIDDEN, "AUTH_USER_UNAPPROVED")

            if _is_demo_user_by_phone(getattr(user_from_token, "phone_number", None)) and not _is_demo_path_allowed(
                request.path
            ):
                return _auth_error(
                    "Akun demo hanya diizinkan mengakses alur pembayaran.",
                    HTTPStatus.FORBIDDEN,
                    "AUTH_DEMO_SCOPE_RESTRICTED",
                )

            if not is_logout_path:
                jwt_payload = {"sub": str(user_from_token.id), "rl": user_from_token.role.value}
                new_access = create_access_token(data=jwt_payload)
                g.new_access_token = new_access
                g.new_refresh_token = rotated.new_refresh_token

            return f(current_user_id=user_uuid_from_token, *args, **kwargs)
        except (JWTError, ValueError, TypeError) as e:
            return _auth_error(f"Invalid token: {str(e)}", HTTPStatus.UNAUTHORIZED, "AUTH_TOKEN_INVALID")

        return f(current_user_id=user_uuid_from_token, *args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated_function(current_user_id, *args, **kwargs):
        admin_user = db.session.get(User, current_user_id)

        if not admin_user or not admin_user.is_admin_role:
            current_app.logger.warning(
                f"Akses DITOLAK ke rute admin. User ID: {current_user_id}, "
                f"Role: {admin_user.role.value if admin_user and admin_user.role else 'Tidak Ditemukan'}"
            )
            return _auth_error("Akses ditolak. Memerlukan hak akses Admin.", HTTPStatus.FORBIDDEN, "AUTH_ADMIN_REQUIRED")

        resp = f(current_admin=admin_user, *args, **kwargs)

        try:
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and not getattr(g, "admin_action_logged", False):
                disable_super_admin_logs = str(
                    os.getenv("DISABLE_SUPER_ADMIN_ACTION_LOGS", "false") or ""
                ).strip().lower() in {"1", "true", "yes", "y", "on"}
                if not (disable_super_admin_logs and getattr(admin_user, "is_super_admin_role", False)):
                    response_obj = make_response(resp)

                    def _sanitize(value: object, *, depth: int = 0) -> object:
                        if depth > 4:
                            return "(truncated)"
                        if value is None:
                            return None
                        if isinstance(value, (int, float, bool)):
                            return value
                        if isinstance(value, str):
                            return value if len(value) <= 500 else (value[:500] + "…")
                        if isinstance(value, (list, tuple)):
                            items = list(value)[:50]
                            return [_sanitize(v, depth=depth + 1) for v in items]
                        if isinstance(value, dict):
                            blocked = {
                                "password",
                                "new_password",
                                "otp",
                                "token",
                                "access_token",
                                "refresh_token",
                                "authorization",
                                "server_key",
                                "client_key",
                                "signature",
                                "signature_key",
                            }
                            sanitized: dict[str, object] = {}
                            for k, v in list(value.items())[:100]:
                                key = str(k)
                                if key.lower() in blocked:
                                    sanitized[key] = "(redacted)"
                                else:
                                    sanitized[key] = _sanitize(v, depth=depth + 1)
                            return sanitized
                        try:
                            return str(value)
                        except Exception:
                            return "(unserializable)"

                    payload: object | None = None
                    try:
                        payload = request.get_json(silent=True)
                    except Exception:
                        payload = None

                    details_json = json.dumps(
                        {
                            "method": request.method,
                            "path": request.path,
                            "query": _sanitize(dict(request.args)),
                            "json": _sanitize(payload),
                            "status_code": int(getattr(response_obj, "status_code", 0) or 0),
                        },
                        ensure_ascii=False,
                        default=str,
                    )

                    stmt = sa.text(
                        """
                        INSERT INTO admin_action_logs (id, admin_id, target_user_id, action_type, details)
                        VALUES (:id, :admin_id, :target_user_id, :action_type, :details)
                        """
                    )
                    with db.engine.begin() as conn:
                        conn.execute(
                            stmt,
                            {
                                "id": str(uuid.uuid4()),
                                "admin_id": str(admin_user.id),
                                "target_user_id": None,
                                "action_type": AdminActionType.ADMIN_API_MUTATION.value,
                                "details": details_json,
                            },
                        )
        except Exception as e:
            current_app.logger.error(f"Gagal mencatat ADMIN_API_MUTATION: {e}", exc_info=True)

        return resp

    return decorated_function


# --- PENAMBAHAN BARU ---
def super_admin_required(f):
    @wraps(f)
    @token_required
    def decorated_function(current_user_id, *args, **kwargs):
        super_admin_user = db.session.get(User, current_user_id)

        # Periksa apakah pengguna adalah SUPER_ADMIN
        if not super_admin_user or not super_admin_user.is_super_admin_role:
            current_app.logger.warning(
                f"Akses DITOLAK ke rute Super Admin. User ID: {current_user_id}, "
                f"Role: {super_admin_user.role.value if super_admin_user and super_admin_user.role else 'Tidak Ditemukan'}"
            )
            # Pesan error sesuai dengan rencana pengembangan
            return _auth_error(
                "Akses ditolak. Memerlukan hak akses Super Admin.",
                HTTPStatus.FORBIDDEN,
                "AUTH_SUPER_ADMIN_REQUIRED",
            )

        resp = f(current_admin=super_admin_user, *args, **kwargs)

        try:
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and not getattr(g, "admin_action_logged", False):
                disable_super_admin_logs = str(
                    os.getenv("DISABLE_SUPER_ADMIN_ACTION_LOGS", "false") or ""
                ).strip().lower() in {"1", "true", "yes", "y", "on"}
                if not (disable_super_admin_logs and getattr(super_admin_user, "is_super_admin_role", False)):
                    response_obj = make_response(resp)

                    def _sanitize(value: object, *, depth: int = 0) -> object:
                        if depth > 4:
                            return "(truncated)"
                        if value is None:
                            return None
                        if isinstance(value, (int, float, bool)):
                            return value
                        if isinstance(value, str):
                            return value if len(value) <= 500 else (value[:500] + "…")
                        if isinstance(value, (list, tuple)):
                            items = list(value)[:50]
                            return [_sanitize(v, depth=depth + 1) for v in items]
                        if isinstance(value, dict):
                            blocked = {
                                "password",
                                "new_password",
                                "otp",
                                "token",
                                "access_token",
                                "refresh_token",
                                "authorization",
                                "server_key",
                                "client_key",
                                "signature",
                                "signature_key",
                            }
                            sanitized: dict[str, object] = {}
                            for k, v in list(value.items())[:100]:
                                key = str(k)
                                if key.lower() in blocked:
                                    sanitized[key] = "(redacted)"
                                else:
                                    sanitized[key] = _sanitize(v, depth=depth + 1)
                            return sanitized
                        try:
                            return str(value)
                        except Exception:
                            return "(unserializable)"

                    payload: object | None = None
                    try:
                        payload = request.get_json(silent=True)
                    except Exception:
                        payload = None

                    details_json = json.dumps(
                        {
                            "method": request.method,
                            "path": request.path,
                            "query": _sanitize(dict(request.args)),
                            "json": _sanitize(payload),
                            "status_code": int(getattr(response_obj, "status_code", 0) or 0),
                        },
                        ensure_ascii=False,
                        default=str,
                    )

                    stmt = sa.text(
                        """
                        INSERT INTO admin_action_logs (id, admin_id, target_user_id, action_type, details)
                        VALUES (:id, :admin_id, :target_user_id, :action_type, :details)
                        """
                    )
                    with db.engine.begin() as conn:
                        conn.execute(
                            stmt,
                            {
                                "id": str(uuid.uuid4()),
                                "admin_id": str(super_admin_user.id),
                                "target_user_id": None,
                                "action_type": AdminActionType.ADMIN_API_MUTATION.value,
                                "details": details_json,
                            },
                        )
        except Exception as e:
            current_app.logger.error(f"Gagal mencatat ADMIN_API_MUTATION: {e}", exc_info=True)

        return resp

    return decorated_function
