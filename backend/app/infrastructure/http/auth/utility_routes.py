# backend/app/infrastructure/http/auth/utility_routes.py

import logging
from flask import Blueprint, jsonify, request, current_app

from app.extensions import limiter
from app.services.client_detection_service import ClientDetectionService
from app.services.auth_session_service import AuthSessionService
from app.utils.cache_manager import cache_manager
from app.utils.request_utils import get_client_ip, get_client_mac

logger = logging.getLogger(__name__)

utility_bp = Blueprint('utility', __name__, url_prefix='/auth')

@utility_bp.route('/clear-cache', methods=['POST'])
@limiter.limit("5 per minute;30 per hour")
def clear_auth_cache():
    """Membersihkan cache deteksi IP/MAC."""
    client_ip = get_client_ip()
    client_mac = get_client_mac()
    ClientDetectionService.clear_cache(client_ip, client_mac)
    cache_manager.clear_ip_mac_cache(client_ip, client_mac)
    return jsonify({"status": "SUCCESS", "message": "Cache cleared"}), 200

@utility_bp.route('/force-device-sync', methods=['POST'])
@limiter.limit("5 per minute;20 per hour")
def force_device_sync():
    """
    Endpoint darurat untuk memaksa sinkronisasi perangkat.
    Membersihkan semua cache dan memaksa deteksi ulang.
    
    ⚠️ Catatan: Endpoint ini tidak mengubah status otorisasi perangkat,
    hanya memaksa deteksi ulang dan membersihkan cache.
    Untuk sinkronisasi penuh dengan otorisasi, gunakan /auth/sync-device.
    """
    client_ip = get_client_ip()
    client_mac = get_client_mac()
    
    # Dapatkan data deteksi terbaru
    detection_result = ClientDetectionService.get_client_info(force_refresh=True)
    if detection_result.get('detected_ip'):
        client_ip = detection_result.get('detected_ip')
    if detection_result.get('detected_mac'):
        client_mac = detection_result.get('detected_mac')
    
    # Clear all caches
    ClientDetectionService.clear_cache(client_ip, client_mac)
    cache_manager.clear_ip_mac_cache(client_ip, client_mac)
    
    # Force fresh detection on next request
    cache_manager.force_fresh_detection(client_ip, client_mac)
    
    # Log untuk audit
    logger.warning(f"[FORCE-SYNC] Force device sync triggered for IP={client_ip}, MAC={client_mac}")
    
    # Update status sesi jika IP dan MAC terdeteksi
    if client_ip and client_mac:
        AuthSessionService.update_session(
            client_ip=str(client_ip),
            client_mac=str(client_mac),
            updates={"force_sync_triggered": True},
            activity="force_device_sync"
        )
    
    return jsonify({
        "status": "SUCCESS", 
        "message": "Force sync initialized. Next request will perform fresh detection.",
        "client_ip": client_ip,
        "client_mac": client_mac,
        "detection_result": detection_result
    }), 200

@utility_bp.route('/session-stats', methods=['GET'])
def session_stats():
    """Mendapatkan statistik sesi dari Redis."""
    client_ip = request.args.get('ip') or get_client_ip()
    stats = AuthSessionService.get_session_stats(client_ip)
    return jsonify({"status": "SUCCESS", "stats": stats}), 200

@utility_bp.route('/test-redis', methods=['GET'])
def test_redis():
    """Endpoint untuk menguji koneksi Redis."""
    try:
        redis_client = getattr(current_app, 'redis_client_otp', None)
        if not redis_client:
            return jsonify({"status": "ERROR", "message": "Redis client not configured"}), 500

        test_key = "test:redis:connection"
        test_value = "OK"
        redis_client.set(test_key, test_value, ex=60)
        result = redis_client.get(test_key)
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Redis connection test successful",
            "result": result.decode('utf-8') if result else None,
            "expected": test_value
        }), 200
    except Exception as e:
        logger.error(f"Redis test error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": "Redis connection test failed",
            "error": str(e)
        }), 500
