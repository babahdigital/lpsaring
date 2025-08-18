# backend/app/tasks/auth_optimization_tasks.py
"""
Celery Tasks untuk Auth Optimization
Menggunakan service-based architecture yang harmonis dengan struktur yang ada
"""

import time
import logging
from typing import Dict, Any, Optional
from celery import Task

from app.extensions import celery_app as celery
from app.services.client_detection_service import ClientDetectionService
from app.services.auth_session_service import AuthSessionService
from flask import current_app

# MikroTik helpers (lazy import inside tasks to avoid import cycles at module load time)
try:  # pragma: no cover - best effort import
    from app.infrastructure.gateways.mikrotik_client import (
        remove_ip_from_address_list,
        find_and_remove_static_lease_by_mac,
    )
except Exception:  # pragma: no cover
    remove_ip_from_address_list = None  # type: ignore
    find_and_remove_static_lease_by_mac = None  # type: ignore

logger = logging.getLogger(__name__)

@celery.task(bind=True, name='auth.cleanup_expired_sessions')
def cleanup_expired_sessions(self: Task) -> Dict[str, Any]:
    """
    Celery task untuk membersihkan session yang expired
    """
    try:
        # Buat Flask app context untuk Celery
        with current_app.app_context():
            redis_client = getattr(current_app, 'redis_client_otp', None)
            if not redis_client:
                return {"status": "ERROR", "message": "Redis not available"}
            
            current_time = time.time()
            cleanup_stats = {
                "sessions_checked": 0,
                "sessions_cleaned": 0,
                "failures_cleaned": 0,
                "cache_cleaned": 0
            }
            
            # 1. Clean expired auth sessions
            session_keys = redis_client.keys("auth_session:*")
            for session_key in session_keys:
                try:
                    session_data_raw = redis_client.get(session_key)
                    if session_data_raw:
                        import json
                        session_data = json.loads(session_data_raw)
                        
                        # Check if session is older than 1 hour
                        created_at = session_data.get('created_at', 0)
                        if current_time - created_at > 3600:  # 1 hour
                            redis_client.delete(session_key)
                            cleanup_stats["sessions_cleaned"] += 1
                        
                        cleanup_stats["sessions_checked"] += 1
                except Exception as e:
                    logger.warning(f"[CLEANUP] Error processing session {session_key}: {e}")
            
            # 2. Clean expired failure counters (older than 10 minutes)
            failure_keys = redis_client.keys("auth_failures:*")
            for failure_key in failure_keys:
                try:
                    ttl = redis_client.ttl(failure_key)
                    if ttl == -1:  # No TTL set, delete
                        redis_client.delete(failure_key)
                        cleanup_stats["failures_cleaned"] += 1
                except Exception as e:
                    logger.warning(f"[CLEANUP] Error processing failure key {failure_key}: {e}")
            
            # 3. Clean old detection cache (older than 1 minute)
            cache_keys = redis_client.keys("client_info:*")
            for cache_key in cache_keys:
                try:
                    ttl = redis_client.ttl(cache_key)
                    if ttl == -1 or ttl > 60:  # No TTL or too long
                        redis_client.delete(cache_key)
                        cleanup_stats["cache_cleaned"] += 1
                except Exception as e:
                    logger.warning(f"[CLEANUP] Error processing cache key {cache_key}: {e}")
            
            logger.info(f"[CLEANUP] Session cleanup completed: {cleanup_stats}")
            
            return {
                "status": "SUCCESS",
                "cleanup_stats": cleanup_stats,
                "timestamp": current_time
            }
            
    except Exception as e:
        logger.error(f"[CLEANUP] Task failed: {e}")
        return {
            "status": "ERROR",
            "message": str(e),
            "timestamp": time.time()
        }

@celery.task(bind=True, name='auth.cleanup_mikrotik_on_token_expiry')
def cleanup_mikrotik_on_token_expiry(self: Task, client_ip: Optional[str], client_mac: Optional[str], list_name: Optional[str], comment: Optional[str], jti: Optional[str] = None) -> Dict[str, Any]:
    """
    Cleanup MikroTik artifacts (address-list + static lease) when a token expires.
    Best-effort and idempotent. Skips if an active-session key still exists for the IP.
    """
    try:
        with current_app.app_context():
            r = getattr(current_app, 'redis_client_otp', None)
            results: Dict[str, Any] = {"removed": {}, "skipped": False}

            # If there's an active session marker for this IP, skip cleanup
            if client_ip and r:
                active_key = f"auth:active:{client_ip}"
                if r.get(active_key):
                    results["skipped"] = True
                    results["reason"] = "active_session_present"
                    logger.info(f"[JWT-CLEANUP] Skip cleanup for {client_ip}: active session present")
                    return {"status": "SKIPPED", **results}

            # Idempotency lock per jti or ip
            lock_key = f"jwt_cleanup_lock:{jti or client_ip or 'unknown'}"
            have_lock = True
            if r:
                try:
                    # NX with short TTL to avoid duplicate concurrent cleanups
                    have_lock = r.set(lock_key, '1', nx=True, ex=600) or False
                except Exception:
                    have_lock = True  # proceed anyway

            if not have_lock:
                return {"status": "SKIPPED", "reason": "lock_exists"}

            # Remove from address list
            if list_name and client_ip and remove_ip_from_address_list:
                try:
                    ok, msg = remove_ip_from_address_list(list_name, client_ip)
                    results["removed"]["address_list"] = {"ok": ok, "msg": msg}
                    if ok:
                        logger.info(f"[JWT-CLEANUP] Removed {client_ip} from list {list_name}: {msg}")
                    else:
                        logger.warning(f"[JWT-CLEANUP] Failed removing {client_ip} from {list_name}: {msg}")
                except Exception as e:
                    results["removed"]["address_list_error"] = str(e)
                    logger.warning(f"[JWT-CLEANUP] Address list cleanup error: {e}")

            # Remove static lease by MAC
            if client_mac and find_and_remove_static_lease_by_mac:
                try:
                    ok, msg = find_and_remove_static_lease_by_mac(client_mac)
                    results["removed"]["dhcp_lease"] = {"ok": ok, "msg": msg}
                    if ok:
                        logger.info(f"[JWT-CLEANUP] Removed static lease for {client_mac}: {msg}")
                    else:
                        logger.warning(f"[JWT-CLEANUP] Failed removing lease for {client_mac}: {msg}")
                except Exception as e:
                    results["removed"]["dhcp_lease_error"] = str(e)
                    logger.warning(f"[JWT-CLEANUP] DHCP lease cleanup error: {e}")

            return {"status": "SUCCESS", **results}

    except Exception as e:
        logger.error(f"[JWT-CLEANUP] Task failed: {e}")
        return {"status": "ERROR", "message": str(e)}


def schedule_token_cleanup(client_ip: Optional[str], client_mac: Optional[str], comment: Optional[str], list_name: Optional[str], ttl_seconds: int, jti: Optional[str] = None) -> bool:
    """Schedule a one-shot cleanup task for when a token expires."""
    try:
        delay = max(int(ttl_seconds), 1)
        cleanup_mikrotik_on_token_expiry.apply_async(args=[client_ip, client_mac, list_name, comment, jti], countdown=delay + 1)
        logger.info(f"[JWT-CLEANUP] Scheduled cleanup for {client_ip}/{client_mac} in {delay}s")
        # Also mark active session for this IP for that TTL
        r = getattr(current_app, 'redis_client_otp', None)
        if r and client_ip:
            r.setex(f"auth:active:{client_ip}", delay + 60, '1')
        return True
    except Exception as e:  # pragma: no cover
        logger.warning(f"[JWT-CLEANUP] Failed to schedule cleanup: {e}")
        return False

@celery.task(bind=True, name='auth.refresh_client_detection')
def refresh_client_detection(self: Task, client_ip: str, client_mac: Optional[str] = None) -> Dict[str, Any]:
    """
    Celery task untuk refresh client detection secara asynchronous
    """
    try:
        from flask import current_app
        
        with current_app.app_context():
            logger.info(f"[REFRESH-DETECTION] Starting for IP: {client_ip}, MAC: {client_mac}")
            
            # Clear existing cache
            ClientDetectionService.clear_cache(client_ip, client_mac)
            
            # Force fresh detection
            detection_result = ClientDetectionService.get_client_info(
                frontend_ip=client_ip,
                frontend_mac=client_mac,
                force_refresh=True,
                use_cache=True  # Cache hasil baru
            )
            
            # Update session if detection successful
            if detection_result.get('ip_detected') and detection_result.get('mac_detected'):
                AuthSessionService.update_session(
                    client_ip=detection_result['detected_ip'],
                    client_mac=detection_result['detected_mac'],
                    activity="background_detection_refresh"
                )
            
            logger.info(f"[REFRESH-DETECTION] Completed for {client_ip}: {detection_result['status']}")
            
            return {
                "status": "SUCCESS",
                "detection_result": detection_result,
                "refreshed_at": time.time()
            }
            
    except Exception as e:
        logger.error(f"[REFRESH-DETECTION] Task failed: {e}")
        return {
            "status": "ERROR",
            "message": str(e),
            "timestamp": time.time()
        }

@celery.task(bind=True, name='auth.monitor_auth_performance')
def monitor_auth_performance(self: Task) -> Dict[str, Any]:
    """
    Celery task untuk monitoring performa auth system
    """
    try:
        from flask import current_app
        
        with current_app.app_context():
            redis_client = getattr(current_app, 'redis_client_otp', None)
            if not redis_client:
                return {"status": "ERROR", "message": "Redis not available"}
            
            current_time = time.time()
            
            # Collect performance metrics
            metrics = {
                "active_sessions": len(redis_client.keys("auth_session:*")),
                "failure_trackers": len(redis_client.keys("auth_failures:*")),
                "detection_cache_entries": len(redis_client.keys("client_info:*")),
                "force_refresh_flags": len(redis_client.keys("force_refresh:*")),
                "mikrotik_cache_entries": len(redis_client.keys("mikrotik_cache:*")),
                "timestamp": current_time
            }
            
            # Analyze failure patterns
            failure_analysis = {
                "high_failure_ips": [],
                "common_failure_reasons": {}
            }
            
            failure_keys = redis_client.keys("auth_failures:*:*")
            for failure_key in failure_keys:
                try:
                    failure_data_raw = redis_client.get(failure_key)
                    if failure_data_raw:
                        import json
                        failure_data = json.loads(failure_data_raw)
                        
                        # Extract IP from key
                        key_parts = failure_key.decode().split(":")
                        if len(key_parts) >= 3:
                            ip = key_parts[2]
                            failure_count = failure_data.get("count", 0)
                            
                            if failure_count >= 3:
                                failure_analysis["high_failure_ips"].append({
                                    "ip": ip,
                                    "failures": failure_count,
                                    "action": key_parts[3] if len(key_parts) > 3 else "unknown"
                                })
                            
                            # Count failure reasons
                            for reason_entry in failure_data.get("reasons", []):
                                reason = reason_entry.get("reason", "unknown")
                                failure_analysis["common_failure_reasons"][reason] = \
                                    failure_analysis["common_failure_reasons"].get(reason, 0) + 1
                                    
                except Exception as e:
                    logger.warning(f"[MONITOR] Error analyzing failure key {failure_key}: {e}")
            
            # Store metrics for trending
            metrics_key = f"auth_metrics:{int(current_time/300)}"  # 5-minute buckets
            redis_client.setex(metrics_key, 1800, json.dumps(metrics))  # Store for 30 minutes
            
            result = {
                "status": "SUCCESS",
                "metrics": metrics,
                "failure_analysis": failure_analysis,
                "monitored_at": current_time
            }
            
            # Log warnings for high failure rates
            if len(failure_analysis["high_failure_ips"]) > 0:
                logger.warning(f"[MONITOR] High failure IPs detected: {failure_analysis['high_failure_ips']}")
            
            return result
            
    except Exception as e:
        logger.error(f"[MONITOR] Task failed: {e}")
        return {
            "status": "ERROR", 
            "message": str(e),
            "timestamp": time.time()
        }

@celery.task(bind=True, name='auth.sync_device_background')
def sync_device_background(self: Task, client_ip: str, client_mac: Optional[str] = None) -> Dict[str, Any]:
    """
    Background device sync untuk menghindari blocking UI
    """
    try:
        from flask import current_app
        
        with current_app.app_context():
            logger.info(f"[BG-SYNC] Starting background sync for {client_ip}:{client_mac}")
            
            # Import models di dalam task untuk menghindari circular import
            from app.infrastructure.db.models import User, UserDevice
            from app.extensions import db
            from sqlalchemy import select
            
            try:
                # Cari device
                device = None
                user = None
                
                if client_mac:
                    device = db.session.execute(
                        select(UserDevice).filter_by(mac_address=client_mac)
                    ).scalar_one_or_none()
                    if device:
                        user = device.user
                
                if not device and client_ip:
                    user = db.session.execute(
                        select(User).filter_by(last_login_ip=client_ip)
                    ).scalar_one_or_none()
                
                sync_result = {
                    "device_found": bool(device),
                    "user_found": bool(user),
                    "sync_timestamp": time.time()
                }
                
                if device and user:
                    sync_result.update({
                        "user_id": str(user.id),
                        "device_id": str(device.id),
                        "user_name": user.full_name,
                        "device_name": device.device_name
                    })
                    
                    # Update session dengan hasil sync
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={
                            "background_sync": True,
                            "sync_result": sync_result
                        },
                        activity=f"background_sync_completed:user_{user.id}"
                    )
                    
                    logger.info(f"[BG-SYNC] Successfully synced device {device.id} for user {user.id}")
                else:
                    # Update session dengan info tidak ditemukan
                    AuthSessionService.update_session(
                        client_ip=client_ip,
                        client_mac=client_mac,
                        updates={
                            "background_sync": True,
                            "sync_result": sync_result
                        },
                        activity="background_sync_not_found"
                    )
                    
                    logger.info(f"[BG-SYNC] Device not found for {client_ip}:{client_mac}")
                
                return {
                    "status": "SUCCESS",
                    "sync_result": sync_result
                }
                
            except Exception as task_error:
                logger.error(f"[BG-SYNC] Task database error: {task_error}")
                db.session.rollback()
                raise
                
    except Exception as e:
        logger.error(f"[BG-SYNC] Task failed: {e}")
        
        # Update session dengan error info
        try:
            AuthSessionService.update_session(
                client_ip=client_ip,
                client_mac=client_mac,
                updates={
                    "background_sync": True,
                    "sync_error": str(e)
                },
                activity=f"background_sync_error:{str(e)[:50]}"
            )
        except:
            pass  # Jangan biarkan error session mengganggu task
        
        return {
            "status": "ERROR",
            "message": str(e),
            "timestamp": time.time()
        }

# Task scheduler helpers (untuk integrasi dengan scheduler yang ada)
def schedule_auth_maintenance():
    """
    Helper function untuk menjadwalkan maintenance tasks
    Bisa dipanggil dari scheduler yang sudah ada
    """
    try:
        # Schedule cleanup setiap 30 menit
        cleanup_expired_sessions.apply_async(countdown=1800)  
        
        # Schedule monitoring setiap 5 menit
        monitor_auth_performance.apply_async(countdown=300)
        
        logger.info("[SCHEDULER] Auth maintenance tasks scheduled")
        return True
        
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to schedule auth maintenance: {e}")
        return False

def trigger_background_sync(client_ip: str, client_mac: Optional[str] = None):
    """
    Helper function untuk trigger background sync
    Bisa dipanggil dari auth routes tanpa blocking
    """
    try:
        sync_device_background.apply_async(
            args=[client_ip, client_mac],
            countdown=1  # Delay 1 detik
        )
        
        logger.info(f"[TRIGGER] Background sync triggered for {client_ip}:{client_mac}")
        return True
        
    except Exception as e:
        logger.error(f"[TRIGGER] Failed to trigger background sync: {e}")
        return False
