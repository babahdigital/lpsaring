# backend/app/infrastructure/http/auth/session_routes.py

import logging
from http import HTTPStatus
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import select
from werkzeug.security import check_password_hash

from app.extensions import db, limiter
from app.infrastructure.db.models import User, UserLoginHistory, UserRole
from app.services.client_detection_service import ClientDetectionService
from app.services.auth_session_service import AuthSessionService
from app.utils.formatters import normalize_to_e164, format_to_local_phone
from app.utils.request_utils import get_client_ip
from app.infrastructure.gateways.mikrotik_client import (
    disable_ip_binding_by_comment,
    remove_ip_from_address_list,
    find_and_remove_static_lease_by_mac
)
from flask_jwt_extended import (
    create_access_token, create_refresh_token, get_current_user,
    get_jwt, get_jwt_identity, jwt_required, set_refresh_cookies,
    unset_jwt_cookies
)

logger = logging.getLogger(__name__)

session_bp = Blueprint('session', __name__, url_prefix='/auth')

@session_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """Endpoint khusus untuk login admin."""
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON"}), HTTPStatus.BAD_REQUEST

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), HTTPStatus.BAD_REQUEST

    try:
        phone = normalize_to_e164(username)
    except ValueError as e:
        return jsonify({"error": str(e)}), HTTPStatus.BAD_REQUEST

    user = db.session.scalar(
        select(User).filter(
            User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]),
            User.phone_number == phone
        )
    )

    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Username atau password salah"}), HTTPStatus.UNAUTHORIZED

    if not user.is_active or user.is_blocked:
        return jsonify({"message": "Akun admin tidak aktif atau diblokir"}), HTTPStatus.FORBIDDEN

    user.last_login_at = datetime.now(timezone.utc)
    
    # Buat entry history login
    history = UserLoginHistory()
    history.user_id = user.id
    history.ip_address = get_client_ip()
    history.user_agent_string = request.headers.get('User-Agent')
    db.session.add(history)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    resp = jsonify({
        "token": access_token, 
        "access_token": access_token,
        "user": {
            "id": str(user.id),
            "full_name": user.full_name,
            "role": user.role.value
        }
    })
    set_refresh_cookies(resp, refresh_token)
    return resp, HTTPStatus.OK

@session_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
@limiter.limit("5 per minute; 30 per hour")
def refresh_access_token():
    """Refresh JWT access token."""
    identity = get_jwt_identity()
    new_access_token = create_access_token(identity=identity)
    return jsonify(access_token=new_access_token, token=new_access_token), 200

@session_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user_info():
    """Mendapatkan informasi user yang sedang login."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User not found"}), 404
    
    return jsonify({
        "status": "SUCCESS",
        "user": {
            "id": str(current_user.id),
            "phone_number": current_user.phone_number,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
            "approval_status": current_user.approval_status.value,
            "is_active": current_user.is_active,
            "is_blocked": current_user.is_blocked,
            "blok": current_user.blok,
            "kamar": current_user.kamar,
            "total_quota_purchased_mb": current_user.total_quota_purchased_mb,
            "total_quota_used_mb": current_user.total_quota_used_mb,
            "is_unlimited_user": current_user.is_unlimited_user,
            "quota_expiry_date": current_user.quota_expiry_date.isoformat() if current_user.quota_expiry_date else None,
            "device_brand": current_user.device_brand,
            "device_model": current_user.device_model,
            "client_ip": current_user.last_login_ip,
            "client_mac": current_user.last_login_mac,
            "blocking_reason": current_user.blocking_reason,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None,
            "approved_at": current_user.approved_at.isoformat() if current_user.approved_at else None,
            "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
        }
    }), 200

@session_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout_user():
    """Logout user dan bersihkan sesi di MikroTik."""
    current_user = get_current_user()
    detection_result = ClientDetectionService.get_client_info()
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')

    if current_user:
        mikrotik_username = format_to_local_phone(current_user.phone_number)
        if mikrotik_username:
            disable_ip_binding_by_comment(mikrotik_username)
        
        if client_ip:
            list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
            if list_name:
                remove_ip_from_address_list(list_name, client_ip)
            AuthSessionService.destroy_session(client_ip)
            ClientDetectionService.clear_cache(client_ip)

        if client_mac:
            find_and_remove_static_lease_by_mac(client_mac)
            
    resp = jsonify({"status": "SUCCESS", "message": "Logout berhasil"})
    unset_jwt_cookies(resp)
    return resp, 200

@session_bp.route('/verify-role', methods=['GET'])
@jwt_required()
def verify_user_role():
    """Memverifikasi role dari user saat ini."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User not found"}), 404
    
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    return jsonify({"status": "SUCCESS", "isAdmin": is_admin, "role": current_user.role.value}), 200
