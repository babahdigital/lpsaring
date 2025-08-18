# backend/app/infrastructure/gateways/mikrotik_client_enhancement.py
"""
Enhanced MikroTik client functionality untuk pre-emptive ARP warming dan deteksi yang lebih baik
"""

import logging
from typing import List, Dict, Optional, Any  # Removed unused Tuple import

import flask
from app.infrastructure.gateways.mikrotik_client import _get_api_from_pool

# Get configuration without needing application context
# TODO: This function is currently unused but kept for future use
def _get_config(key, default=None):
    """Get configuration value safely without requiring app context"""
    try:
        return flask.current_app.config.get(key, default)
    except RuntimeError:
        # No application context
        return default

logger = logging.getLogger(__name__)

def ping_ip_with_options(ip_address: str, sizes: Optional[List[int]] = None, count: int = 1) -> bool:
    """
    Ping an IP address with various size options to trigger ARP
    
    Args:
        ip_address: The IP to ping
        sizes: List of ping packet sizes to try
        count: Number of pings to send for each size
        
    Returns:
        True if at least one ping was successful
    """
    if not ip_address:
        return False
        
    if sizes is None:
        sizes = [56]  # Default size
    try:
        api = _get_api_from_pool()
        if api is None:
            logger.warning("Failed to get API connection")
            return False
            
        success = False
        
        for size in sizes:
            try:
                ping_resource = api.get_resource('/')
                ping_resource = api.get_resource('/')
                result = ping_resource.call('ping', {
                    'address': ip_address,
                    'count': str(count),
                    'size': str(size)
                })
                
                # Check if any ping was successful
                for item in result:
                    if 'status' in item and item['status'] != 'timeout':
                        success = True
                        break
                        
                if success:
                    break
            except Exception as e:
                logger.debug(f"Ping failed for {ip_address} with size {size}: {e}")
                
        return success
    except Exception as e:
        logger.warning(f"Error pinging {ip_address}: {e}")
        return False

def get_active_ip_addresses(limit: int = 100) -> List[str]:
    """
    Get list of active IP addresses from MikroTik
    
    Args:
        limit: Maximum number of entries to retrieve
        
    Returns:
        List of active IP addresses
    """
    try:
        api = _get_api_from_pool()
        if api is None:
            logger.warning("Failed to get API connection")
            return []
            
        active_ips = set()
        
        # 1. Get active hotspot users
        try:
            active_hotspot = api.get_resource('/ip/hotspot/active').get(limit=str(limit))
            for item in active_hotspot:
                if 'address' in item:
                    active_ips.add(item['address'])
        except Exception as e:
            logger.debug(f"Failed to get active hotspot users: {e}")
            
        # 2. Get active from ARP
        try:
            arp_table = api.get_resource('/ip/arp').get(dynamic='yes', limit=str(limit))
            for item in arp_table:
                if 'address' in item:
                    active_ips.add(item['address'])
        except Exception as e:
            logger.debug(f"Failed to get ARP table: {e}")
            
        # 3. Get DHCP leases
        try:
            dhcp_leases = api.get_resource('/ip/dhcp-server/lease').get(
                status='bound', 
                limit=str(limit)
            )
            for item in dhcp_leases:
                if 'address' in item:
                    active_ips.add(item['address'])
        except Exception as e:
            logger.debug(f"Failed to get DHCP leases: {e}")
            
        return list(active_ips)
    except Exception as e:
        logger.warning(f"Error getting active IP addresses: {e}")
        return []

def get_active_connection_by_ip(ip_address: str) -> List[Dict[str, Any]]:
    """
    Get active TCP connections for an IP address
    
    Args:
        ip_address: The IP address to check
        
    Returns:
        List of connection information dictionaries
    """
    if not ip_address:
        return []
        
    try:
        api = _get_api_from_pool()
        if api is None:
            logger.warning("Failed to get API connection")
            return []
        
        # Get all active TCP connections for this IP (either source or destination)
        connections = api.get_resource('/ip/firewall/connection').get(
            **{"src-address": ip_address}
        )
        
        # Add destination address connections
        connections.extend(
            api.get_resource('/ip/firewall/connection').get(
                **{"dst-address": ip_address}
            )
        )
        
        return connections
    except Exception as e:
        logger.warning(f"Error getting TCP connections for {ip_address}: {e}")
        return []
