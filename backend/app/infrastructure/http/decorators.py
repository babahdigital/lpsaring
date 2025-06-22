# backend/app/infrastructure/http/decorators.py
# VERSI DIPERBARUI: Penambahan decorator @super_admin_required

from functools import wraps
from flask import request, jsonify, current_app
from http import HTTPStatus
import uuid
from jose import jwt, JWTError, ExpiredSignatureError

from app.extensions import db
from app.infrastructure.db.models import User
from .schemas.auth_schemas import AuthErrorResponseSchema

def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        error_response = AuthErrorResponseSchema(error="Unauthorized")
        if not auth_header:
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) != 2:
            error_response.error = "Invalid token header format."
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

        token = parts[1]
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
            user_uuid_from_token = uuid.UUID(payload.get('sub'))
            user_from_token = db.session.get(User, user_uuid_from_token)
            
            if not user_from_token:
                error_response.error = "User associated with token not found."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
            
            if not user_from_token.is_active:
                error_response.error = "User account is inactive."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

        except ExpiredSignatureError:
            error_response.error = "Token has expired."
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
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
            return jsonify(AuthErrorResponseSchema(error="Akses ditolak. Memerlukan hak akses Admin.").model_dump()), HTTPStatus.FORBIDDEN
        
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
            return jsonify(AuthErrorResponseSchema(error="Akses ditolak. Memerlukan hak akses Super Admin.").model_dump()), HTTPStatus.FORBIDDEN
        
        return f(current_admin=super_admin_user, *args, **kwargs)
    return decorated_function