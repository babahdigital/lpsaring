# backend/app/infrastructure/gateways/mikrotik_cache.py
"""
MikroTik Caching Layer untuk optimasi performa
"""

import logging
import json
from typing import Optional, Tuple, Any, Dict
from flask import current_app
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

class MikroTikCache:
    """Redis-based cache untuk hasil lookup MikroTik."""

    def __init__(self):
        self.redis_client = None
        self.cache_ttl = 300  # 5 minutes default
        # Pipeline related state
        self._pipeline = None
        self._pipeline_buffer = 0
        self._pipeline_batch_size = 0
        self._pipeline_first_ts = None
        self._pipeline_flush_interval_ms = 10  # ms
        
    def _get_redis_client(self):
        """Get Redis client dari Flask app"""
        if self.redis_client is None:
            try:
                self.redis_client = getattr(current_app, 'redis_client_otp', None)
                if self.redis_client:
                    # Test connection
                    self.redis_client.ping()
                    logger.debug("MikroTik cache: Redis client connected")
                else:
                    logger.warning("MikroTik cache: Redis client not available")
            except Exception as e:
                logger.warning(f"MikroTik cache: Redis connection failed: {e}")
                self.redis_client = None
        return self.redis_client

    def _maybe_init_pipeline(self):
        try:
            cfg_batch = int(current_app.config.get('REDIS_PIPELINE_BATCH_SIZE', 0))
        except Exception:
            cfg_batch = 0
        if cfg_batch <= 0:
            self._pipeline_batch_size = 0
            self._pipeline = None
            return False
        if self._pipeline is None:
            rc = self._get_redis_client()
            if not rc:
                return False
            try:
                self._pipeline = rc.pipeline(transaction=False)
                self._pipeline_buffer = 0
                self._pipeline_batch_size = cfg_batch
                self._pipeline_first_ts = None
            except Exception as e:
                logger.warning(f"MikroTik cache: gagal init pipeline: {e}")
                self._pipeline = None
                self._pipeline_batch_size = 0
                return False
        return True

    def _pipeline_add(self, fn):
        # fn adalah callable yang akan menambahkan operasi ke pipeline
        if not self._maybe_init_pipeline():
            # fallback: jalankan langsung
            try:
                fn(None)
            except Exception:
                pass
            return
        try:
            fn(self._pipeline)
            self._pipeline_buffer += 1
            now_ms = __import__('time').time() * 1000
            if self._pipeline_first_ts is None:
                self._pipeline_first_ts = now_ms
            # Flush conditions: buffer >= batch size or time window exceeded
            if self._pipeline_buffer >= self._pipeline_batch_size or (self._pipeline_first_ts is not None and (now_ms - self._pipeline_first_ts) >= self._pipeline_flush_interval_ms):
                self._flush_pipeline()
        except Exception as e:
            logger.debug(f"MikroTik cache: pipeline add fallback (error {e}), executing directly")
            try:
                fn(None)
            except Exception:
                pass

    def _flush_pipeline(self):
        if not self._pipeline:
            return
        try:
            self._pipeline.execute()
        except Exception as e:
            logger.debug(f"MikroTik cache: pipeline execute error {e}")
        finally:
            self._pipeline = None
            self._pipeline_buffer = 0
            self._pipeline_first_ts = None
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        # Compressed namespace: mtc:<abbr>:<id>
        return f"mtc:{prefix}:{identifier}"
    
    def get_mac_by_ip(self, ip_address: str) -> Optional[Tuple[bool, Optional[str], str]]:
        """Get cached MAC lookup result"""
        if not ip_address:
            return None
            
        redis_client = self._get_redis_client()
        if not redis_client:
            return None
            
        try:
            cache_key = self._get_cache_key("mbi", ip_address)
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                result = json.loads(cached_data)
                logger.debug(f"MikroTik cache HIT: MAC lookup for IP {ip_address}")
                return (result['success'], result.get('mac'), result['message'])
            
            logger.debug(f"MikroTik cache MISS: MAC lookup for IP {ip_address}")
            return None
            
        except Exception as e:
            logger.warning(f"MikroTik cache get error: {e}")
            return None
    
    def set_mac_by_ip(self, ip_address: str, success: bool, mac: Optional[str], message: str, ttl: Optional[int] = None):
        """Cache MAC lookup result"""
        if not ip_address:
            return
            
        redis_client = self._get_redis_client()
        if not redis_client:
            return
            
        try:
            cache_key = self._get_cache_key("mbi", ip_address)
            cache_data = {
                'success': success,
                'mac': mac,
                'message': message,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            cache_ttl = ttl or self.cache_ttl
            def _op(p):
                target = p if p is not None else redis_client
                target.setex(cache_key, cache_ttl, json.dumps(cache_data))
            self._pipeline_add(_op)
            
            logger.debug(f"MikroTik cache SET: MAC lookup for IP {ip_address} (TTL: {cache_ttl}s)")
            
        except Exception as e:
            logger.warning(f"MikroTik cache set error: {e}")
    
    def get_host_details(self, identifier: str, lookup_type: str = "ip") -> Optional[Dict[str, Any]]:
        """Get cached host details"""
        if not identifier:
            return None
            
        redis_client = self._get_redis_client()
        if not redis_client:
            return None
            
        try:
            cache_key = self._get_cache_key(f"host_details_{lookup_type}", identifier)
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                result = json.loads(cached_data)
                logger.debug(f"MikroTik cache HIT: Host details for {lookup_type} {identifier}")
                return result
            
            logger.debug(f"MikroTik cache MISS: Host details for {lookup_type} {identifier}")
            return None
            
        except Exception as e:
            logger.warning(f"MikroTik cache get error: {e}")
            return None
    
    def set_host_details(self, identifier: str, data: Dict[str, Any], lookup_type: str = "ip", ttl: Optional[int] = None):
        """Cache host details"""
        if not identifier or not data:
            return
            
        redis_client = self._get_redis_client()
        if not redis_client:
            return
            
        try:
            cache_key = self._get_cache_key(f"host_details_{lookup_type}", identifier)
            cache_data = {
                **data,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            cache_ttl = ttl or self.cache_ttl
            def _op(p):
                target = p if p is not None else redis_client
                target.setex(cache_key, cache_ttl, json.dumps(cache_data))
            self._pipeline_add(_op)
            
            logger.debug(f"MikroTik cache SET: Host details for {lookup_type} {identifier} (TTL: {cache_ttl}s)")
            
        except Exception as e:
            logger.warning(f"MikroTik cache set error: {e}")
    
    def invalidate_ip(self, ip_address: str):
        """Invalidate all cache entries for an IP"""
        if not ip_address:
            return
            
        redis_client = self._get_redis_client()
        if not redis_client:
            return
            
        try:
            # Direct key invalidation
            keys_to_delete = [
                self._get_cache_key("mbi", ip_address),
                self._get_cache_key("hdi", ip_address),
                self._get_cache_key("host_details_ip", ip_address),
            ]
            
            # Also check for new format client_info cache pattern
            pattern_keys = redis_client.keys(f"client_info:{ip_address}:*")
            if pattern_keys:
                keys_to_delete.extend(pattern_keys)
                
            # Delete all keys
            if keys_to_delete:
                redis_client.delete(*keys_to_delete)
            
            # Also try to purge any ARP cache entries (used by warming system)
            try:
                arp_keys = redis_client.keys(f"arp:*:{ip_address}")
                if arp_keys:
                    redis_client.delete(*arp_keys)
                    logger.debug(f"MikroTik cache INVALIDATED: {len(arp_keys)} ARP entries for IP {ip_address}")
            except Exception as e_arp:
                logger.debug(f"ARP cache invalidation error (non-critical): {e_arp}")
            
            logger.info(f"MikroTik cache INVALIDATED: All entries for IP {ip_address}")
            
        except Exception as e:
            logger.warning(f"MikroTik cache invalidate error: {e}")
    
    def clear_all(self):
        """Clear all MikroTik cache entries"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return
            
        try:
            pattern = "mikrotik_cache:*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
                logger.info(f"MikroTik cache CLEARED: {len(keys)} entries removed")
            else:
                logger.debug("MikroTik cache CLEAR: No entries to remove")
                
        except Exception as e:
            logger.warning(f"MikroTik cache clear error: {e}")

# Global cache instance
mikrotik_cache = MikroTikCache()

def get_cached_mac_by_ip(ip_address: str) -> Optional[Tuple[bool, Optional[str], str]]:
    """Convenience function to get cached MAC by IP"""
    return mikrotik_cache.get_mac_by_ip(ip_address)

def cache_mac_by_ip(ip_address: str, success: bool, mac: Optional[str], message: str, ttl: Optional[int] = None):
    """Convenience function to cache MAC by IP"""
    mikrotik_cache.set_mac_by_ip(ip_address, success, mac, message, ttl)

def invalidate_ip_cache(ip_address: str):
    """Convenience function to invalidate IP cache"""
    mikrotik_cache.invalidate_ip(ip_address)
