# backend/app/infrastructure/http/decorators.py
# VERSI DIPERBARUI: Penambahan decorator @super_admin_required

from functools import wraps
import ipaddress
from flask import request, jsonify, current_app, g
from http import HTTPStatus
import uuid
from jose import jwt, JWTError, ExpiredSignatureError

from app.extensions import db
from app.infrastructure.db.models import User
from .schemas.auth_schemas import AuthErrorResponseSchema
from app.utils.csrf_utils import is_trusted_origin
from app.utils.request_utils import get_client_ip
from app.services.refresh_token_service import rotate_refresh_token
from app.services.jwt_token_service import create_access_token


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
        token = None
        token_source = None
        auth_header = request.headers.get("Authorization")
        error_response = AuthErrorResponseSchema(error="Unauthorized")
        if auth_header:
            parts = auth_header.split()
            if parts[0].lower() != "bearer" or len(parts) != 2:
                error_response.error = "Invalid token header format."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
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
                error_response.error = "Invalid origin."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

            if raw_refresh:
                rotated = rotate_refresh_token(raw_refresh, user_agent=request.headers.get("User-Agent"))
                if rotated:
                    try:
                        user_uuid_from_token = uuid.UUID(rotated.user_id)
                    except Exception:
                        return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

                    user_from_token = db.session.get(User, user_uuid_from_token)
                    if not user_from_token:
                        error_response.error = "User associated with token not found."
                        return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

                    if not user_from_token.is_active:
                        error_response.error = "User account is inactive."
                        return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN
                    if not user_from_token.is_approved:
                        error_response.error = "User account is not approved."
                        return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

                    jwt_payload = {"sub": str(user_from_token.id), "rl": user_from_token.role.value}
                    new_access = create_access_token(data=jwt_payload)
                    g.new_access_token = new_access
                    g.new_refresh_token = rotated.new_refresh_token

                    return f(current_user_id=user_uuid_from_token, *args, **kwargs)

            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

        if token_source == "cookie" and not _passes_csrf_guard():
            error_response.error = "Invalid origin."
            return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN
        try:
            payload = jwt.decode(
                token, current_app.config["JWT_SECRET_KEY"], algorithms=[current_app.config["JWT_ALGORITHM"]]
            )
            user_uuid_from_token = uuid.UUID(payload.get("sub"))
            user_from_token = db.session.get(User, user_uuid_from_token)

            if not user_from_token:
                error_response.error = "User associated with token not found."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            if not user_from_token.is_active:
                error_response.error = "User account is inactive."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN
            if not user_from_token.is_approved:
                error_response.error = "User account is not approved."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

        except ExpiredSignatureError:
            # Jika access token expired dan token berasal dari cookie, coba refresh.
            if token_source != "cookie":
                error_response.error = "Token has expired."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            refresh_cookie_name = current_app.config.get("REFRESH_COOKIE_NAME", "refresh_token")
            raw_refresh = request.cookies.get(refresh_cookie_name)
            if not raw_refresh:
                error_response.error = "Token has expired."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            if not _passes_csrf_guard():
                error_response.error = "Invalid origin."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

            rotated = rotate_refresh_token(raw_refresh, user_agent=request.headers.get("User-Agent"))
            if not rotated:
                error_response.error = "Token has expired."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            try:
                user_uuid_from_token = uuid.UUID(rotated.user_id)
            except Exception:
                error_response.error = "Token has expired."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            user_from_token = db.session.get(User, user_uuid_from_token)
            if not user_from_token:
                error_response.error = "User associated with token not found."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

            if not user_from_token.is_active:
                error_response.error = "User account is inactive."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN
            if not user_from_token.is_approved:
                error_response.error = "User account is not approved."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

            jwt_payload = {"sub": str(user_from_token.id), "rl": user_from_token.role.value}
            new_access = create_access_token(data=jwt_payload)
            g.new_access_token = new_access
            g.new_refresh_token = rotated.new_refresh_token

            return f(current_user_id=user_uuid_from_token, *args, **kwargs)
        except (JWTError, ValueError, TypeError) as e:
            error_response.error = f"Invalid token: {str(e)}"
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

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
            return jsonify(
                AuthErrorResponseSchema(error="Akses ditolak. Memerlukan hak akses Admin.").model_dump()
            ), HTTPStatus.FORBIDDEN

        return f(current_admin=admin_user, *args, **kwargs)

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
            return jsonify(
                AuthErrorResponseSchema(error="Akses ditolak. Memerlukan hak akses Super Admin.").model_dump()
            ), HTTPStatus.FORBIDDEN

        return f(current_admin=super_admin_user, *args, **kwargs)

    return decorated_function
