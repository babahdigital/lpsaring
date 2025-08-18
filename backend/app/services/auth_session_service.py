# backend/app/services/auth_session_service.py
"""
Enhanced Session Service dengan Redis State Management
Menggantikan global variables dengan Redis-based session tracking
"""

import time
import logging
import json
import hashlib
from typing import Optional, Dict, Any, List
from flask import current_app

logger = logging.getLogger(__name__)

class AuthSessionService:
    """Layanan session dengan Redis-based state management"""
    
    @staticmethod
    def _get_redis_client():
        """Get Redis client safely"""
        try:
            return getattr(current_app, 'redis_client_otp', None)
        except RuntimeError:
            return None
    
    @staticmethod
    def _generate_session_key(client_ip: str, client_mac: Optional[str] = None) -> str:
        """Generate unique session key"""
        key_data = f"{client_ip}:{client_mac or 'no-mac'}"
        hash_suffix = hashlib.md5(key_data.encode()).hexdigest()[:8]
        return f"auth_session:{client_ip}:{hash_suffix}"
    
    @staticmethod
    def create_session(
        client_ip: str,
        client_mac: Optional[str] = None,
        user_id: Optional[int] = None,
        session_type: str = "auth",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Buat session baru dengan state management
        """
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            logger.warning("[SESSION] Redis not available for session creation")
            return {"success": False, "message": "Session service unavailable"}
        
        try:
            session_key = AuthSessionService._generate_session_key(client_ip, client_mac)
            current_time = time.time()
            
            session_data = {
                "session_id": session_key,
                "client_ip": client_ip,
                "client_mac": client_mac,
                "user_id": user_id,
                "session_type": session_type,
                "created_at": current_time,
                "updated_at": current_time,
                "status": "active",
                "metadata": metadata or {},
                "activities": []
            }
            
            # Store session with 1 hour TTL
            redis_client.setex(session_key, 3600, json.dumps(session_data))
            
            logger.info(f"[SESSION] Created session {session_key} for IP {client_ip}")
            return {"success": True, "session_key": session_key, "session_data": session_data}
            
        except Exception as e:
            logger.error(f"[SESSION] Error creating session: {e}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def get_session(client_ip: str, client_mac: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve session data"""
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return None
        
        try:
            session_key = AuthSessionService._generate_session_key(client_ip, client_mac)
            session_raw = redis_client.get(session_key)
            
            if session_raw:
                session_data = json.loads(session_raw)
                # Update last accessed
                session_data["last_accessed"] = time.time()
                redis_client.setex(session_key, 3600, json.dumps(session_data))
                
                logger.debug(f"[SESSION] Retrieved session {session_key}")
                return session_data
            
            return None
            
        except Exception as e:
            logger.error(f"[SESSION] Error retrieving session: {e}")
            return None
    
    @staticmethod
    def update_session(
        client_ip: str,
        client_mac: Optional[str] = None,
        updates: Optional[Dict] = None,
        activity: Optional[str] = None
    ) -> bool:
        """Update session with new data or activity"""
        session_data = AuthSessionService.get_session(client_ip, client_mac)
        if not session_data:
            return False
        
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return False
        
        try:
            # Apply updates
            if updates:
                session_data.update(updates)
            
            # Add activity log
            if activity:
                session_data["activities"].append({
                    "timestamp": time.time(),
                    "activity": activity
                })
                # Keep only last 10 activities
                session_data["activities"] = session_data["activities"][-10:]
            
            session_data["updated_at"] = time.time()
            
            session_key = AuthSessionService._generate_session_key(client_ip, client_mac)
            redis_client.setex(session_key, 3600, json.dumps(session_data))
            
            logger.debug(f"[SESSION] Updated session {session_key}")
            return True
            
        except Exception as e:
            logger.error(f"[SESSION] Error updating session: {e}")
            return False
    
    @staticmethod
    def track_consecutive_failures(
        client_ip: str,
        action: str,
        failure_reason: str = "unknown",
        max_failures: int = 5
    ) -> Dict[str, Any]:
        """
        Track consecutive failures dengan Redis
        Menggantikan global failure_counters
        """
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return {"consecutive_failures": 0, "should_block": False}
        
        try:
            failure_key = f"auth_failures:{client_ip}:{action}"
            current_time = time.time()
            
            # Get current failures
            failure_data_raw = redis_client.get(failure_key)
            if failure_data_raw:
                failure_data = json.loads(failure_data_raw)
            else:
                failure_data = {
                    "count": 0,
                    "first_failure": current_time,
                    "last_failure": None,
                    "reasons": []
                }
            
            # Increment failure count
            failure_data["count"] += 1
            failure_data["last_failure"] = current_time
            failure_data["reasons"].append({
                "timestamp": current_time,
                "reason": failure_reason
            })
            
            # Keep only last 10 reasons
            failure_data["reasons"] = failure_data["reasons"][-10:]
            
            # Store with 10 minute expiry
            redis_client.setex(failure_key, 600, json.dumps(failure_data))
            
            should_block = failure_data["count"] >= max_failures
            
            logger.warning(f"[SESSION] Failure #{failure_data['count']} for {client_ip}:{action} - {failure_reason}")
            
            return {
                "consecutive_failures": failure_data["count"],
                "should_block": should_block,
                "first_failure": failure_data["first_failure"],
                "last_failure": failure_data["last_failure"],
                "time_since_first": current_time - failure_data["first_failure"]
            }
            
        except Exception as e:
            logger.error(f"[SESSION] Error tracking failures: {e}")
            return {"consecutive_failures": 0, "should_block": False}
    
    @staticmethod
    def reset_failure_counter(client_ip: str, action: str) -> bool:
        """Reset failure counter after successful operation"""
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return False
        
        try:
            failure_key = f"auth_failures:{client_ip}:{action}"
            deleted = redis_client.delete(failure_key)
            
            if deleted:
                logger.info(f"[SESSION] Reset failure counter for {client_ip}:{action}")
            
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"[SESSION] Error resetting failure counter: {e}")
            return False
    
    @staticmethod
    def destroy_session(client_ip: str, client_mac: Optional[str] = None) -> bool:
        """Destroy session and cleanup related data"""
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return False
        
        try:
            session_key = AuthSessionService._generate_session_key(client_ip, client_mac)
            
            # Delete session
            deleted = redis_client.delete(session_key)
            
            # Cleanup related data
            patterns_to_clean = [
                f"auth_failures:{client_ip}:*",
                f"client_info:{client_ip}:*",
                f"rate_limit:{client_ip}:*"
            ]
            
            total_cleaned = 0
            for pattern in patterns_to_clean:
                keys = redis_client.keys(pattern)
                if keys:
                    cleaned = redis_client.delete(*keys)
                    total_cleaned += cleaned
            
            logger.info(f"[SESSION] Destroyed session {session_key}, cleaned {total_cleaned} related keys")
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"[SESSION] Error destroying session: {e}")
            return False
    
    @staticmethod
    def get_session_stats(client_ip: Optional[str] = None) -> Dict[str, Any]:
        """Get session statistics for monitoring"""
        redis_client = AuthSessionService._get_redis_client()
        if not redis_client:
            return {"error": "Redis not available"}
        
        try:
            stats = {}
            
            if client_ip:
                # Stats for specific IP
                session_key = AuthSessionService._generate_session_key(client_ip)
                session_data = AuthSessionService.get_session(client_ip)
                
                failure_keys = redis_client.keys(f"auth_failures:{client_ip}:*")
                
                stats = {
                    "client_ip": client_ip,
                    "has_active_session": bool(session_data),
                    "session_data": session_data,
                    "failure_trackers": len(failure_keys),
                    "timestamp": time.time()
                }
            else:
                # Global stats
                all_sessions = redis_client.keys("auth_session:*")
                all_failures = redis_client.keys("auth_failures:*")
                
                stats = {
                    "total_active_sessions": len(all_sessions),
                    "total_failure_trackers": len(all_failures),
                    "timestamp": time.time()
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"[SESSION] Error getting session stats: {e}")
            return {"error": str(e)}
