# backend/app/utils/cache_manager.py
"""
Unified Cache Manager untuk IP/MAC Detection
Mengelola semua cache yang terkait dengan deteksi IP dan MAC address
"""

import logging
import json
import time
from typing import Optional, Dict, Any, List
from flask import current_app

logger = logging.getLogger(__name__)

class CacheManager:
    """Manager terpusat untuk cache IP/MAC detection"""
    
    def __init__(self):
        self.redis_client = None
        self._recently_accessed_ips = {}  # Track IP access frequency
        # Throttling untuk warning Redis unavailable agar log tidak banjir
        self._last_redis_warn = 0.0
        self._redis_warn_interval = 30.0  # detik

    def _throttled_warn(self, msg: str):
        now = time.time()
        if now - self._last_redis_warn > self._redis_warn_interval:
            logger.warning(msg)
            self._last_redis_warn = now
        else:
            logger.debug(msg + " (throttled)")
        
    def _get_redis_client(self):
        """Dapatkan Redis client dengan fallback safety"""
        if self.redis_client is None:
            try:
                # Check if we're in Flask application context
                from flask import current_app, has_app_context
                
                if not has_app_context():
                    logger.debug("CacheManager: No Flask application context available")
                    return None
                    
                self.redis_client = getattr(current_app, 'redis_client_otp', None)
                if self.redis_client:
                    self.redis_client.ping()
                    logger.debug("CacheManager: Redis connected")
                else:
                    self._throttled_warn("CacheManager: Redis client tidak tersedia")
            except RuntimeError as e:
                if "application context" in str(e):
                    logger.debug("CacheManager: Working outside of application context")
                else:
                    self._throttled_warn(f"CacheManager: Redis connection failed: {e}")
                self.redis_client = None
            except Exception as e:
                self._throttled_warn(f"CacheManager: Redis connection failed: {e}")
                self.redis_client = None
        return self.redis_client
        
    def track_ip_access(self, ip_address: str):
        """
        Track IP address access for ARP warming priority
        """
        if not ip_address:
            return
            
        now = time.time()
        self._recently_accessed_ips[ip_address] = {
            'last_accessed': now,
            'access_count': self._recently_accessed_ips.get(ip_address, {}).get('access_count', 0) + 1
        }
        
        # Cleanup old entries occasionally
        if len(self._recently_accessed_ips) > 1000:  # Arbitrary limit to trigger cleanup
            cutoff = now - (24 * 60 * 60)  # 24 hours
            self._recently_accessed_ips = {
                ip: data for ip, data in self._recently_accessed_ips.items()
                if data['last_accessed'] > cutoff
            }
    
    def get_recently_accessed_ips(self, max_count: int = 50, max_age_seconds: int = 3600) -> List[str]:
        """
        Get list of recently accessed IP addresses, ordered by frequency
        
        Args:
            max_count: Maximum number of IPs to return
            max_age_seconds: Maximum age of IPs to consider (default: 1 hour)
            
        Returns:
            List of IP addresses
        """
        if not self._recently_accessed_ips:
            return []
            
        now = time.time()
        cutoff = now - max_age_seconds
        
        # Filter by age and sort by access count (descending)
        recent_ips = sorted(
            [(ip, data) for ip, data in self._recently_accessed_ips.items() 
             if data['last_accessed'] > cutoff],
            key=lambda x: x[1]['access_count'],
            reverse=True
        )
        
        # Return just the IPs, limited to max_count
        return [ip for ip, _ in recent_ips[:max_count]]
    
    def clear_ip_mac_cache(self, ip_address: Optional[str] = None, mac_address: Optional[str] = None):
        """
        Hapus semua cache terkait IP dan MAC address
        Jika tidak ada parameter, hapus semua cache IP/MAC
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            self._throttled_warn("CacheManager: Tidak dapat menghapus cache - Redis tidak tersedia")
            return
            
        try:
            patterns_to_clear = []
            
            if ip_address:
                # Pattern spesifik untuk IP tertentu
                patterns_to_clear.extend([
                    f"mikrotik_cache:mac_by_ip:{ip_address}",
                    f"mikrotik_cache:host_details_ip:{ip_address}",
                    f"client_info_cache:*:{ip_address}:*",
                    f"auth_cache:detect_client:*:{ip_address}:*"
                ])
            elif mac_address:
                # Pattern spesifik untuk MAC tertentu
                patterns_to_clear.extend([
                    f"mikrotik_cache:host_details_mac:{mac_address}",
                    f"client_info_cache:*:*:{mac_address}",
                    f"auth_cache:detect_client:*:*:{mac_address}"
                ])
            else:
                # Hapus semua cache IP/MAC
                patterns_to_clear.extend([
                    "mikrotik_cache:mac_by_ip:*",
                    "mikrotik_cache:host_details_ip:*", 
                    "mikrotik_cache:host_details_mac:*",
                    "client_info_cache:*",
                    "auth_cache:detect_client:*"
                ])
            
            total_deleted = 0
            for pattern in patterns_to_clear:
                try:
                    keys = redis_client.keys(pattern)
                    if keys:
                        deleted = redis_client.delete(*keys)
                        total_deleted += deleted
                        logger.debug(f"CacheManager: Deleted {deleted} keys for pattern {pattern}")
                except Exception as e:
                    logger.warning(f"CacheManager: Error deleting pattern {pattern}: {e}")
            
            if total_deleted > 0:
                logger.info(f"CacheManager: Successfully cleared {total_deleted} cache entries")
            else:
                logger.debug("CacheManager: No cache entries to clear")
                
        except Exception as e:
            logger.error(f"CacheManager: Error clearing IP/MAC cache: {e}")
    
    def clear_client_detection_cache(self):
        """Hapus cache khusus untuk client detection"""
        self.clear_ip_mac_cache()
        
        # Clear in-memory cache juga
        try:
            # Use safer approach to access the in-memory cache
            # Import the module rather than trying to import a specific variable
            import importlib
            auth_routes = importlib.import_module('app.infrastructure.http.auth_routes')
            
            # Check if the module has the cache attribute
            if hasattr(auth_routes, '_client_info_cache'):
                auth_routes._client_info_cache.clear()
                logger.debug("CacheManager: Cleared in-memory client info cache")
            else:
                logger.debug("CacheManager: In-memory client info cache not found in module")
        except ImportError:
            logger.debug("CacheManager: In-memory cache module not available")
    
    def force_fresh_detection(self, ip_address: Optional[str] = None, mac_address: Optional[str] = None):
        """
        Force fresh detection dengan menghapus semua cache terkait
        Dan set flag untuk bypass cache pada request berikutnya
        """
        self.clear_ip_mac_cache(ip_address, mac_address)
        
        redis_client = self._get_redis_client()
        if redis_client:
            try:
                # Set flag untuk force refresh pada request berikutnya
                refresh_key = f"force_refresh:{ip_address or 'global'}:{int(time.time())}"
                redis_client.setex(refresh_key, 60, "1")  # Berlaku 1 menit
                logger.debug(f"CacheManager: Set force refresh flag: {refresh_key}")
            except Exception as e:
                logger.warning(f"CacheManager: Error setting force refresh flag: {e}")
    
    def should_force_refresh(self, ip_address: Optional[str] = None) -> bool:
        """Check apakah harus force refresh berdasarkan flag"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return False
            
        try:
            # Check global flag
            global_keys = redis_client.keys("force_refresh:global:*")
            if global_keys:
                return True
                
            # Check IP specific flag
            if ip_address:
                ip_keys = redis_client.keys(f"force_refresh:{ip_address}:*")
                if ip_keys:
                    return True
                    
            return False
        except Exception as e:
            logger.warning(f"CacheManager: Error checking force refresh flag: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Dapatkan statistik cache untuk monitoring"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return {"error": "Redis tidak tersedia"}
            
        try:
            stats = {
                "mikrotik_mac_cache": len(redis_client.keys("mikrotik_cache:mac_by_ip:*")),
                "mikrotik_host_cache": len(redis_client.keys("mikrotik_cache:host_details_*:*")),
                "client_info_cache": len(redis_client.keys("client_info_cache:*")),
                "auth_detection_cache": len(redis_client.keys("auth_cache:detect_client:*")),
                "force_refresh_flags": len(redis_client.keys("force_refresh:*")),
                "timestamp": int(time.time())
            }
            return stats
        except Exception as e:
            logger.error(f"CacheManager: Error getting cache stats: {e}")
            return {"error": str(e)}

# Global instance
cache_manager = CacheManager()

# Convenience functions
def clear_ip_mac_cache(ip_address: Optional[str] = None, mac_address: Optional[str] = None):
    """Convenience function untuk clear IP/MAC cache"""
    cache_manager.clear_ip_mac_cache(ip_address, mac_address)

def force_fresh_detection(ip_address: Optional[str] = None, mac_address: Optional[str] = None):
    """Convenience function untuk force fresh detection""" 
    cache_manager.force_fresh_detection(ip_address, mac_address)

def should_force_refresh(ip_address: Optional[str] = None) -> bool:
    """Convenience function untuk check force refresh flag"""
    return cache_manager.should_force_refresh(ip_address)
