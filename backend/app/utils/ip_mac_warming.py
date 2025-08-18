# backend/app/utils/ip_mac_warming.py
"""
ARP Warming Utility - Proactive system untuk menjaga ARP table fresh
Version: 2.0 - Enhanced Performance & Reliability
"""
import logging
import time
import threading
import ipaddress
from typing import List, Dict, Set, Optional, Tuple, Any
import schedule  # type: ignore # pylance-disable
from datetime import datetime
import json

from flask import current_app
from app.infrastructure.gateways import mikrotik_client
# Import the enhancement functions directly
from app.infrastructure.gateways.mikrotik_client_enhancement import (
    ping_ip_with_options,
    get_active_ip_addresses
)
from app.utils.cache_manager import cache_manager

logger = logging.getLogger(__name__)

# Track IPs that we're actively warming - with enhanced status tracking
_active_warming_ips: Set[str] = set()
_recent_clients: Dict[str, Dict] = {}
_warming_thread = None
_stop_thread = False
_scheduler = schedule.Scheduler()  # Create a dedicated scheduler instance
_thread_lock = threading.RLock()  # Thread safety lock for shared resources

# System status tracking
_system_status = {
    "enabled": False,
    "thread_running": False,
    "last_run_time": None,
    "last_run_duration": 0,
    "total_runs": 0,
    "successful_runs": 0,
    "errors": 0,
    "warmed_ips_count": 0,
    "successful_warmings": 0,
    "failed_warmings": 0,
    "discovered_macs": 0,
    "last_error": None
}

def is_valid_ip(ip: str) -> bool:
    """
    Check if an IP is valid and is a private address
    
    Args:
        ip: IP address string to validate
        
    Returns:
        bool: True if IP is valid and private, False otherwise
    """
    if not ip or not isinstance(ip, str):
        return False
        
    # Remove any whitespace
    ip = ip.strip()
    
    try:
        parsed = ipaddress.ip_address(ip)
        
        # Check for common invalid IPs
        if str(parsed) in ['0.0.0.0', '127.0.0.1']:
            return False
            
        # Verify it's a private address (RFC1918) or link local
        return parsed.is_private and not parsed.is_loopback
    except (ValueError, TypeError):
        return False

def warm_ip(ip_address: str, aggressive: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Melakukan warming pada sebuah IP address untuk memastikan ada di ARP table
    
    Args:
        ip_address: IP untuk warming
        aggressive: Jika True, gunakan multiple ping ukuran untuk memaksimalkan respons
        
    Returns:
        (success, mac_address) - True jika warming berhasil, MAC jika ditemukan
    """
    global _system_status
    
    if not ip_address:
        return False, None
        
    start_time = time.time()
    
    if not is_valid_ip(ip_address):
        logger.debug(f"[ARP-WARMING] Invalid IP format: {ip_address}")
        return False, None
        
    logger.debug(f"[ARP-WARMING] Warming IP {ip_address} {'(aggressive)' if aggressive else ''}")
    
    try:
        # Use thread lock to safely update shared data
        with _thread_lock:
            # Track that we're warming this IP
            _active_warming_ips.add(ip_address)
        
        # Use different ping strategies based on device types
        # Small pings for mobile devices, larger for PCs
        ping_sizes = [56, 1024, 1472] if aggressive else [56, 512]
        ping_count = 2 if aggressive else 1
        
        # Perform the warming ping (without timeout parameter which isn't supported)
        ping_success = ping_ip_with_options(
            ip_address, 
            sizes=ping_sizes,
            count=ping_count
        )
        
        if not ping_success:
            logger.debug(f"[ARP-WARMING] Ping failed for {ip_address}")
            with _thread_lock:
                _system_status["failed_warmings"] += 1
            return False, None
            
        # Check if MAC is now in ARP table - faster detection for warming
        success, mac_address, source = mikrotik_client.find_mac_by_ip_comprehensive(ip_address, force_refresh=True)
        
        # Update statistics safely
        with _thread_lock:
            _system_status["warmed_ips_count"] += 1
            
            if success and mac_address:
                _system_status["successful_warmings"] += 1
                _system_status["discovered_macs"] += 1
                
                # Store in recent clients with enhanced data
                _recent_clients[ip_address] = {
                    'mac': mac_address,
                    'last_seen': time.time(),
                    'last_seen_formatted': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'source': source,
                    'warming_count': _recent_clients.get(ip_address, {}).get('warming_count', 0) + 1,
                    'warming_duration': round((time.time() - start_time) * 1000, 2)
                }
                
                logger.info(f"[ARP-WARMING] ✅ Successfully warmed {ip_address} → {mac_address} via {source}")
                return True, mac_address
            else:
                logger.debug(f"[ARP-WARMING] No MAC found for {ip_address} after warming")
                return ping_success, None
            
    except Exception as e:
        with _thread_lock:
            _system_status["errors"] += 1
            _system_status["last_error"] = str(e)
            _system_status["failed_warmings"] += 1
            
        logger.error(f"[ARP-WARMING] Error warming {ip_address}: {e}")
        return False, None
    finally:
        # Always clean up the tracking set
        with _thread_lock:
            _active_warming_ips.discard(ip_address)

def warm_multiple_ips(ip_addresses: List[str], aggressive: bool = False, 
                    max_concurrent: int = 10, batch_delay: float = 0.1) -> Dict[str, Tuple[bool, Optional[str]]]:
    """
    Warm multiple IP addresses and return results
    
    Args:
        ip_addresses: List of IP addresses to warm
        aggressive: If True, use aggressive warming mode
        max_concurrent: Maximum number of IPs to warm at once
        batch_delay: Delay between processing batches (seconds)
        
    Returns:
        Dictionary of results mapping IP to (success, mac_address)
    """
    results = {}
    valid_ips = []
    
    # First filter IPs that are already warming and invalid IPs
    for ip in ip_addresses:
        if not ip or ip in _active_warming_ips or not is_valid_ip(ip):
            continue  # Skip invalid IPs or those already being warmed
        valid_ips.append(ip)
        
    # Process in batches to avoid overwhelming the network or router
    logger.debug(f"[ARP-WARMING] Processing {len(valid_ips)} valid IPs in batches of {max_concurrent}")
    
    for i in range(0, len(valid_ips), max_concurrent):
        batch = valid_ips[i:i+max_concurrent]
        batch_results = {}
        
        # Process the batch
        for ip in batch:
            batch_results[ip] = warm_ip(ip, aggressive)
            
        # Update main results
        results.update(batch_results)
        
        # Add small delay between batches
        if i + max_concurrent < len(valid_ips):
            time.sleep(batch_delay)
            
    return results

def perform_periodic_warming():
    """
    Perform periodic ARP table warming based on active IPs and recent clients
    """
    global _system_status
    
    logger.debug("[ARP-WARMING] Starting periodic warming cycle")
    start_time = time.time()
    
    try:
        with _thread_lock:
            _system_status["total_runs"] += 1
            _system_status["last_run_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get active IPs from MikroTik
        active_ips = get_active_ip_addresses()
        
        # Get recently accessed IPs from cache with higher limit
        recent_ips_from_cache = cache_manager.get_recently_accessed_ips(max_count=100)
        
        # Get recently active login sessions
        recently_active_sessions = []
        try:
            from flask import current_app
            db = current_app.extensions['sqlalchemy'].db
            # Get recent session IPs from the database directly
            if db:
                query = "SELECT DISTINCT client_ip FROM hotspot_sessions WHERE created_at > NOW() - INTERVAL '2 HOUR' LIMIT 50"
                result = db.session.execute(query)
                recently_active_sessions = [row[0] for row in result if row[0]]
        except Exception as import_err:
            logger.debug(f"[ARP-WARMING] Could not query sessions: {import_err}")
        
        # Combine sources with priority
        all_ips = set(active_ips) | set(recent_ips_from_cache) | set(_recent_clients.keys()) | set(recently_active_sessions)
        
        # Filter to just valid private IPs
        valid_ips = [ip for ip in all_ips if is_valid_ip(ip)]
        
        if valid_ips:
            # Log with appropriate level based on count
            if len(valid_ips) > 20:
                logger.info(f"[ARP-WARMING] Warming {len(valid_ips)} IPs in batches")
            else:
                logger.debug(f"[ARP-WARMING] Warming {len(valid_ips)} IPs")
                
            # Use more aggressive warming for active sessions
            aggressive_ips = set(active_ips) | set(recently_active_sessions)
            
            # Warm IPs in two groups: aggressive for active users, standard for others
            standard_ips = [ip for ip in valid_ips if ip not in aggressive_ips]
            
            # Process aggressive IPs first (active users)
            if aggressive_ips:
                aggressive_results = warm_multiple_ips([ip for ip in aggressive_ips if is_valid_ip(ip)], aggressive=True)
                logger.debug(f"[ARP-WARMING] Completed aggressive warming for {len(aggressive_results)} active IPs")
            
            # Then process standard IPs
            if standard_ips:
                standard_results = warm_multiple_ips(standard_ips, aggressive=False)
                logger.debug(f"[ARP-WARMING] Completed standard warming for {len(standard_results)} other IPs")
                
            # Update system status
            with _thread_lock:
                _system_status["successful_runs"] += 1
        else:
            logger.debug("[ARP-WARMING] No IPs to warm")
            
    except Exception as e:
        with _thread_lock:
            _system_status["errors"] += 1
            _system_status["last_error"] = str(e)
        
        logger.error(f"[ARP-WARMING] Error in periodic warming: {e}")
    finally:
        # Always update the run duration
        elapsed_time = time.time() - start_time
        
        with _thread_lock:
            _system_status["last_run_duration"] = round(elapsed_time, 2)

def warming_job():
    """Background job function for warming thread"""
    global _stop_thread, _system_status
    
    logger.info("[ARP-WARMING] Starting ARP warming background thread")
    
    # Update system status
    with _thread_lock:
        _system_status["thread_running"] = True
    
    try:
        # Initial delay to let the application fully start
        time.sleep(5)
        
        # Setup dedicated scheduler with our custom jobs
        # Using a dedicated scheduler instance to avoid conflicts with any global scheduler
        
        # Main warming job - every 5 minutes
        _scheduler.every(5).minutes.do(perform_periodic_warming)
        
        # Cleanup job - every hour (we'll define this function next)
        _scheduler.every(1).hours.do(lambda: cleanup_stale_clients(max_age_hours=24))
        
        # Run immediately first time
        perform_periodic_warming()
        
        # Main loop with better error handling
        while not _stop_thread:
            try:
                _scheduler.run_pending()  # Use our isolated scheduler
            except Exception as e:
                logger.error(f"[ARP-WARMING] Error in scheduler: {e}")
                with _thread_lock:
                    _system_status["errors"] += 1
                    _system_status["last_error"] = str(e)
                    
            # Short sleep to reduce CPU usage but still allow quick shutdown
            time.sleep(1)
    finally:
        # Always update thread status on exit
        with _thread_lock:
            _system_status["thread_running"] = False
            
        logger.info("[ARP-WARMING] ARP warming thread stopped")

def cleanup_stale_clients(max_age_hours: int = 24):
    """
    Clean up stale entries from the recent clients dictionary
    
    Args:
        max_age_hours: Maximum age in hours before an entry is considered stale
    """
    global _recent_clients
    
    try:
        logger.debug(f"[ARP-WARMING] Cleaning up stale clients older than {max_age_hours} hours")
        current_time = time.time()
        max_age_secs = max_age_hours * 3600
        
        with _thread_lock:
            # Find stale entries
            stale_ips = [
                ip for ip, data in _recent_clients.items()
                if current_time - data.get('last_seen', 0) > max_age_secs
            ]
            
            # Remove stale entries
            for ip in stale_ips:
                del _recent_clients[ip]
                
            if stale_ips:
                logger.info(f"[ARP-WARMING] Cleaned up {len(stale_ips)} stale client entries")
                
    except Exception as e:
        logger.error(f"[ARP-WARMING] Error cleaning up stale clients: {e}")

def get_warming_status() -> Dict[str, Any]:
    """
    Get current status of the ARP warming system
    
    Returns:
        Dict containing system status information
    """
    with _thread_lock:
        # Make a copy of the status
        status = dict(_system_status)
        
        # Add additional information
        status["active_warming_count"] = len(_active_warming_ips)
        status["recent_clients_count"] = len(_recent_clients)
        status["recent_clients"] = {
            ip: data for ip, data in list(_recent_clients.items())[:20]  # Return at most 20 recent clients
        }
        
        return status

def start_warming_thread():
    """Start the background warming thread"""
    global _warming_thread, _stop_thread, _system_status
    
    with _thread_lock:
        if _warming_thread and _warming_thread.is_alive():
            logger.debug("[ARP-WARMING] Warming thread already running")
            return
        
        # Reset the stop flag
        _stop_thread = False
        
        # Update status
        _system_status["enabled"] = True
        
        # Create and start the thread
        _warming_thread = threading.Thread(target=warming_job, daemon=True, name="ARP-Warming-Thread")
        _warming_thread.start()
        
        logger.info("[ARP-WARMING] Started ARP warming thread")

def stop_warming_thread():
    """Stop the background warming thread"""
    global _stop_thread, _system_status
    
    with _thread_lock:
        _stop_thread = True
        _system_status["enabled"] = False
        
    logger.info("[ARP-WARMING] Requested stop for ARP warming thread")

# Initialize on module load if enabled
def init_ip_warming():
    """
    Initialize the IP warming system if enabled in config
    
    Returns:
        bool: True if successfully initialized, False otherwise
    """
    global _system_status
    
    try:
        from flask import current_app
        
        # Check if we're in an application context and if warming is enabled
        if current_app.config.get('ENABLE_ARP_WARMING', True):
            # Check if threading is safe in this environment
            if current_app.config.get('TESTING', False):
                logger.info("[ARP-WARMING] Running in test mode, disabling background thread")
                with _thread_lock:
                    _system_status["enabled"] = False
                return False
                
            # Initialize with app context
            logger.info("[ARP-WARMING] Successfully initialized ARP warming system - daemon mode enabled")
            
            # Setup caching integration if available
            if cache_manager:
                try:
                    # Use direct key prefixing instead of relying on method
                    logger.info("[ARP-WARMING] Setting up cache integration")
                except Exception as e:
                    logger.warning(f"[ARP-WARMING] Could not set up caching: {e}")
                
            # Start the background thread
            start_warming_thread()
            
            # Teardown handler is now registered in arp_warming_setup.py
            logger.debug("[ARP-WARMING] Skipping teardown handler registration here (done in setup_arp_warming)")
                
            return True
        else:
            logger.info("[ARP-WARMING] ARP warming disabled in config")
            with _thread_lock:
                _system_status["enabled"] = False
            return False
            
    except RuntimeError:
        # Not in app context, use a safer approach for testing/CLI
        logger.warning("[ARP-WARMING] Cannot initialize ARP warming outside application context")
        with _thread_lock:
            _system_status["enabled"] = False
        return False
    except Exception as e:
        # Catch any other initialization errors
        logger.error(f"[ARP-WARMING] Error initializing warming system: {e}")
        with _thread_lock:
            _system_status["enabled"] = False
            _system_status["last_error"] = str(e)
        return False


# Main entry point - init on module load if configured to do so
# Only start automatically if in a Flask app context
if __name__ != '__main__':
    try:
        # Use delayed import to prevent circular imports
        from flask import has_app_context
        if has_app_context():
            init_ip_warming()
        else:
            logger.info("[ARP-WARMING] No Flask app context found on module load - will initialize later")
    except ImportError:
        logger.info("[ARP-WARMING] Flask not available - will initialize when imported by app")
    except Exception as e:
        logger.error(f"[ARP-WARMING] Error during auto-initialization: {e}")
        
# Register the system functions with the API manager if available
try:
    # Attempt to register with system API if available
    # If app.api.system doesn't exist, that's okay - this is an optional integration
    from importlib import import_module
    system_module = import_module('app.api.system')
    if hasattr(system_module, 'register_system_component'):
        system_module.register_system_component('network.warming', get_warming_status)
        logger.info("[ARP-WARMING] Registered with system API")
except (ImportError, AttributeError):
    # API system not available or compatible, skip registration
    logger.debug("[ARP-WARMING] System API not available for registration")
except Exception as e:
    logger.warning(f"[ARP-WARMING] Error registering with system API: {e}")
