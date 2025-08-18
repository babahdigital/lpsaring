# backend/app/infrastructure/http/auth_routes.py
"""
Optimized Auth Routes with Service Integration
Complete replacement for old auth_routes.py with fixed imports
"""
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

import time
import logging
import json
import random
from typing import Optional, Dict, Any
from flask import Blueprint, request, jsonify, current_app
from urllib.parse import unquote
from sqlalchemy import select

# Import Services
from app.services.client_detection_service import ClientDetectionService
from app.services.auth_session_service import AuthSessionService

# Import existing utilities with correct paths
from app.utils.request_utils import get_client_ip, get_client_mac, is_captive_browser_request
# Import fungsi spesifik yang dibutuhkan
from app.infrastructure.gateways import mikrotik_client
# Import langsung semua fungsi yang dibutuhkan untuk Pylance
from app.infrastructure.gateways.mikrotik_client import (
    disable_ip_binding_by_comment,
    create_or_update_ip_binding,
    find_mac_by_ip_comprehensive,
    get_active_session_by_ip,
    find_and_update_address_list_entry,
    find_and_remove_static_lease_by_mac,
    create_static_lease,
    purge_user_from_hotspot,
    purge_user_from_hotspot_by_comment
)
# Removed unused import: from app.utils.mikrotik_helpers import find_dhcp_server_for_ip
from app.infrastructure.db.models import User, UserDevice, UserRole, ApprovalStatus, UserBlok, UserKamar
from app.extensions import db, limiter
from app.infrastructure.gateways.whatsapp_client import send_otp_whatsapp
from app.utils.formatters import format_to_local_phone, normalize_to_e164
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_current_user,
    get_jwt_identity,
    set_refresh_cookies,
    unset_jwt_cookies,
    get_jwt,
)
from app.utils.cache_manager import cache_manager
from app.infrastructure.http.schemas.auth_schemas import UserRegisterRequestSchema, AuthErrorResponseSchema
from http import HTTPStatus
from datetime import datetime, timedelta, timezone
from app.tasks.auth_optimization_tasks import schedule_token_cleanup

logger = logging.getLogger(__name__)

# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/register', methods=['POST'])
def register_user():
    """
    Register a new user in the system
    
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/UserRegisterRequest'
    responses:
      200:
        description: User registration successful
      400:
        description: Invalid input
      409:
        description: Phone number already registered
      500:
        description: Server error
    """
    if not request.is_json: 
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        normalized_phone_number = data_input.phone_number
        if db.session.execute(select(User.id).filter_by(phone_number=normalized_phone_number)).scalar_one_or_none(): 
            return jsonify(AuthErrorResponseSchema(error="Nomor telepon sudah terdaftar.").model_dump()), HTTPStatus.CONFLICT
        
        # Parse user agent for device info
        from user_agents import parse as parse_user_agent
        ua_string = request.headers.get('User-Agent')
        device_brand, device_model, raw_ua = None, None, None
        if ua_string: 
            raw_ua, ua_info = ua_string[:1024], parse_user_agent(ua_string)
            device_brand, device_model = getattr(ua_info.device, 'brand', None), getattr(ua_info.device, 'model', None)
        
        # Create new user object
        new_user_obj = User()
        new_user_obj.phone_number = normalized_phone_number
        new_user_obj.full_name = data_input.full_name
        new_user_obj.approval_status = ApprovalStatus.PENDING_APPROVAL
        new_user_obj.is_active = False
        new_user_obj.device_brand = device_brand
        new_user_obj.device_model = device_model
        new_user_obj.raw_user_agent = raw_ua
        new_user_obj.is_unlimited_user = False

        # Determine role based on registration type
        if data_input.register_as_komandan: 
            new_user_obj.role = UserRole.KOMANDAN
        else: 
            new_user_obj.role = UserRole.USER
        
        # Use the centralized helper for server name determination - this handles test mode properly
        from app.utils.mikrotik_helpers import get_server_for_user
        new_user_obj.mikrotik_server_name = get_server_for_user(new_user_obj)
        
        # Use string values for blok and kamar
        if data_input.blok:
            # Set as string directly without using enum
            setattr(new_user_obj, 'blok', data_input.blok)
        
        if data_input.kamar:
            # Set as string directly without using enum
            setattr(new_user_obj, 'kamar', f"Kamar_{data_input.kamar}")

        # Generate and store OTP
        def generate_otp(length: int = 6) -> str:
            """Generate a random numeric OTP with given length"""
            return ''.join(random.choices('0123456789', k=length))
        
        def store_otp_in_redis(phone_number: str, otp: str) -> bool:
            try:
                key = f"otp:{phone_number}"
                expire_seconds = current_app.config.get('OTP_EXPIRE_SECONDS', 300)
                redis_client = getattr(current_app, 'redis_client_otp', None)
                if redis_client is None:
                    logger.error("Redis client for OTP not available")
                    return False
                redis_client.setex(key, expire_seconds, otp)
                return True
            except Exception as e:
                logger.error(f"Failed to store OTP in Redis: {e}", exc_info=True)
                return False
                
        # Save user to database
        db.session.add(new_user_obj)
        db.session.commit()
        
        # Kirim notifikasi pendaftaran (bukan OTP) ke pengguna
        try:
            # Impor helper untuk mengirim notifikasi WhatsApp
            from app.services.user_management.helpers import _send_whatsapp_notification
            
            # Kirim notifikasi ke pengguna bahwa pendaftaran sedang menunggu persetujuan
            context = {
                "full_name": data_input.full_name,
                "link_user_app": current_app.config.get('APP_LINK_USER')
            }
            _send_whatsapp_notification(normalized_phone_number, "user_self_register_pending", context)
            
            # Notify admins about the new user registration
            # Cek jika notifikasi admin diaktifkan
            notify_admins = current_app.config.get('ENABLE_ADMIN_NOTIFICATIONS', 'True') == 'True'
            
            if notify_admins:
                # Dapatkan semua admin dan super admin untuk notifikasi
                admin_phones = db.session.scalars(select(User.phone_number).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))).all()
                
                admin_context = {
                    "full_name": data_input.full_name,
                    "phone_number": normalized_phone_number,
                    "role": data_input.register_as_komandan and "KOMANDAN" or "USER",
                    "blok": data_input.blok or "-",
                    "kamar": data_input.kamar or "-"
                }
                
                for admin_phone in admin_phones:
                    try:
                        _send_whatsapp_notification(admin_phone, "new_user_registration_to_admin", admin_context)
                    except Exception as admin_ex:
                        logger.error(f"Failed to notify admin {admin_phone}: {str(admin_ex)}")
                    
        except Exception as e:
            logger.error(f"[Register] ⚠️ Failed to send WhatsApp notifications: {str(e)}", exc_info=True)
            # Continue even if WhatsApp fails
        
        return jsonify({
            "message": "Pendaftaran berhasil diterima! Kami akan memproses permintaan Anda dan pemberitahuan telah dikirim ke WhatsApp Anda.",
            "phone_number": normalized_phone_number
        }), HTTPStatus.OK
        
    except ValueError as e:
        error_details = str(e)
        logger.warning(f"[Register] ⚠️ Validation error: {error_details}")
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=error_details).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
        
    except Exception as e:
        logger.error(f"[Register] 💥 Unexpected error during registration: {str(e)}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tak terduga.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

@auth_bp.route('/detect-client-info', methods=['GET'])
@limiter.limit("30 per minute;100 per hour")
def detect_client_info():
    """
    ENHANCED V3: Deteksi informasi client (IP, MAC) menggunakan Client Detection Service
    Lebih agresif dalam mencari MAC untuk browser biasa dengan retry mechanism
    
    ---
    tags:
      - Authentication
    responses:
      200:
        description: Client info detected successfully
      429:
        description: Rate limited due to too many requests
    """
    try:
        # Get client information from headers
        frontend_ip = request.headers.get('X-Frontend-Detected-IP')
        frontend_mac = request.headers.get('X-Frontend-Detected-MAC')
        force_refresh = request.headers.get('force-refresh', '').lower() == 'true' or request.args.get('force', '').lower() in ('true', '1', 't')
        is_browser = not is_captive_browser_request()
        
        # PERBAIKAN: Rate limiting untuk mencegah overload pada RouterOS API
        client_ip = get_client_ip()
        rate_limit_key = f"ratelimit:detect:{client_ip}"
        redis_client = getattr(current_app, 'redis_client_otp', None)
        
        if redis_client:
            try:
                # Improved rate limiting - max 30 requests per minute per IP with burst allowance
                # This is much more lenient than the previous 5 requests per 10 seconds
                request_count = redis_client.incr(rate_limit_key)
                if request_count == 1:
                    # Set expiration only on first request
                    redis_client.expire(rate_limit_key, 60)  # 1 minute window
                
                # Allow burst of 3 requests without rate limiting
                if request_count > 30 and not force_refresh:
                    # Track client that hit rate limit for analysis
                    redis_client.setex(
                        f"rate_limited:{client_ip}",
                        3600,  # 1 hour tracking
                        f"{request_count}:{time.time()}"
                    )
                    
                    logger.warning(f"[DETECT-CLIENT] ⛔ Rate limited request from IP {client_ip} ({request_count} requests/min)")
                    
                    # Return 429 with proper headers
                    response = jsonify({
                        "error": "Rate limited",
                        "message": "Too many detection requests. Please try again in a few seconds.",
                        "retry_after": 5
                    })
                    response.status_code = 429
                    response.headers["Retry-After"] = "5"
                    return response
            except Exception as e:
                # Rate limiting failure should not block the request
                logger.warning(f"[DETECT-CLIENT] Rate limiting error: {str(e)}")
        
        # PERBAIKAN: Gunakan layanan terpisah untuk deteksi client
        logger.info(f"[DETECT-CLIENT] Detecting client info (force_refresh={force_refresh}, browser={is_browser})")
        detection_start = time.time()
        
        # Track this IP for ARP warming priority
        if client_ip:  # Only track if we have a valid client IP
            cache_manager.track_ip_access(client_ip)
        
        # For regular browsers (non-captive), try to warm ARP cache first if IP is known
        if is_browser and client_ip and not frontend_mac:
            try:
                # Import here to avoid circular imports
                from app.utils.ip_mac_warming import warm_ip
                
                # Try to warm the IP address (non-blocking)
                warm_success, warm_mac = warm_ip(client_ip, aggressive=True)
                if warm_success and warm_mac:
                    logger.info(f"[DETECT-CLIENT] ✅ ARP warming successful for {client_ip} → {warm_mac}")
                    # If we found the MAC through warming, use it directly
                    frontend_mac = warm_mac
            except Exception as e:
                logger.warning(f"[DETECT-CLIENT] ARP warming error: {str(e)}")
        
        # Gunakan Client Detection Service with improved parameters
        client_info = ClientDetectionService.get_client_info(
            frontend_ip=frontend_ip,
            frontend_mac=frontend_mac,
            force_refresh=force_refresh,
            use_cache=not force_refresh,
            is_browser=is_browser  # Pass browser flag for optimized detection
        )
        
        # Mapping output ke format API
        elapsed_ms = round((time.time() - detection_start) * 1000, 2)
        
        # Format response untuk API
        result = {
            "status": "SUCCESS",
            "summary": {
                "detected_ip": client_info.get("detected_ip"),
                "detected_mac": client_info.get("detected_mac"),
                "ip_detected": client_info.get("ip_detected", False),
                "mac_detected": client_info.get("mac_detected", False),
                "access_mode": client_info.get("access_mode", "unknown"),
                "user_guidance": client_info.get("user_guidance")
            },
            "mikrotik_lookup": client_info.get("mikrotik_lookup", {}),
            "timestamp": time.time(),
            "elapsed_ms": elapsed_ms,
            "cached": client_info.get("cached", False),
            "is_browser": is_browser,
            "is_captive_browser": not is_browser,
            "force_refresh": force_refresh
        }
        # Bubble up detected values at top-level for easier frontend consumption
        try:
            result["ip"] = result["summary"].get("detected_ip")
            result["mac"] = result["summary"].get("detected_mac")
        except Exception:
            pass
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error detecting client info: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to detect client info"}), 500

@auth_bp.route('/detect-client', methods=['GET'])
def detect_client():
    """
    Optimized client detection using ClientDetectionService
    
    ---
    tags:
      - Authentication
    parameters:
      - name: ip
        in: query
        schema:
          type: string
        description: IP address from frontend detection
      - name: mac
        in: query
        schema:
          type: string
        description: MAC address from frontend detection
      - name: force_refresh
        in: query
        schema:
          type: boolean
        description: Force refresh of detection data
    responses:
      200:
        description: Successful client detection
      500:
        description: Detection error
    """
    try:
        # Parse query parameters
        frontend_ip = request.args.get('ip')
        frontend_mac = request.args.get('mac')
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        logger.info(f"[DETECT-CLIENT] Request from IP: {frontend_ip}, MAC: {frontend_mac}")
        
        # Use centralized detection service
        detection_result = ClientDetectionService.get_client_info(
            frontend_ip=frontend_ip,
            frontend_mac=frontend_mac,
            force_refresh=force_refresh,
            use_cache=True
        )
        
        # Create or update session
        if detection_result.get('ip_detected') and detection_result.get('mac_detected'):
            AuthSessionService.create_session(
                client_ip=detection_result['detected_ip'],
                client_mac=detection_result['detected_mac'],
                session_type="detection",
                metadata={
                    "access_mode": detection_result['access_mode'],
                    "mikrotik_lookup": detection_result['mikrotik_lookup']
                }
            )
            AuthSessionService.update_session(
                client_ip=detection_result['detected_ip'],
                client_mac=detection_result['detected_mac'],
                activity="client_detected"
            )
        
        # Using standardized API response
        from app.utils.api_response import success_response
        return success_response(
            data=detection_result, 
            message="Client detection successful"
        )
        
    except Exception as e:
        logger.error(f"[DETECT-CLIENT] Error: {e}")
        
        # Using standardized API response
        from app.utils.api_response import error_response, ApiErrorCode
        return error_response(
            message="Detection failed: " + str(e),
            error_code=ApiErrorCode.CLIENT_DETECTION_ERROR,
            status_code=500,
            data={
                "user_guidance": "Terjadi kesalahan saat mendeteksi perangkat. Silakan coba lagi."
            }
        )

@auth_bp.route('/sync-device', methods=['POST'])
def sync_device():
    """
    [Arsitektur 2.0] Sinkronisasi device yang dioptimalkan dengan Address List
    """
    try:
        from flask_jwt_extended import get_current_user
        from app.utils.formatters import format_to_local_phone
        from app.infrastructure.gateways.mikrotik_client import find_and_update_address_list_entry

        data = request.get_json(silent=True) or {}

        # Prefer IP/MAC provided by frontend if present; also read from query and headers
        requested_ip = (
            data.get('ip') or data.get('client_ip')
            or request.args.get('ip') or request.args.get('client_ip')
            or request.headers.get('X-Frontend-Detected-IP')
        )
        requested_mac = (
            data.get('mac') or data.get('client_mac')
            or request.args.get('mac') or request.args.get('client_mac')
            or request.headers.get('X-Frontend-Detected-MAC')
        )
        # Obtain trusted IP detected by server (proxy headers) and override stale frontend IP when mismatch
        try:
            _trusted_ip = get_client_ip()
        except Exception:
            _trusted_ip = None
        effective_ip = requested_ip
        if _trusted_ip and requested_ip and _trusted_ip != requested_ip:
            logger.info(f"[SYNC-DEVICE] Overriding frontend IP {requested_ip} with trusted {_trusted_ip}")
            effective_ip = _trusted_ip
        # Tag the source for observability
        try:
            request.environ['CLIENT_IP_SOURCE'] = request.environ.get('CLIENT_IP_SOURCE', 'unknown') + '|sync-device'
        except Exception:
            pass
        # Detect if IP or MAC might have changed
        is_ip_mac_change = False
        has_previous_ip = False
        
        # Check if we have a current user that might have an IP/MAC mismatch
        current_user = None
        try:
            current_user = get_current_user()
            if current_user:
                prev_ip = getattr(current_user, 'last_login_ip', None)
                has_previous_ip = bool(prev_ip)
                # If the current IP doesn't match the last known one, we might have an IP change
                if prev_ip and effective_ip and prev_ip != effective_ip:
                    logger.warning(f"[SYNC-DEVICE] ⚠️ Detected possible IP change from {prev_ip} to {effective_ip}")
                    is_ip_mac_change = True
        except Exception:
            pass
            
        # Look for a device matching the MAC address to detect MAC changes
        if not is_ip_mac_change and requested_mac:
            try:
                device = db.session.execute(
                    select(UserDevice).filter_by(mac_address=requested_mac)
                ).scalar_one_or_none()
                
                if device and device.user:
                    last_ip = getattr(device.user, 'last_login_ip', None)
                    if last_ip and effective_ip and last_ip != effective_ip:
                        logger.warning(f"[SYNC-DEVICE] ⚠️ Device {requested_mac} previously used with IP {last_ip}, now using {effective_ip}")
                        is_ip_mac_change = True
            except Exception as e:
                logger.warning(f"[SYNC-DEVICE] Failed to check for MAC change: {e}")
        
        try:
            # For IP/MAC changes or no previous context, do a more thorough detection
            if is_ip_mac_change or not has_previous_ip:
                logger.info(f"[SYNC-DEVICE] Using thorough detection for possible IP/MAC change (is_ip_mac_change={is_ip_mac_change})")
                # Use the special force_refresh_detection method that does thorough cache clearing first
                detection_result = ClientDetectionService.force_refresh_detection(
                    client_ip=effective_ip or requested_ip,
                    client_mac=requested_mac,
                    is_browser=not is_captive_browser_request()
                )
            else:
                # Normal path - First attempt with forced refresh for accurate detection
                detection_result = ClientDetectionService.get_client_info(
                    frontend_ip=effective_ip or requested_ip,
                    frontend_mac=requested_mac,
                    force_refresh=True,  # Always force refresh for best accuracy during sync
                    use_cache=False  # Don't use cache for sync to ensure we get latest state
                )
        except Exception as e:
            logger.warning(f"[SYNC-DEVICE] Error during forced refresh detection: {e}")
            # Fallback to cached detection if forced refresh fails
            try:
                # Clear caches first if this might be an IP/MAC change
                if is_ip_mac_change:
                    ClientDetectionService.clear_cache(effective_ip or requested_ip, requested_mac)
                    
                detection_result = ClientDetectionService.get_client_info(
                    frontend_ip=effective_ip or requested_ip,
                    frontend_mac=requested_mac,
                    force_refresh=True,  # Still try to force refresh even in fallback
                    use_cache=False  # Don't use cache in fallback to avoid stale data
                )
            except Exception as e2:
                logger.error(f"[SYNC-DEVICE] Both detection attempts failed: {e2}")
                detection_result = {
                    'detected_ip': effective_ip or requested_ip,
                    'detected_mac': requested_mac,
                    'status': 'ERROR',
                    'is_captive': False
                }

        # Use provided values first, then fallback to detected values
        client_ip = (effective_ip or requested_ip) or detection_result.get('detected_ip')
        client_mac = requested_mac or detection_result.get('detected_mac')

        if not client_ip:
            return jsonify({
                "status": "ERROR",
                "message": "IP tidak dapat dideteksi",
                "action": "redirect_to_network_setup"
            }), 400
        
    # Catatan: Jangan hitung sebagai failure pada awal request. Hanya tingkatkan counter saat terjadi error nyata.

        # Coba dapatkan user dari JWT (jika sudah login)
        current_user = None
        try:
            current_user = get_current_user()
        except Exception:
            pass
        
        # Mode Legacy - Jika tidak ada JWT atau belum login, menggunakan metode lama
        if not current_user:
            # Jika membutuhkan persetujuan eksplisit, JANGAN lakukan bypass/lease otomatis
            try:
                if False:  # HOTFIX: Bypass device authorization check
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={"sync_status": "requires_authorization", "registered": False},
                        activity="device_sync_requires_explicit_auth_legacy"
                    )
                    return jsonify({
                        "status": "DEVICE_UNREGISTERED",
                        "registered": False,
                        "requires_explicit_authorization": True,
                        "message": "Perangkat memerlukan otorisasi eksplisit",
                        "ip": client_ip,
                        "mac": client_mac,
                        "action": "redirect_to_authorize"
                    }), 200
            except Exception:
                # Fallback ke flow lama bila terjadi error membaca config
                pass
            device = None
            user = None
            
            try:
                # 1. Cari device berdasarkan MAC
                if client_mac:
                    device = db.session.execute(
                        select(UserDevice).filter_by(mac_address=client_mac)
                    ).scalar_one_or_none()
                    if device:
                        user = device.user
                        logger.info(f"[SYNC-DEVICE] Device found: {device.id} for user {user.id}")
                
                # 2. Jika tidak ditemukan, cari user berdasarkan IP terakhir
                if not device and client_ip:
                    user = db.session.execute(
                        select(User).filter_by(last_login_ip=client_ip)
                    ).scalar_one_or_none()
                    if user:
                        logger.info(f"[SYNC-DEVICE] User found by IP: {user.id}")
                
                # 3. Status dan response
                if device and user:
                    # Check if IP might have changed
                    is_ip_changed = False
                    try:
                        prev_ip = getattr(user, 'last_login_ip', None)
                        if prev_ip and client_ip and prev_ip != client_ip:
                            logger.warning(f"[SYNC-DEVICE] (legacy) ⚠️ IP changed from {prev_ip} to {client_ip}")
                            is_ip_changed = True
                            # Force a fresh detection when IP changes to ensure we have accurate MAC
                            if is_ip_changed:
                                try:
                                    logger.info(f"[SYNC-DEVICE] (legacy) Re-detecting with force refresh due to IP change")
                                    # Clear all caches first to ensure fresh detection
                                    ClientDetectionService.clear_cache(client_ip, client_mac)
                                    # Do a completely fresh detection
                                    fresh_result = ClientDetectionService.force_refresh_detection(
                                        client_ip=client_ip,
                                        client_mac=client_mac,
                                        is_browser=not is_captive_browser_request()
                                    )
                                    # Update our client_mac if it was successfully detected
                                    if fresh_result.get('mac_detected'):
                                        detected_mac = fresh_result.get('detected_mac')
                                        if detected_mac and detected_mac != client_mac:
                                            logger.info(f"[SYNC-DEVICE] (legacy) ⚠️ MAC changed from {client_mac} to {detected_mac}")
                                            client_mac = detected_mac
                                except Exception as e_fresh:
                                    logger.error(f"[SYNC-DEVICE] (legacy) Fresh detection failed after IP change: {e_fresh}")
                    except Exception as e_check:
                        logger.warning(f"[SYNC-DEVICE] (legacy) IP change check failed: {e_check}")
                    
                    # Reset failure counter on success
                    AuthSessionService.reset_failure_counter(client_ip, "sync_device")

                    # Check if device needs explicit authorization
                    if device.status != 'APPROVED' and current_app.config.get("REQUIRE_EXPLICIT_DEVICE_AUTH"):
                        AuthSessionService.update_session(
                            client_ip=client_ip,
                            client_mac=client_mac,
                            updates={"sync_status": "requires_authorization", "registered": False},
                            activity="device_sync_requires_explicit_auth"
                        )
                        return jsonify({
                            "status": "DEVICE_AUTHORIZATION_REQUIRED",
                            "registered": False,
                            "requires_explicit_authorization": True,
                            "message": "Perangkat memerlukan otorisasi eksplisit",
                            "data": {"device_info": {"mac": client_mac, "ip": client_ip, "id": str(device.id)}}
                        }), 200
                    
                    # If device is approved or explicit authorization is not required
                        # Best-effort: upsert bypass & static DHCP lease even without JWT
                        try:
                            list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
                            from app.utils.formatters import format_to_local_phone as _fmt_local
                            comment = _fmt_local(user.phone_number) if user and getattr(user, 'phone_number', None) else None
                            if list_name and comment and client_ip:
                                try:
                                    # If IP changed, ensure we remove the old one first
                                    if is_ip_changed and prev_ip:
                                        try:
                                            from app.infrastructure.gateways.mikrotik_client import remove_ip_from_address_list
                                            ok_rm, msg_rm = remove_ip_from_address_list(list_name, prev_ip)
                                            if ok_rm:
                                                logger.info(f"[SYNC-DEVICE] (legacy) Removed old bypass {prev_ip} after IP change")
                                        except Exception as e_rm:
                                            logger.warning(f"[SYNC-DEVICE] (legacy) Failed to remove old bypass: {e_rm}")
                                            
                                    # Now update or add the new entry
                                    ok_upd, msg_upd = find_and_update_address_list_entry(list_name, client_ip, comment)
                                    if not ok_upd:
                                        from app.infrastructure.gateways.mikrotik_client import add_ip_to_address_list
                                        ok_add, msg_add = add_ip_to_address_list(list_name, client_ip, comment)
                                        if ok_add:
                                            logger.info(f"[SYNC-DEVICE] (legacy) Bypass added for {client_ip} comment {comment}")
                                        else:
                                            logger.warning(f"[SYNC-DEVICE] (legacy) Bypass update failed: {msg_upd} / add failed: {msg_add}")
                                    else:
                                        logger.info(f"[SYNC-DEVICE] (legacy) Bypass ensured for {client_ip}")
                                    # Purge stale entries with same comment but different IP
                                    try:
                                        from app.infrastructure.gateways.mikrotik_client_impl import _get_api_from_pool  # type: ignore
                                        api = _get_api_from_pool()
                                        if api is not None:
                                            res = api.get_resource("/ip/firewall/address-list")
                                            entries = res.get(list=list_name, comment=comment)
                                            for ent in entries:
                                                ent_ip = ent.get('address')
                                                if ent_ip and ent_ip != client_ip:
                                                    ent_id = ent.get('.id') or ent.get('id')
                                                    if ent_id:
                                                        try:
                                                            res.remove(id=ent_id)
                                                            logger.info(f"[SYNC-DEVICE] (legacy) Purged stale bypass {ent_ip} for comment {comment}")
                                                        except Exception:
                                                            pass
                                    except Exception:
                                        pass
                                except Exception as _e_b:
                                    logger.warning(f"[SYNC-DEVICE] (legacy) Bypass ensure error: {_e_b}")

                            # Ensure DHCP static lease
                            if client_ip and client_mac and comment:
                                try:
                                    # Always remove existing leases for this MAC first
                                    try:
                                        _ok_rm, _ = find_and_remove_static_lease_by_mac(client_mac)
                                        if _ok_rm:
                                            logger.info(f"[SYNC-DEVICE] (legacy) Removed existing lease for MAC {client_mac}")
                                    except Exception:
                                        _ok_rm = False
                                    
                                    # Create new lease with current IP/MAC using the configured DHCP server name
                                    ok_lease, msg_lease = create_static_lease(client_ip, client_mac, comment)
                                    if ok_lease:
                                        dhcp_server = current_app.config.get("MIKROTIK_DHCP_SERVER_NAME") or "default"
                                        logger.info(f"[SYNC-DEVICE] (legacy) DHCP lease ensured for {client_ip}/{client_mac} on server {dhcp_server}")
                                    else:
                                        logger.warning(f"[SYNC-DEVICE] (legacy) DHCP lease not ensured: {msg_lease}")
                                except Exception as _e_le:
                                    logger.warning(f"[SYNC-DEVICE] (legacy) DHCP lease error: {_e_le}")
                            
                            # Update user's last_login_ip for traceability
                            try:
                                if user and client_ip:
                                    user.last_login_ip = client_ip
                                    db.session.commit()
                            except Exception:
                                db.session.rollback()
                        except Exception as _e:
                            logger.debug(f"[SYNC-DEVICE] (legacy) Post-detect actions skipped: {_e}")
                            
                    # Update session
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={
                            "user_id": str(user.id),
                            "device_id": str(device.id),
                            "sync_status": "found"
                        },
                        activity=f"device_sync_success:user_{user.id}"
                    )
                    
                    return jsonify({
                        "status": "DEVICE_VALID",
                        "registered": True,
                        "user_id": str(user.id),
                        "device_id": str(device.id),
                        "user_name": user.full_name,
                        "phone": user.phone_number,
                        "message": "Device ditemukan dan tersinkronisasi",
                        "ip": client_ip,
                        "mac": client_mac,
                        "action": "proceed_to_dashboard"
                    }), 200
                else:
                    # Device belum terdaftar
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={"sync_status": "not_found"},
                        activity="device_sync_not_registered"
                    )
                    
                    return jsonify({
                        "status": "DEVICE_UNREGISTERED",
                        "registered": False,
                        "message": "Device belum terdaftar",
                        "ip": client_ip,
                        "mac": client_mac,
                        "action": "redirect_to_register",
                        "consecutive_failures": 0
                    }), 200
            except Exception as db_error:
                logger.error(f"[SYNC-DEVICE] Database error: {db_error}")
                db.session.rollback()
                raise
        
        # Mode Arsitektur 2.0 - User sudah login (JWT valid)
        else:
            try:
                # Get bypass address list name
                list_name = current_app.config['MIKROTIK_BYPASS_ADDRESS_LIST']
                # Format phone untuk comment di address list
                comment = format_to_local_phone(current_user.phone_number)
                if not comment:
                    return jsonify({
                        "status": "ERROR",
                        "message": "Nomor telepon tidak valid",
                        "action": "update_profile"
                    }), 400

                # Check if device requires explicit authorization
                try:
                    require_explicit = current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH', True)
                except Exception:
                    require_explicit = True
                
                # Find device by MAC address
                device = None
                if client_mac:
                    device = db.session.execute(
                        select(UserDevice).filter_by(mac_address=client_mac)
                    ).scalar_one_or_none()
                
                # If device exists, check its status
                device_authorized = False
                if device:
                    # Update the device with current user_id
                    if device.user_id != current_user.id:
                        device.user_id = current_user.id
                        db.session.commit()
                    
                    # Check if device is already approved
                    device_authorized = (device.status == 'APPROVED')
                
                # --- PERBAIKAN MODAL POPUP ---
                # If device authorization is required and device is not approved
                if require_explicit and ((device and not device_authorized) or not device):
                    current_app.logger.warning(
                        f"[SYNC-DEVICE] New device detected for user {current_user.id} "
                        f"({client_ip}/{client_mac}). Authorization required."
                    )
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={
                            "user_id": str(current_user.id),
                            "sync_status": "requires_authorization",
                            "lease_updated": False
                        },
                        activity=f"device_requires_authorization:user_{current_user.id}"
                    )
                    return jsonify({
                        "status": "DEVICE_AUTHORIZATION_REQUIRED",
                        "message": "Perangkat baru terdeteksi. Silakan otorisasi perangkat ini untuk melanjutkan.",
                        "data": {
                            "device_info": {
                                "ip": client_ip,
                                "mac": client_mac,
                                "user_id": str(current_user.id),
                                "id": str(device.id) if device else None
                            }
                        },
                        "registered": False,
                        "requires_explicit_authorization": True,
                        "action": "authorize_device"
                    }), 200

                # Update/ensure address list entry for current IP
                ok, msg = find_and_update_address_list_entry(list_name, client_ip, comment)
                if not ok:
                    # If not found, add new entry for this IP with comment
                    try:
                        from app.infrastructure.gateways.mikrotik_client import add_ip_to_address_list, remove_ip_from_address_list
                        ok_add, msg_add = add_ip_to_address_list(list_name, client_ip, comment)
                        if not ok_add:
                            logger.error(f"[SYNC-DEVICE] Failed to add bypass for {client_ip}: {msg_add}")
                            return jsonify({"status": "ERROR", "message": msg_add}), 500
                    except Exception as add_e:
                        logger.error(f"[SYNC-DEVICE] Error adding bypass: {add_e}")
                        return jsonify({"status": "ERROR", "message": str(add_e)}), 500
                else:
                    try:
                        from app.infrastructure.gateways.mikrotik_client import remove_ip_from_address_list
                    except Exception:
                        remove_ip_from_address_list = None  # type: ignore

                # Remove previous IP from bypass if changed; also purge any stale entries for this comment
                prev_ip = getattr(current_user, 'last_login_ip', None)
                if 'remove_ip_from_address_list' in locals() and remove_ip_from_address_list:
                    if prev_ip and prev_ip != client_ip:
                        try:
                            ok_rm, msg_rm = remove_ip_from_address_list(list_name, prev_ip)
                            if ok_rm:
                                logger.info(f"[SYNC-DEVICE] Removed old bypass {prev_ip} from {list_name}")
                            else:
                                logger.warning(f"[SYNC-DEVICE] Failed to remove old bypass {prev_ip}: {msg_rm}")
                        except Exception as rm_e:
                            logger.warning(f"[SYNC-DEVICE] Error removing old bypass: {rm_e}")
                    # Best-effort cleanup: remove any other entries with same comment but different IPs
                    try:
                        from app.infrastructure.gateways.mikrotik_client_impl import _get_api_from_pool  # type: ignore
                        api = _get_api_from_pool()
                        if api is not None:
                            res = api.get_resource("/ip/firewall/address-list")
                            entries = res.get(list=list_name, comment=comment)
                            for ent in entries:
                                ent_ip = ent.get('address')
                                if ent_ip and ent_ip != client_ip:
                                    ent_id = ent.get('.id') or ent.get('id')
                                    if ent_id:
                                        try:
                                            res.remove(id=ent_id)
                                            logger.info(f"[SYNC-DEVICE] Purged stale bypass entry {ent_ip} with same comment {comment}")
                                        except Exception as _e:
                                            logger.debug(f"[SYNC-DEVICE] Purge skip: {_e}")
                    except Exception:
                        pass

                # Ensure DHCP static lease matches current IP/MAC
                lease_updated = False
                if client_ip and client_mac:
                    try:
                        # Remove any existing static lease for this MAC, then re-create for current IP
                        try:
                            _ok_rm_lease, _msg_rm_lease = find_and_remove_static_lease_by_mac(client_mac)
                        except Exception:
                            _ok_rm_lease, _msg_rm_lease = False, ''
                        
                                # --- PERBAIKAN DHCP SERVER ---
                        # Get configured DHCP server name from environment
                        dhcp_server_name = current_app.config.get("MIKROTIK_DHCP_SERVER_NAME")
                        
                        # Create lease with the server parameter if available
                        lease_params = {
                            "address": client_ip,
                            "mac-address": client_mac,
                            "comment": comment,
                        }
                        
                        if dhcp_server_name and dhcp_server_name.lower() != 'all':
                            lease_params["server"] = dhcp_server_name
                            logger.info(f"[SYNC-DEVICE] Using configured DHCP server '{dhcp_server_name}' for IP {client_ip}")
                        else:
                            logger.info(
                                f"[SYNC-DEVICE] No specific DHCP server configured, RouterOS will automatically select the appropriate server"
                            )
                            
                        # Create the static lease
                        ok_lease, msg_lease = create_static_lease(client_ip, client_mac, comment)
                        
                        lease_updated = ok_lease
                        if ok_lease:
                            logger.info(f"[SYNC-DEVICE] DHCP static lease ensured for {client_ip}/{client_mac} on server '{dhcp_server_name or 'all'}'")
                        else:
                            logger.warning(f"[SYNC-DEVICE] DHCP lease not ensured for {client_ip}/{client_mac}: {msg_lease}")
                    except Exception as le:
                        logger.warning(f"[SYNC-DEVICE] DHCP lease update error: {le}")

                # Update IP terakhir di database
                current_user.last_login_ip = client_ip
                db.session.commit()

                # Reset failure counter & Update session
                AuthSessionService.reset_failure_counter(client_ip, "sync_device")
                AuthSessionService.update_session(
                    client_ip=client_ip,
                    client_mac=client_mac,
                    updates={
                        "user_id": str(current_user.id),
                        "sync_status": "bypass_updated",
                        "lease_updated": lease_updated
                    },
                    activity=f"bypass_and_lease_updated:user_{current_user.id}"
                )

                return jsonify({
                    "status": "DEVICE_VALID",
                    "action": "proceed",
                    "message": "Koneksi telah dipulihkan",
                    "ip": client_ip,
                    "mac": client_mac
                }), 200

            except Exception as db_error:
                logger.error(f"[SYNC-DEVICE] Error in Arch 2.0 mode: {db_error}")
                db.session.rollback()
                raise
            
    except Exception as e:
        logger.error(f"[SYNC-DEVICE] Error: {e}")
        
        # Track error as failure (anti-loop)
        if 'client_ip' in locals() and client_ip:
            try:
                AuthSessionService.track_consecutive_failures(
                    client_ip=client_ip,
                    action="sync_device",
                    failure_reason=f"error:{str(e)[:50]}"
                )
            except Exception:
                pass
        
        return jsonify({
            "status": "ERROR",
            "message": f"Sync failed: {str(e)}",
            "action": "retry_sync"
        }), 500

@auth_bp.route('/request-otp', methods=['POST'])
@limiter.limit("3 per minute; 10 per hour")
def request_otp():
    """
    Request OTP untuk login
    """
    try:
        data = request.get_json() or {}
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({
                "status": "ERROR",
                "message": "Phone number wajib diisi"
            }), 400
        
        logger.info(f"[REQUEST-OTP] Request for {phone_number}")
        
        # Check if user exists
        user = db.session.execute(
            select(User).filter_by(phone_number=phone_number)
        ).scalar_one_or_none()
        
        if not user:
            return jsonify({
                "status": "ERROR",
                "message": "Nomor telepon belum terdaftar"
            }), 404
        
        if user.approval_status != ApprovalStatus.APPROVED:
            return jsonify({
                "status": "ERROR",
                "message": "Akun belum disetujui admin"
            }), 403
        
        # Generate OTP
        redis_client = getattr(current_app, 'redis_client_otp', None)
        if not redis_client:
            return jsonify({
                "status": "ERROR",
                "message": "Service tidak tersedia"
            }), 500
        
        # Generate 6-digit OTP
        otp_code = str(random.randint(100000, 999999))
        
        # Store in Redis with 5 minute expiry
        otp_key = f"otp:{phone_number}"
        redis_client.setex(otp_key, 300, otp_code)
        
        # Send via WhatsApp
        message = f"Kode OTP Anda: {otp_code}\nBerlaku 5 menit."
        
        try:
            send_otp_whatsapp(phone_number, message)
            logger.info(f"[REQUEST-OTP] OTP sent successfully to {phone_number}")
            return jsonify({
                "status": "SUCCESS",
                "message": "Kode OTP telah dikirim via WhatsApp"
            }), 200
        except Exception as e:
            logger.error(f"[REQUEST-OTP] WhatsApp send error: {e}")
            return jsonify({
                "status": "ERROR",
                "message": "Gagal mengirim OTP via WhatsApp"
            }), 500
            
    except Exception as e:
        logger.error(f"[REQUEST-OTP] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/verify-otp', methods=['POST'])
@limiter.limit("5 per minute; 30 per hour")
def verify_otp():
    """
    Optimized OTP verification with auto device registration
    """
    try:
        data = request.get_json() or {}
        # Terima beberapa variasi nama field dari frontend
        phone = data.get('phone') or data.get('phone_number') or data.get('phoneNumber')
        otp_raw = data.get('otp') or data.get('code') or data.get('otp_code')
        otp_code = str(otp_raw) if otp_raw is not None else None

        # Client detection
        detection_result = ClientDetectionService.get_client_info(
            frontend_ip=(data.get('ip') or data.get('client_ip')),
            frontend_mac=(data.get('mac') or data.get('client_mac')),
            force_refresh=False,
            use_cache=True
        )

        client_ip = detection_result.get('detected_ip')
        client_mac = detection_result.get('detected_mac')

        if not phone or not otp_code:
            return jsonify({
                "status": "ERROR",
                "message": "Phone dan OTP wajib diisi"
            }), 400

        # Verify OTP using Redis
        redis_client = getattr(current_app, 'redis_client_otp', None)
        if not redis_client:
            return jsonify({
                "status": "ERROR",
                "message": "Service tidak tersedia"
            }), 500

        otp_key = f"otp:{phone}"
        stored_otp = redis_client.get(otp_key)
        # redis_client dibuat dengan decode_responses=True sehingga get() mengembalikan str
        if not stored_otp or str(stored_otp) != otp_code:
            # Track failure
            if client_ip:
                AuthSessionService.track_consecutive_failures(
                    client_ip=client_ip,
                    action="verify_otp",
                    failure_reason="invalid_otp"
                )

            return jsonify({
                "status": "ERROR",
                "message": "OTP tidak valid atau sudah expired"
            }), 400

        # OTP valid, hapus dari Redis
        redis_client.delete(otp_key)

        try:
            # Cari user
            user = db.session.execute(
                select(User).filter_by(phone_number=phone)
            ).scalar_one_or_none()

            if not user:
                return jsonify({
                    "status": "ERROR",
                    "message": "User tidak ditemukan"
                }), 404

            # Dapatkan nama server DHCP dari environment, fallback ke None jika tidak ada
            dhcp_server_name = current_app.config.get("MIKROTIK_DHCP_SERVER_NAME")
            
            # ✅ SEMPURNAKAN: Hanya periksa apakah perangkat sudah diotorisasi, JANGAN buat perangkat baru
            device_authorized = False
            device_id = None
            
            if client_mac:
                # Periksa apakah perangkat ini sudah pernah disetujui sebelumnya
                device = db.session.execute(
                    select(UserDevice).filter_by(mac_address=client_mac, status='APPROVED')
                ).scalar_one_or_none()
                
                if device:
                    device_authorized = True
                    device_id = str(device.id)
                    logger.info(f"[VERIFY-OTP] Device {client_mac} already authorized for user {user.id}")
                    
                    # Update informasi perangkat jika perlu
                    device.last_seen_at = db.func.now()
                    device.user_agent = request.user_agent.string
                    device.ip_address = client_ip
                    db.session.commit()
            
            # Generate token untuk semua kasus (disetujui atau tidak)
            token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            
            # Reset failure counters
            if client_ip:
                AuthSessionService.reset_failure_counter(client_ip, "verify_otp")
                AuthSessionService.reset_failure_counter(client_ip, "sync_device")
            
            # Jika perangkat belum terotorisasi dan fitur otorisasi eksplisit aktif
            if not device_authorized and current_app.config.get("REQUIRE_EXPLICIT_DEVICE_AUTH"):
                # Kirim status bahwa otorisasi diperlukan, BESERTA token yang valid
                response_data = {
                    "status": "DEVICE_AUTHORIZATION_REQUIRED",
                    "message": "Perangkat baru terdeteksi. Otorisasi diperlukan.",
                    "token": token,  # ✅ PENTING: Tetap sertakan token
                    "user": {"id": str(user.id), "full_name": user.full_name, "role": user.role.value},
                    "data": {
                        "device_info": {
                            "mac": client_mac, 
                            "ip": client_ip,
                            "user_agent": request.user_agent.string
                        }
                    }
                }
                
                db.session.commit()
                resp = jsonify(response_data)
                set_refresh_cookies(resp, refresh_token)
                
                # Log untuk audit dan monitoring
                logger.info(f"[VERIFY-OTP] Device authorization required for MAC={client_mac}, user={user.id}")
                
                # Update session dengan status otorisasi
                if client_ip and client_mac:
                    AuthSessionService.update_session(
                        client_ip=client_ip, 
                        client_mac=client_mac,
                        updates={
                            "user_id": str(user.id),
                            "auth_status": "needs_device_authorization",
                            "token_issued": True
                        },
                        activity="otp_verified_pending_device_auth"
                    )
                
                return resp, 200

            # Update user last login info
            if client_ip:
                user.last_login_ip = client_ip
            if client_mac:
                user.last_login_mac = client_mac
            user.last_login_at = db.func.now()
            db.session.commit()

            # Generate JWT access & refresh token
            token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))

            # Reset failure counters
            if client_ip:
                AuthSessionService.reset_failure_counter(client_ip, "verify_otp")
                AuthSessionService.reset_failure_counter(client_ip, "sync_device")

                # Update session dengan status yang benar (device sudah terotorisasi)
                AuthSessionService.update_session(
                    client_ip=client_ip,
                    client_mac=client_mac,
                    updates={
                        "user_id": str(user.id),
                        "device_id": device_id,  # Bisa null jika perangkat belum diotorisasi sebelumnya
                        "auth_status": "verified",
                        "token_issued": True,
                        "authorized": device_authorized  # ✅ Tambahkan flag ini untuk menunjukkan status otorisasi
                    },
                    activity=f"otp_verification_success:device_{'authorized' if device_authorized else 'pending_authorization'}"
                )

            # Upsert bypass address-list segera setelah login sukses (best-effort)
            try:
                if client_ip:
                    try:
                        from app.utils.formatters import format_to_local_phone
                    except Exception:
                        format_to_local_phone = None  # type: ignore
                    list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST') or ''
                    if list_name and format_to_local_phone:
                        comment = format_to_local_phone(user.phone_number) or ''
                        if comment:
                            # First try to update existing by IP (address)
                            ok_bypass, msg_bypass = find_and_update_address_list_entry(list_name, client_ip, comment)
                            if not ok_bypass:
                                # If not found or failed, try to add
                                from app.infrastructure.gateways.mikrotik_client import add_ip_to_address_list
                                ok_bypass, msg_bypass = add_ip_to_address_list(list_name, client_ip, comment)
                            # Purge stale entries for same comment (different IPs)
                            try:
                                from app.infrastructure.gateways.mikrotik_client_impl import _get_api_from_pool  # type: ignore
                                api = _get_api_from_pool()
                                if api is not None:
                                    res = api.get_resource("/ip/firewall/address-list")
                                    entries = res.get(list=list_name, comment=comment)
                                    for ent in entries:
                                        ent_ip = ent.get('address')
                                        if ent_ip and ent_ip != client_ip:
                                            ent_id = ent.get('.id') or ent.get('id')
                                            if ent_id:
                                                try:
                                                    res.remove(id=ent_id)
                                                    logger.info(f"[VERIFY-OTP] Purged stale bypass entry {ent_ip} with same comment {comment}")
                                                except Exception as _e:
                                                    logger.debug(f"[VERIFY-OTP] Purge skip: {_e}")
                            except Exception:
                                pass
                            # Ensure DHCP static lease exists for this IP/MAC (best-effort)
                            if client_mac:
                                try:
                                    ok_lease, msg_lease = create_static_lease(client_ip, client_mac, comment)
                                    if ok_lease:
                                        logger.info(f"[VERIFY-OTP] ✅ DHCP static lease ensured for {client_ip}/{client_mac}: {msg_lease}")
                                    else:
                                        logger.warning(f"[VERIFY-OTP] ⚠️ DHCP lease not ensured for {client_ip}/{client_mac}: {msg_lease}")
                                except Exception as le:
                                    logger.warning(f"[VERIFY-OTP] DHCP lease error: {le}")
                        else:
                            ok_bypass, msg_bypass = False, 'Empty comment from phone number'
                        if ok_bypass:
                            logger.info(f"[VERIFY-OTP] ✅ Bypass updated for IP {client_ip} with comment {comment}")
                        else:
                            logger.warning(f"[VERIFY-OTP] ⚠️ Failed to update bypass for {client_ip}: {msg_bypass}")
            except Exception as mik_e:
                logger.warning(f"[VERIFY-OTP] MikroTik bypass update error: {mik_e}")

            # Schedule cleanup on access token expiry (no address-list TTL)
            try:
                list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
                # Determine access token TTL
                cfg_exp = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES')
                ttl = 3600  # default 1 hour
                try:
                    if cfg_exp is not None and hasattr(cfg_exp, 'total_seconds'):
                        ttl = int(cfg_exp.total_seconds())
                    elif isinstance(cfg_exp, (int, float)):
                        ttl = int(cfg_exp)
                except Exception:
                    ttl = 3600
                # Prefer the comment computed above; fallback to formatter alias
                try:
                    from app.utils.formatters import format_to_local_phone as _fmt_phone
                except Exception:
                    _fmt_phone = None  # type: ignore
                phone_comment = (comment if 'comment' in locals() and comment else (_fmt_phone(user.phone_number) if _fmt_phone else None))
                schedule_token_cleanup(client_ip, client_mac, phone_comment, list_name, ttl)
            except Exception as sce:
                logger.warning(f"[VERIFY-OTP] Failed to schedule token-expiry cleanup: {sce}")

            response_data: Dict[str, Any] = {
                "status": "SUCCESS",
                "message": "OTP verified successfully",
                "user_id": str(user.id),
                "user_name": user.full_name,
                "phone": user.phone_number,
                "token": token,
                "action": "proceed_to_dashboard",
                "ip": client_ip,
                "mac": client_mac
            }

            if device:
                response_data["device_id"] = str(device.id)
                response_data["device_registered"] = True
                response_data["auto_registration"] = True

            resp = jsonify(response_data)
            try:
                # Set refresh token via HttpOnly cookie
                set_refresh_cookies(resp, refresh_token)
            except Exception:
                pass
            return resp, 200

        except Exception as db_error:
            logger.error(f"[VERIFY-OTP] Database error: {db_error}")
            db.session.rollback()
            raise

    except Exception as e:
        logger.error(f"[VERIFY-OTP] Error: {e}")

        if 'client_ip' in locals() and client_ip:
            AuthSessionService.track_consecutive_failures(
                client_ip=client_ip,
                action="verify_otp",
                failure_reason=f"error:{str(e)[:50]}"
            )

        return jsonify({
            "status": "ERROR",
            "message": f"Verification failed: {str(e)}"
        }), 500

# Refresh access token using refresh token cookie
@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
@limiter.limit("5 per minute; 30 per hour")
def refresh_access_token():
    try:
        identity = get_jwt_identity()
        if not identity:
            return jsonify({
                "status": "ERROR",
                "message": "Invalid refresh token"
            }), 401

        # Rotate refresh token: blocklist current jti and set a new cookie
        current_refresh = get_jwt()  # current refresh JWT data
        jti = current_refresh.get('jti')
        # Determine TTL for blocklist entry
        cfg_exp = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES')
        ttl = 2592000  # default 30 days
        try:
            if cfg_exp is not None and hasattr(cfg_exp, 'total_seconds'):
                ttl = int(cfg_exp.total_seconds())
            elif isinstance(cfg_exp, (int, float)):
                ttl = int(cfg_exp)
        except Exception:
            ttl = 2592000

        # Store to Redis if available
        try:
            r = getattr(current_app, 'redis_client_otp', None)
            if r and jti:
                r.setex(f"jwt:block:{jti}", ttl, '1')
            elif jti:
                # Fallback in-memory (non-shared)
                if not hasattr(current_app, '_jwt_blocklist'):
                    current_app._jwt_blocklist = set()
                current_app._jwt_blocklist.add(jti)
        except Exception as be:
            logger.warning(f"[REFRESH] Blocklist store failed: {be}")

        # Issue new tokens
        new_access = create_access_token(identity=identity)
        new_refresh = create_refresh_token(identity=identity)

        response = jsonify({
            "status": "SUCCESS",
            "access_token": new_access,
            "token": new_access
        })
        try:
            set_refresh_cookies(response, new_refresh)
        except Exception:
            pass

        # Schedule cleanup for new access token lifetime
        try:
            # Compute TTL for access token
            acc_exp = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES')
            acc_ttl = 900  # default 15 min
            try:
                if acc_exp is not None and hasattr(acc_exp, 'total_seconds'):
                    acc_ttl = int(acc_exp.total_seconds())
                elif isinstance(acc_exp, (int, float)):
                    acc_ttl = int(acc_exp)
            except Exception:
                acc_ttl = 900

            # Detect client info for cleanup scheduling
            detection_result = ClientDetectionService.get_client_info()
            client_ip = detection_result.get('detected_ip')
            client_mac = detection_result.get('detected_mac')

            list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
            comment = None
            try:
                # Use phone number as comment if available
                from app.utils.formatters import format_to_local_phone as _fmt_local_phone
                if isinstance(identity, str):
                    # Try to fetch user to get phone number
                    user_obj = None
                    try:
                        user_obj = db.session.get(User, identity)
                    except Exception:
                        user_obj = None
                    if user_obj and getattr(user_obj, 'phone_number', None):
                        comment = _fmt_local_phone(user_obj.phone_number)
            except Exception:
                comment = None

            # Schedule if we have at least IP or MAC
            if (client_ip or client_mac) and acc_ttl:
                try:
                    schedule_token_cleanup(client_ip, client_mac, comment, list_name, acc_ttl, jti)
                except Exception as se:
                    logger.warning(f"[REFRESH] Failed to schedule token cleanup: {se}")
        except Exception as e_sched:
            logger.debug(f"[REFRESH] Scheduling block ignored: {e_sched}")

        return response, 200
    except Exception as e:
        logger.error(f"[REFRESH] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/verify-role', methods=['GET'])
@jwt_required()
def verify_user_role():
    """
    Verify the current user's role
    
    This endpoint checks if the authenticated user has admin privileges
    without relying on frontend assumptions or hardcoded values.
    Used as a security measure when frontend detects inconsistencies.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "status": "ERROR",
                "message": "User not found"
            }), 404
        
        # Check if user has admin role
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        
        return jsonify({
            "status": "SUCCESS",
            "isAdmin": is_admin,
            "role": current_user.role.value
        }), 200
    except Exception as e:
        logger.error(f"Error verifying user role: {e}")
        return jsonify({
            "status": "ERROR",
            "message": "Internal server error"
        }), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user_info():
    """
    Get current user information
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "status": "ERROR",
                "message": "User not found"
            }), 404
        
        return jsonify({
            "status": "SUCCESS",
            "user": {
                "id": str(current_user.id),
                "phone_number": current_user.phone_number,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
                "approval_status": current_user.approval_status.value,
                "is_active": current_user.is_active,
                "is_blocked": current_user.is_blocked
            }
        }), 200
        
    except Exception as e:
        logger.error(f"[GET-ME] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout_user():
    """
    User logout with device cleanup
    """
    try:
        current_user = get_current_user()

        # Get client IP/MAC for cleanup
        detection_result = ClientDetectionService.get_client_info()
        client_ip = detection_result.get('detected_ip')
        client_mac = detection_result.get('detected_mac')

        if current_user:
            logger.info(f"[LOGOUT] User {current_user.id} logging out from IP {client_ip}")

            # Disable MikroTik binding
            mikrotik_username = format_to_local_phone(current_user.phone_number)
            if mikrotik_username:
                try:
                    disable_ip_binding_by_comment(mikrotik_username)
                    logger.info(f"[LOGOUT] Disabled MikroTik binding for {mikrotik_username}")
                except Exception as e:
                    logger.error(f"[LOGOUT] Failed to disable MikroTik binding: {e}")

            # Remove IP from bypass address-list (best-effort)
            try:
                if client_ip:
                    list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
                    if list_name:
                        from app.infrastructure.gateways.mikrotik_client import remove_ip_from_address_list
                        ok_rm, msg_rm = remove_ip_from_address_list(list_name, client_ip)
                        if ok_rm:
                            logger.info(f"[LOGOUT] Bypass entry removed for IP {client_ip} from list {list_name} ({msg_rm})")
                        else:
                            logger.warning(f"[LOGOUT] Failed to remove bypass entry for {client_ip}: {msg_rm}")
            except Exception as e:
                logger.warning(f"[LOGOUT] Bypass removal error: {e}")

            # Remove DHCP static lease by MAC (best-effort)
            if client_mac:
                try:
                    lease_ok, lease_msg = find_and_remove_static_lease_by_mac(client_mac)
                    if lease_ok:
                        logger.info(f"[LOGOUT] DHCP static lease removed for {client_mac}: {lease_msg}")
                    else:
                        logger.warning(f"[LOGOUT] Failed to remove DHCP lease for {client_mac}: {lease_msg}")
                except Exception as le:
                    logger.warning(f"[LOGOUT] DHCP lease removal error: {le}")

            # Destroy session and clear detection cache
            if client_ip:
                AuthSessionService.destroy_session(client_ip)
                ClientDetectionService.clear_cache(client_ip)
                # Clear active marker used by scheduled cleanup
                try:
                    r = getattr(current_app, 'redis_client_otp', None)
                    if r:
                        r.delete(f"auth:active:{client_ip}")
                except Exception:
                    pass

        # Clear JWT cookie
        resp = jsonify({
            "status": "SUCCESS",
            "message": "Logout berhasil"
        })

        # Hapus cookie JWT (access/refresh)
        try:
            unset_jwt_cookies(resp)
        except Exception:
            pass
        resp.set_cookie('app_token', value='', path='/', expires=0, httponly=True, samesite='Lax', secure=request.is_secure)

        return resp, 200
        
    except Exception as e:
        logger.error(f"[LOGOUT] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/authorize-device', methods=['POST'])
@jwt_required()
def authorize_device():
    """
    [Arsitektur 2.0] Endpoint untuk mengotorisasi perangkat baru secara eksplisit.
    Dipanggil saat user menekan tombol "Otorisasi Perangkat Ini" di frontend.
    """
    try:
        from flask_jwt_extended import get_current_user
        from app.utils.formatters import format_to_local_phone
        from app.infrastructure.gateways.mikrotik_client import (
            find_and_remove_static_lease_by_mac,
            create_static_lease,
            find_and_update_address_list_entry,
            add_ip_to_address_list,
            purge_user_from_hotspot
        )
        from sqlalchemy import select as _select
        # Import model audit (akan dibuat jika belum ada) via lazy fallback
        try:
            from app.infrastructure.db.models import AddressListAudit
        except Exception:
            AddressListAudit = None  # type: ignore
        
        data = request.get_json() or {}
        
        # Client detection - Use data from frontend if available, otherwise detect
        client_ip = data.get('client_ip') or data.get('ip')
        client_mac = data.get('client_mac') or data.get('mac')
        device_id = data.get('device_id') # Untuk referensi silang jika ada
        
        # Jika data tidak lengkap, gunakan deteksi
        if not client_ip or not client_mac:
            detection_result = ClientDetectionService.get_client_info(
                frontend_ip=client_ip,
                frontend_mac=client_mac,
                force_refresh=True,  # Force refresh untuk mendapatkan data terkini
                use_cache=False      # Jangan gunakan cache untuk keakuratan
            )
            
            client_ip = detection_result.get('detected_ip') or client_ip
            client_mac = detection_result.get('detected_mac') or client_mac
        
        if not client_ip or not client_mac:
            logger.error("[AUTHORIZE-DEVICE] Tidak dapat mendeteksi IP atau MAC untuk otorisasi")
            return jsonify({
                "status": "ERROR",
                "message": "IP/MAC tidak dapat dideteksi untuk otorisasi perangkat",
                "action": "retry_detection"
            }), 400

        # Simple per-user rate limit (60 detik) dan idempotency lock
        redis_client = getattr(current_app, 'redis_client_otp', None)

        # Get user from JWT
        try:
            current_user = get_current_user()
        except Exception:
            # Testing fallback untuk unit test
            if current_app.config.get('TESTING'):
                test_user_id = request.headers.get('X-Test-User-ID')
                if test_user_id:
                    from app.infrastructure.db.models import User as _User
                    import uuid as _uuid
                    try:
                        _uid = _uuid.UUID(str(test_user_id))
                    except Exception:
                        _uid = None
                    if _uid:
                        current_user = db.session.get(_User, _uid)
            if not current_user:
                return jsonify({
                    "status": "UNAUTHENTICATED",
                    "message": "Token tidak valid atau kadaluarsa",
                    "action": "redirect_to_login"
                }), 401
        
        if not current_user:
            return jsonify({
                "status": "UNAUTHENTICATED",
                "message": "Login terlebih dahulu",
                "action": "redirect_to_login" 
            }), 401

        try:
            # Rate limit sederhana per nomor (1 setiap 30s) - lebih pendek dari sebelumnya
            if redis_client and current_user:
                rl_key = f"authz_rl:{current_user.id}"
                if redis_client.get(rl_key):
                    return jsonify({
                        "status": "RATE_LIMITED",
                        "message": "Terlalu sering melakukan otorisasi. Coba lagi sebentar lagi.",
                        "retry_after": 30
                    }), 429
                redis_client.setex(rl_key, 30, "1")

            # Idempotency: jika request_id dikirim dan sudah sukses, return cepat
            request_id = (data.get('request_id') or '').strip()
            if request_id and redis_client:
                idem_key = f"authz_idem:{request_id}:{current_user.id}"
                if redis_client.get(idem_key):
                    stored = redis_client.get(idem_key).decode('utf-8') if redis_client.get(idem_key) else 'cached'
                    return jsonify({
                        "status": "SUCCESS",
                        "message": "Perangkat sudah diotorisasi (idempotent)",
                        "info": stored
                    }), 200

            # Format nomor telepon untuk comment di MikroTik
            comment = format_to_local_phone(current_user.phone_number)
            if not comment:
                return jsonify({
                    "status": "ERROR",
                    "message": "Nomor telepon tidak valid",
                    "action": "update_profile"
                }), 400
                
            # ✅ SEMPURNAKAN: Cari atau buat entri perangkat untuk user ini
            device = db.session.execute(
                select(UserDevice).filter_by(mac_address=client_mac)
            ).scalar_one_or_none()
            
            if not device:
                # Perangkat benar-benar baru, buat sekarang dengan status APPROVED langsung
                device = UserDevice(
                    user_id=current_user.id,
                    mac_address=client_mac.upper(),
                    ip_address=client_ip,
                    user_agent=request.user_agent.string,
                    device_name=f"Device-{client_mac[-4:]}",
                    status='APPROVED'  # ✅ Langsung set APPROVED
                )
                db.session.add(device)
                logger.info(f"[AUTHORIZE-DEVICE] Perangkat baru {client_mac} dibuat dan disetujui untuk user {current_user.id}")
            else:
                # Perangkat sudah ada, update statusnya menjadi APPROVED dan pastikan terhubung ke user yang benar
                device.status = 'APPROVED'
                device.user_id = current_user.id
                device.ip_address = client_ip
                device.last_seen_at = db.func.now()
                logger.info(f"[AUTHORIZE-DEVICE] Perangkat {client_mac} diperbarui statusnya menjadi APPROVED untuk user {current_user.id}")
            
            list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
            if not list_name:
                logger.warning("[AUTHORIZE-DEVICE] MIKROTIK_BYPASS_ADDRESS_LIST tidak dikonfigurasi")
                return jsonify({
                    "status": "CONFIG_ERROR",
                    "message": "Konfigurasi MikroTik tidak lengkap. Hubungi administrator."
                }), 500
            
            # Simpan info lama untuk debugging jika diperlukan
            old_mac = current_user.trusted_mac_address or current_user.last_login_mac
            old_ip = current_user.last_login_ip
            
            # 1. Hapus lease lama (jika ada dan berbeda dengan yang baru)
            if old_mac and old_mac != client_mac:
                lease_remove_ok, lease_remove_msg = find_and_remove_static_lease_by_mac(old_mac)
                logger.info(f"[AUTHORIZE-DEVICE] Remove old lease for {old_mac}: {lease_remove_msg}")
            
            # 2. Buat lease statis baru
            lease_ok, lease_msg = create_static_lease(client_ip, client_mac, comment)
            if not lease_ok:
                logger.warning(f"[AUTHORIZE-DEVICE] Warning: Gagal membuat lease: {lease_msg}")
                # Teruskan meskipun ada warning ini
            
            # 3 & 4. Update address list (remove old + add new) dengan fallback ke add jika update gagal
            address_list_ok, address_list_msg = find_and_update_address_list_entry(list_name, client_ip, comment)
            
            # ✅ PERBAIKAN: Jika update gagal, coba langsung add entry baru ke address list
            if not address_list_ok:
                logger.warning(f"[AUTHORIZE-DEVICE] Update address list gagal: {address_list_msg}, mencoba add baru")
                # Coba langsung menambahkan ke address list
                add_ok, add_msg = add_ip_to_address_list(list_name, client_ip, comment)
                
                if add_ok:
                    logger.info(f"[AUTHORIZE-DEVICE] Berhasil menambahkan IP ke address list dengan fallback: {add_msg}")
                    address_list_ok = True  # Set ke sukses jika add berhasil
                else:
                    logger.error(f"[AUTHORIZE-DEVICE] Gagal menambahkan IP ke address list: {add_msg}")
            
            # Audit trail untuk address list
            if AddressListAudit:
                try:
                    audit = AddressListAudit(
                        user_id=str(current_user.id),
                        phone_comment=comment,
                        old_ip=old_ip,
                        new_ip=client_ip,
                        old_mac=old_mac,
                        new_mac=client_mac.upper(),
                        action_source='authorize-device',
                        success=address_list_ok
                    )
                    db.session.add(audit)
                except Exception as _e:  # pragma: no cover
                    logger.warning(f"[AUTHORIZE-DEVICE] Audit insert gagal: {_e}")
            
            # 5. Update database
            current_user.trusted_mac_address = client_mac.upper()
            current_user.last_login_mac = client_mac.upper()
            current_user.last_login_ip = client_ip
            current_user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            
            # 6. Kick hotspot session (opsional)
            purge_ok, purge_msg = purge_user_from_hotspot(comment)
            if purge_ok:
                logger.info(f"[AUTHORIZE-DEVICE] Purged user from hotspot: {purge_msg}")
            
            # Catat aktivitas di session
            AuthSessionService.update_session(
                client_ip=client_ip,
                client_mac=client_mac,
                updates={
                    "authorized": True,
                    "authorization_type": "address_list+lease",
                    "old_mac": old_mac,
                    "old_ip": old_ip
                },
                activity=f"device_authorization_v2:user_{current_user.id}"
            )
            
            # Simpan idempotency marker
            if request_id and redis_client:
                redis_client.setex(idem_key, 300, f"ip={client_ip};mac={client_mac}")

            return jsonify({
                "status": "SUCCESS",
                "message": "Perangkat berhasil diotorisasi",
                "ip": client_ip,
                "mac": client_mac,
                "action": "proceed_to_dashboard"
            }), 200
            
        except Exception as db_error:
            logger.error(f"[AUTHORIZE-DEVICE] Database error: {db_error}")
            db.session.rollback()
            raise
    except Exception as e:
        logger.error(f"[AUTHORIZE-DEVICE] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": f"Authorization failed: {str(e)}",
            "action": "retry_authorization"
        }), 500

# Additional utility endpoints
from app.extensions import limiter  # local import to avoid circular issues earlier
@auth_bp.route('/clear-cache', methods=['POST'])
@limiter.limit("5 per minute;30 per hour")
def clear_auth_cache():
    """
    ENHANCED V3: Clear authentication cache dan refresh MAC detection
    Menambahkan mekanisme retry untuk browser yang mengakses secara manual
    
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            ip:
              type: string
              description: IP address to clear cache for
            mac:
              type: string
              description: MAC address to clear cache for
            force_refresh:
              type: boolean
              description: Whether to force refresh after clearing cache
    responses:
      200:
        description: Cache cleared successfully
      500:
        description: Error clearing cache
    """
    try:
        data = request.get_json() or {}
        client_ip = get_client_ip()
        client_mac = get_client_mac()
        # Param frontend
        frontend_ip = data.get('ip')
        frontend_mac = data.get('mac')
        force_refresh = data.get('force_refresh', True)
        # Default: purge grace cache unless explicitly disabled
        purge_grace = (data.get('purge_grace') != False) or request.args.get('purge_grace') == '1'
        is_browser = not is_captive_browser_request()
        
        # Log untuk tracking
        logger.info(f"[CLEAR-CACHE] Request from Client IP: {client_ip}, Frontend IP: {frontend_ip}, MAC: {client_mac or frontend_mac}, Browser: {is_browser}")
        
        # Use frontend provided IP if available and different
        if frontend_ip and frontend_ip != client_ip:
            logger.info(f"[CLEAR-CACHE] Using frontend provided IP: {frontend_ip} (different from detected {client_ip})")
            # We'll clear cache for both IPs to be safe
        
        # Clear all relevant caches
        ClientDetectionService.clear_cache(client_ip, client_mac)  # Clear for detected IP/MAC
        if frontend_ip and frontend_ip != client_ip:
            ClientDetectionService.clear_cache(frontend_ip, frontend_mac)  # Clear for frontend provided IP/MAC
        
        # Clear legacy cache manager
        cache_manager.clear_ip_mac_cache(client_ip, client_mac)
        if frontend_ip and frontend_ip != client_ip:
            cache_manager.clear_ip_mac_cache(frontend_ip, frontend_mac)
        
        # Invalidate RouterOS cache (MAC by IP; also clear host detail caches via service call below)
        from app.infrastructure.gateways.mikrotik_cache import invalidate_ip_cache
        if client_ip:
            invalidate_ip_cache(client_ip)
        if frontend_ip and frontend_ip != client_ip:
            invalidate_ip_cache(frontend_ip)

        # Optional: purge in-memory grace cache for fresher MAC detection
        if purge_grace:
            try:
                from app.infrastructure.gateways import mikrotik_client_impl as _mimpl  # type: ignore
                removed = []
                for ipx in {client_ip, frontend_ip}:
                    if ipx and ipx in getattr(_mimpl, '_last_positive_mac', {}):
                        _mimpl._last_positive_mac.pop(ipx, None)
                        removed.append(ipx)
                if removed:
                    logger.info(f"[CLEAR-CACHE] Purged grace cache for IPs: {removed}")
            except Exception as e:
                logger.warning(f"[CLEAR-CACHE] Failed to purge grace cache: {e}")
        
        # Force immediate MAC detection if IP is available
        detected_info = {}
        ip_to_check = frontend_ip if frontend_ip else client_ip
        
        # ENHANCEMENT: Untuk browser biasa, lakukan multiple attempts dengan delay
        # agar ARP table memiliki waktu untuk update
        if ip_to_check:
            logger.info(f"[CLEAR-CACHE] Forcing fresh MAC detection for IP: {ip_to_check}")
            max_attempts = 2 if is_browser else 1  # Multiple attempts for browser, once for captive
            
            for attempt in range(max_attempts):
                try:
                    # Small delay between attempts for browser
                    if attempt > 0 and is_browser:
                        logger.info(f"[CLEAR-CACHE] Waiting 1s before retry attempt {attempt+1}...")
                        time.sleep(1)  # Wait 1 second between attempts
                    
                    # Attempt immediate refresh of MAC with force_refresh for faster response
                    success, found_mac, search_msg = find_mac_by_ip_comprehensive(ip_to_check, force_refresh=True)
                    detected_info = {
                        "mac_lookup_success": success,
                        "detected_mac": found_mac,
                        "lookup_method": search_msg,
                        "attempt": attempt + 1,
                        "is_browser": is_browser
                    }
                    
                    if success and found_mac:
                        logger.info(f"[CLEAR-CACHE] ✅ Fresh MAC detection (attempt {attempt+1}): {found_mac}")
                        break  # Success, stop trying
                    else:
                        logger.warning(f"[CLEAR-CACHE] ❓ MAC detection attempt {attempt+1} failed: {search_msg}")
                        # Continue to next attempt if available
                        
                except Exception as e:
                    logger.error(f"[CLEAR-CACHE] MAC detection error (attempt {attempt+1}): {e}")
                    detected_info = {
                        "error": str(e),
                        "attempt": attempt + 1,
                        "is_browser": is_browser
                    }
        
        # Now use ClientDetectionService for a comprehensive detection
        if ip_to_check and force_refresh:
            try:
                fresh_result = ClientDetectionService.get_client_info(
                    frontend_ip=ip_to_check, 
                    frontend_mac=frontend_mac or client_mac,
                    force_refresh=True,
                    use_cache=False
                )
                detected_info["service_detection"] = {
                    "ip_detected": fresh_result.get("ip_detected", False),
                    "mac_detected": fresh_result.get("mac_detected", False),
                    "detected_ip": fresh_result.get("detected_ip"),
                    "detected_mac": fresh_result.get("detected_mac"),
                    "access_mode": fresh_result.get("access_mode")
                }
            except Exception as e:
                logger.error(f"[CLEAR-CACHE] Service detection error: {e}")
                detected_info["service_detection_error"] = str(e)
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Cache cleared successfully",
            "cleared_for": {
                "ip": client_ip,
                "frontend_ip": frontend_ip,
                "mac": client_mac,
                "frontend_mac": frontend_mac
            },
            "fresh_detection": detected_info
        }), 200
        
    except Exception as e:
        logger.error(f"[CLEAR-CACHE] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/force-device-sync', methods=['POST'])
def force_device_sync():
    """
    Force device sync for emergency situations
    """
    try:
        data = request.get_json() or {}
        
        # Clear all caches first
        ClientDetectionService.clear_cache()
        
        # Force fresh detection
        detection_result = ClientDetectionService.get_client_info(
            frontend_ip=data.get('ip'),
            frontend_mac=data.get('mac'),
            force_refresh=True,
            use_cache=False
        )
        
        client_ip = detection_result.get('detected_ip')
        client_mac = detection_result.get('detected_mac')
        
        # Reset all failure counters
        if client_ip:
            AuthSessionService.reset_failure_counter(client_ip, "sync_device")
            AuthSessionService.reset_failure_counter(client_ip, "verify_otp")
            AuthSessionService.destroy_session(client_ip, client_mac)
        
        # Force cache refresh
        cache_manager.force_fresh_detection(client_ip, client_mac)
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Force sync completed",
            "detection_result": detection_result,
            "cache_cleared": True,
            "failures_reset": True
        }), 200
        
    except Exception as e:
        logger.error(f"[FORCE-SYNC] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": f"Force sync failed: {str(e)}"
        }), 500

@auth_bp.route('/session-stats', methods=['GET'])
def session_stats():
    """
    Get session statistics for monitoring
    """
    try:
        client_ip = request.args.get('ip')
        stats = AuthSessionService.get_session_stats(client_ip)
        
        return jsonify({
            "status": "SUCCESS",
            "stats": stats
        }), 200
        
    except Exception as e:
        logger.error(f"[SESSION-STATS] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500
        
@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """
    Admin login endpoint
    
    ---
    tags:
      - Authentication
    requestBody:
      content:
        application/json:
          schema:
            type: object
            required:
              - username
              - password
            properties:
              username:
                type: string
                description: Admin username (phone number)
              password:
                type: string
                description: Admin password
    responses:
      200:
        description: Admin login successful
      401:
        description: Invalid credentials
      403:
        description: Account blocked or inactive
    """
    # Check for JSON payload
    if not request.is_json:
        from app.utils.api_response import error_response, ApiErrorCode
        return error_response(
            message="Request body must be JSON",
            error_code=ApiErrorCode.VALIDATION_ERROR,
            status_code=400
        )
    
    # Get login credentials
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Validate required fields
    if not username or not password:
        from app.utils.api_response import error_response, ApiErrorCode
        return error_response(
            message="Username and password are required",
            error_code=ApiErrorCode.VALIDATION_ERROR,
            status_code=400
        )
    
    try:
        # Normalize phone number (username)
        from app.utils.formatters import normalize_to_e164
        from werkzeug.security import check_password_hash
        
        try:
            phone = normalize_to_e164(username)
        except ValueError as e:
            from app.utils.api_response import error_response, ApiErrorCode
            return error_response(
                message=str(e),
                error_code=ApiErrorCode.VALIDATION_ERROR,
                status_code=400
            )
        
        # Check for admin user with tolerant phone matching (E164, raw, local)
        candidates = []
        if phone:
            candidates.append(phone)
        if username:
            candidates.append(str(username).strip())
        try:
            local_fmt = format_to_local_phone(phone or username)
            if local_fmt:
                candidates.append(local_fmt)
        except Exception:
            pass
        # De-duplicate
        candidates = list({c for c in candidates if c})
        user = db.session.scalar(
            select(User).filter(
                User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]),
                User.phone_number.in_(candidates) if candidates else (User.phone_number == phone)
            )
        )
        
        # Validate user and password
        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            from app.utils.api_response import error_response, ApiErrorCode
            return error_response(
                message="Username atau password salah",
                error_code=ApiErrorCode.AUTHENTICATION_ERROR,
                status_code=401
            )
        
        # Check account status
        if not user.is_active or user.is_blocked:
            from app.utils.api_response import error_response, ApiErrorCode
            return error_response(
                message="Akun admin tidak aktif atau diblokir",
                error_code=ApiErrorCode.AUTHORIZATION_ERROR,
                status_code=403
            )
        
        # Update last login time
        import datetime
        from datetime import timezone
        user.last_login_at = datetime.datetime.now(timezone.utc)
        
        # Create login history entry
        from app.infrastructure.db.models import UserLoginHistory
        history_entry = UserLoginHistory()
        history_entry.user_id = user.id
        history_entry.ip_address = get_client_ip()
        history_entry.user_agent_string = request.headers.get('User-Agent', 'Unknown')
        
        db.session.add(history_entry)
        db.session.commit()
        
        # Generate JWT access & refresh token
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        # Using standardized API response
        from app.utils.api_response import success_response
        resp, status_code = success_response(
            data={"token": access_token, "access_token": access_token},
            message="Admin login successful"
        )
        try:
            set_refresh_cookies(resp, refresh_token)
        except Exception:
            pass
        return resp, status_code
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN-LOGIN] Error: {e}", exc_info=True)
        
        from app.utils.api_response import error_response, ApiErrorCode
        return error_response(
            message=f"An unexpected error occurred: {str(e)}",
            error_code=ApiErrorCode.SERVER_ERROR,
            status_code=500
        )


@auth_bp.route('/reject-device', methods=['POST'])
@jwt_required()
def reject_device():
    """
    Endpoint baru untuk menangani penolakan otorisasi perangkat.
    Dipanggil saat user memilih "Tolak & Logout" di frontend.
    """
    try:
        current_user = get_current_user()
        logger.warning(f"[REJECT-DEVICE] User {current_user.id} menolak otorisasi perangkat baru. Memaksa logout.")
        
        # Data untuk logging dan analisis
        client_ip = get_client_ip()
        client_mac = get_client_mac()
        
        if client_ip and client_mac:
            logger.info(f"[REJECT-DEVICE] Perangkat yang ditolak: IP={client_ip}, MAC={client_mac}")
            
            # Opsional: tandai di AuthSession bahwa perangkat ini ditolak
            AuthSessionService.update_session(
                client_ip=client_ip,
                client_mac=client_mac,
                updates={"device_rejected": True, "rejected_at": db.func.now()},
                activity="device_auth_rejected"
            )
        
        # Di sini bisa ditambahkan logika untuk menandai perangkat sebagai ditolak
        # atau tambahkan ke blacklist sementara jika diperlukan
        
        return jsonify({
            "status": "SUCCESS", 
            "message": "Perangkat ditolak. Sesi login akan diakhiri."
        }), 200
        
    except Exception as e:
        logger.error(f"[REJECT-DEVICE] Error: {e}", exc_info=True)
        return jsonify({
            "status": "ERROR",
            "message": f"Gagal memproses penolakan: {str(e)}"
        }), 500
