# backend/app/services/client_detection_service.py
"""
Centralized Client Detection Service
Menggabungkan semua logika deteksi IP/MAC dalam satu service untuk menghindari redundansi
"""

import time
import logging
import json
from typing import Optional, Dict, Any, Tuple
from urllib.parse import unquote
from flask import current_app

from app.utils.request_utils import get_client_ip, get_client_mac, is_captive_browser_request
from app.infrastructure.gateways.mikrotik_client import find_mac_by_ip_comprehensive
from app.infrastructure.gateways.mikrotik_cache import (
    get_cached_mac_by_ip,
    cache_mac_by_ip,
    invalidate_ip_cache,
)
from app.utils.cache_manager import cache_manager

logger = logging.getLogger(__name__)

class ClientDetectionService:
    """Layanan terpusat untuk deteksi informasi client (IP, MAC)"""
    
    @staticmethod
    def _get_redis_client():
        """Get Redis client safely"""
        try:
            return getattr(current_app, 'redis_client_otp', None)
        except RuntimeError:
            return None
    
    @staticmethod
    def get_client_info(
        frontend_ip: Optional[str] = None,
        frontend_mac: Optional[str] = None,
        force_refresh: bool = False,
        use_cache: bool = True,
        is_browser: bool = False
    ) -> Dict[str, Any]:
        """
        Deteksi client info dengan prioritas:
        1. Frontend-provided IP/MAC (jika valid)
        2. Request headers
        3. MikroTik lookup untuk MAC
        
        Args:
            frontend_ip: IP yang dideteksi frontend
            frontend_mac: MAC yang dideteksi frontend  
            force_refresh: Paksa refresh tanpa cache
            use_cache: Gunakan cache atau tidak
            
        Returns:
            Dict dengan client info dan metadata
        """
        current_time = time.time()
        
        # 1. Deteksi IP dengan prioritas
        client_ip = frontend_ip or get_client_ip()
        
        # 2. Deteksi MAC dengan prioritas dan decoding + filter placeholder
        client_mac = None
        placeholder_values = {"00:00:00:00:00:00", "00-00-00-00-00-00"}
        if frontend_mac:
            decoded = unquote(frontend_mac).upper()
            if decoded not in placeholder_values:
                client_mac = decoded
            else:
                logger.info(f"[CLIENT-DETECT] Mengabaikan frontend MAC placeholder {decoded}")
        else:
            raw_mac = get_client_mac()
            if raw_mac:
                decoded = unquote(raw_mac).upper()
                if decoded not in placeholder_values:
                    client_mac = decoded
                else:
                    logger.info(f"[CLIENT-DETECT] Mengabaikan header MAC placeholder {decoded}")
        
        # 3. Cache key untuk konsistensi
        cache_key = f"client_info:{client_ip}:{client_mac}:{int(current_time/10)}"
        
        # 4. Check cache jika enabled dan tidak force refresh
        cached_data = None
        if use_cache and not force_refresh:
            redis_client = ClientDetectionService._get_redis_client()
            if redis_client:
                try:
                    cached_raw = redis_client.get(cache_key)
                    if cached_raw:
                        cached_data = json.loads(cached_raw)
                        logger.debug(f"[CLIENT-DETECT] 📦 Cache hit for {client_ip}")
                        cached_data['cached'] = True
                        cached_data['cache_age'] = current_time - cached_data.get('timestamp', current_time)
                        return cached_data
                except Exception as e:
                    logger.warning(f"[CLIENT-DETECT] Cache read error: {e}")
        
        # 5. Deteksi MAC dari MikroTik jika belum ada / atau saat force refresh
        mikrotik_result = {"success": False, "found_mac": None, "message": "Tidak mencari MAC"}

        if client_ip:
            logger.info(
                f"[CLIENT-DETECT] Mencari MAC untuk IP '{client_ip}' (is_browser={is_browser}, force_refresh={force_refresh})..."
            )
            max_retries = 3 if is_browser else 1
            retry_count = 0

            # Coba ambil dari cache MikroTik dulu (bukan ephemeral detection cache)
            if not force_refresh:
                cached_mac_tuple = get_cached_mac_by_ip(client_ip)
                if cached_mac_tuple:
                    success_c, cached_mac, msg_c = cached_mac_tuple
                    if success_c and cached_mac:
                        client_mac = cached_mac.upper()
                        mikrotik_result = {
                            "success": success_c,
                            "found_mac": client_mac,
                            "message": f"CACHE: {msg_c}",
                        }
                        logger.info(
                            f"[CLIENT-DETECT] ✅ MAC dari cache MikroTik: {client_ip} -> {client_mac}"
                        )
                        retry_count = max_retries + 1  # Skip live lookup
                    else:
                        logger.debug(
                            f"[CLIENT-DETECT] MikroTik cache miss/unsuccessful: {msg_c}"
                        )

            while retry_count <= max_retries:
                try:
                    if force_refresh or (retry_count > 0 and retry_count <= max_retries):
                        invalidate_ip_cache(client_ip)
                        logger.info(
                            f"[CLIENT-DETECT] 🧹 MikroTik MAC cache invalidated untuk IP {client_ip} (retry={retry_count})"
                        )

                    if retry_count > 0:
                        logger.info(
                            f"[CLIENT-DETECT] Percobaan ke-{retry_count+1} untuk IP {client_ip}..."
                        )
                        time.sleep(0.5)

                    success, found_mac, search_msg = find_mac_by_ip_comprehensive(
                        client_ip, force_refresh=force_refresh
                    )
                    mikrotik_result = {
                        "success": success,
                        "found_mac": found_mac,
                        "message": search_msg,
                    }

                    if success and found_mac:
                        client_mac = found_mac.upper()
                        logger.info(
                            f"[CLIENT-DETECT] ✅ MAC ditemukan pada percobaan {retry_count+1}: {client_mac}"
                        )
                        ttl_override = 120 if is_browser else None
                        cache_mac_by_ip(
                            client_ip, True, client_mac, search_msg, ttl=ttl_override
                        )
                        break
                    elif retry_count >= max_retries:
                        logger.warning(
                            f"[CLIENT-DETECT] ❌ MAC tidak ditemukan untuk IP {client_ip} setelah {max_retries+1} percobaan ({search_msg})"
                        )
                        cache_mac_by_ip(
                            client_ip, False, None, search_msg, ttl=15
                        )  # negative cache
                        break
                    else:
                        logger.info(
                            f"[CLIENT-DETECT] ⚠️ MAC belum ditemukan pada percobaan {retry_count+1}, mencoba lagi..."
                        )
                        retry_count += 1

                except Exception as e:  # pragma: no cover
                    logger.error(
                        f"[CLIENT-DETECT] Error MikroTik lookup (percobaan {retry_count+1}): {e}"
                    )
                    mikrotik_result["message"] = f"Error: {str(e)}"
                    if retry_count >= max_retries:
                        break
                    retry_count += 1

            if not mikrotik_result.get("success") and not client_mac:
                logger.warning(
                    f"[CLIENT-DETECT] ❌ MAC tidak ditemukan untuk IP {client_ip} ({mikrotik_result.get('message')})"
                )
                logger.error(
                    f"[MAC-DETECTION-FAILED] IP: {client_ip}, Mode: {'captive' if is_captive_browser_request() else 'web'}"
                )
        
        # 6. Build response
        access_mode = "captive" if is_captive_browser_request() else "web"
        
        result = {
            "status": "SUCCESS",
            "timestamp": current_time,
            "detected_ip": client_ip,
            "detected_mac": client_mac,
            "ip_detected": bool(client_ip),
            "mac_detected": bool(client_mac),
            "access_mode": access_mode,
            "mikrotik_lookup": mikrotik_result,
            "cached": False,
            "force_refresh": force_refresh,
            "user_guidance": ClientDetectionService._get_user_guidance(client_ip, client_mac)
        }
        
        # 7. Cache result jika enabled
        if use_cache:
            redis_client = ClientDetectionService._get_redis_client()
            if redis_client:
                try:
                    # Set different TTL based on detection success
                    ttl = 30 if client_mac else 5  # 30s with MAC, 5s without
                    redis_client.setex(cache_key, ttl, json.dumps(result))
                    logger.debug(f"[CLIENT-DETECT] Cached for {ttl}s: {client_ip} → {client_mac or 'Unknown MAC'}")
                except Exception as e:
                    logger.warning(f"[CLIENT-DETECT] Cache write error: {e}")
        
        # 8. Broadcast via WebSocket if MAC was found (especially for regular browser users)
        if client_ip and client_mac and mikrotik_result.get("success"):
            try:
                # Import here to avoid circular imports
                try:
                    from app.infrastructure.http.websocket_routes import broadcast_mac_detected
                    # Only show notification on regular browsers, not captive portal
                    notify_client = not is_captive_browser_request() and is_browser 
                    clients_notified = broadcast_mac_detected(client_ip, client_mac, notify=notify_client)
                    if clients_notified:
                        logger.info(f"[CLIENT-DETECT] WebSocket notification sent to {clients_notified} clients for IP {client_ip}")
                except ImportError:
                    # WebSocket not available
                    pass
            except Exception as e:
                logger.warning(f"[CLIENT-DETECT] WebSocket broadcast error: {e}")
        
        return result
    
    @staticmethod
    def _get_user_guidance(client_ip: Optional[str], client_mac: Optional[str]) -> str:
        """Generate user guidance based on detection results"""
        if client_ip and client_mac:
            return "IP dan MAC berhasil terdeteksi. Siap untuk login."
        elif client_ip and not client_mac:
            return "IP terdeteksi, namun MAC tidak dapat ditemukan di jaringan. Pastikan Anda terhubung ke WiFi Hotspot."
        else:
            return "Gagal mendeteksi perangkat di jaringan. Pastikan koneksi Anda stabil."
    
    @staticmethod
    def clear_cache(client_ip: Optional[str] = None, client_mac: Optional[str] = None):
        """Clear detection cache for specific or all clients"""
        redis_client = ClientDetectionService._get_redis_client()
        if not redis_client:
            logger.warning("[CLIENT-DETECT] Cannot clear cache - Redis not available")
            return
            
        try:
            if client_ip or client_mac:
                # Clear specific patterns
                pattern = f"client_info:{client_ip or '*'}:{client_mac or '*'}:*"
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    logger.info(f"[CLIENT-DETECT] Cleared {len(keys)} cache entries for IP: {client_ip}, MAC: {client_mac}")
            else:
                # Clear all detection cache
                keys = redis_client.keys("client_info:*")
                if keys:
                    redis_client.delete(*keys)
                    logger.info(f"[CLIENT-DETECT] Cleared {len(keys)} cache entries")
        except Exception as e:
            logger.error(f"[CLIENT-DETECT] Error clearing cache: {e}")
