"""
MAC Address Detection Test Script

This script tests the MAC address detection and caching mechanisms.
It checks:
1. MAC address lookup for multiple IPs
2. Cache invalidation when IP changes
3. Proper DHCP server selection based on mode

Usage:
docker-compose exec backend python /app/tests/scripts/mac_detection_test.py [ip_address]
"""
import os
import sys
import time
import json
from datetime import datetime
from flask import current_app

# Add app directory to path for imports
sys.path.append('/app')

try:
    # Import required modules
    from app.services.client_detection_service import ClientDetectionService
    from app.infrastructure.gateways.mikrotik_client import (
        find_mac_for_ip, 
        ensure_dhcp_static_lease,
        find_and_update_address_list_entry,
        get_mikrotik_connection
    )
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you're running this script inside the backend container")
    sys.exit(1)

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f" {text} ".center(78, " "))
    print("=" * 80)

def test_mac_lookup(ip_address):
    """Test MAC address lookup for a specific IP"""
    print_header(f"MAC LOOKUP TEST FOR {ip_address}")
    
    print("Testing MAC lookup using different methods:")
    
    # Method 1: Direct API call with cache
    print("\n1. Direct API call with cache:")
    try:
        start = time.time()
        mac = find_mac_for_ip(ip_address, use_cache=True)
        end = time.time()
        if mac:
            print(f"✅ Found MAC: {mac} (took {end-start:.3f}s)")
        else:
            print(f"❌ No MAC found for {ip_address}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Method 2: Force refresh (no cache)
    print("\n2. Force refresh (no cache):")
    try:
        start = time.time()
        mac = find_mac_for_ip(ip_address, use_cache=False, force_refresh=True)
        end = time.time()
        if mac:
            print(f"✅ Found MAC: {mac} (took {end-start:.3f}s)")
        else:
            print(f"❌ No MAC found for {ip_address}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Method 3: Using ClientDetectionService
    print("\n3. Using ClientDetectionService:")
    try:
        start = time.time()
        result = ClientDetectionService.get_client_info(frontend_ip=ip_address, force_refresh=True)
        end = time.time()
        if result.get('detected_mac'):
            print(f"✅ Found MAC: {result.get('detected_mac')} (took {end-start:.3f}s)")
            print(f"   Detection method: {result.get('detection_method')}")
            print(f"   From cache: {result.get('from_cache', False)}")
        else:
            print(f"❌ No MAC found for {ip_address}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return result.get('detected_mac') if 'result' in locals() and result else mac if 'mac' in locals() and mac else None

def test_dhcp_server_selection(ip_address, mac_address):
    """Test DHCP server selection based on mode"""
    if not mac_address:
        print("\n❌ Cannot test DHCP server selection without a MAC address")
        return
        
    print_header(f"DHCP SERVER SELECTION TEST FOR {ip_address}/{mac_address}")
    
    # Get current test mode setting
    test_mode = os.environ.get('SYNC_TEST_MODE_ENABLED', 'False').lower() == 'true'
    print(f"Current SYNC_TEST_MODE_ENABLED: {test_mode}")
    
    # Get server names from environment or config
    try:
        # Try to get from environment variables first
        test_server = os.environ.get('MIKROTIK_SERVER_TESTING', 'testing')
        user_server = os.environ.get('MIKROTIK_SERVER_USER', 'srv-user')
        
        print(f"Test server name: {test_server}")
        print(f"User server name: {user_server}")
        
        # Check which server would be used based on current mode
        expected_server = test_server if test_mode else user_server
        print(f"Based on current mode, expected server: {expected_server}")
        
        # Use inspect mode to check what would happen (don't actually create lease)
        print("\nInspecting potential DHCP lease command:")
        print(f"IP: {ip_address}")
        print(f"MAC: {mac_address}")
        
        # Create a mock connection for inspection
        client = get_mikrotik_connection()
        
        # Check if a lease already exists
        try:
            command = f"/ip/dhcp-server/lease/print where mac-address={mac_address}"
            result = client(command)
            
            if result:
                print(f"\nExisting lease found for MAC {mac_address}:")
                for lease in result:
                    print(f"  - {json.dumps(lease)}")
        except Exception as e:
            print(f"Error checking existing leases: {e}")
        
        # Inspect what server would be used in prod mode
        os.environ['SYNC_TEST_MODE_ENABLED'] = 'False'
        comment = f"test-{int(time.time())}"
        
        print(f"\nSimulating DHCP lease command in PRODUCTION mode:")
        command = f'/ip/dhcp-server/lease/add =address={ip_address} =mac-address={mac_address}'
        if not test_mode:
            command += f' =server={user_server}'
        command += f' =comment={comment}'
        print(f"Command: {command}")
        
        # Inspect what server would be used in test mode
        os.environ['SYNC_TEST_MODE_ENABLED'] = 'True'
        print(f"\nSimulating DHCP lease command in TEST mode:")
        command = f'/ip/dhcp-server/lease/add =address={ip_address} =mac-address={mac_address}'
        if test_mode:
            command += f' =server={test_server}'
        command += f' =comment={comment}'
        print(f"Command: {command}")
        
        # Restore original test mode setting
        os.environ['SYNC_TEST_MODE_ENABLED'] = str(test_mode)
        
    except Exception as e:
        print(f"❌ Error during DHCP server selection test: {e}")

def test_ip_change_detection():
    """Test MAC address caching and IP change detection"""
    print_header("IP CHANGE DETECTION TEST")
    
    # Let's create two test IPs by incrementing the last octet
    # Get the current client IP from environment
    client_ip = os.environ.get('TEST_CLIENT_IP', '172.16.15.231')
    
    # Split IP into octets
    octets = client_ip.split('.')
    if len(octets) != 4:
        print(f"❌ Invalid IP format: {client_ip}")
        return
    
    # Create a second test IP by incrementing last octet
    last_octet = int(octets[3])
    next_octet = (last_octet + 1) % 254
    ip1 = client_ip
    ip2 = f"{octets[0]}.{octets[1]}.{octets[2]}.{next_octet}"
    
    print(f"Testing IP change detection between {ip1} and {ip2}")
    
    # First, lookup MAC for ip1
    print(f"\n1. Looking up MAC for {ip1}:")
    mac1 = test_mac_lookup(ip1)
    
    if not mac1:
        print(f"❌ Cannot continue test - no MAC found for {ip1}")
        return
    
    # Now test with IP change detection
    print(f"\n2. Looking up MAC for {ip2} with previous_ip={ip1}:")
    try:
        start = time.time()
        result = ClientDetectionService.get_client_info(
            frontend_ip=ip2, 
            force_refresh=True,
            previous_ip=ip1
        )
        end = time.time()
        
        if result.get('detected_mac'):
            print(f"✅ Found MAC: {result.get('detected_mac')} (took {end-start:.3f}s)")
            print(f"   Detection method: {result.get('detection_method')}")
            print(f"   From cache: {result.get('from_cache', False)}")
            
            # Compare with previous MAC
            if result.get('detected_mac') == mac1:
                print(f"✅ MAC addresses match: Both IPs belong to same device")
            else:
                print(f"❓ MAC addresses differ: {mac1} vs {result.get('detected_mac')}")
                print("   This could indicate different devices or MAC spoofing")
        else:
            print(f"❌ No MAC found for {ip2}")
    except Exception as e:
        print(f"❌ Error during IP change detection test: {e}")

if __name__ == "__main__":
    print_header(f"MAC ADDRESS DETECTION TEST - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get IP address from command line or use default
    ip_address = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('TEST_CLIENT_IP', '172.16.15.231')
    print(f"Using IP address: {ip_address}")
    
    # Test MAC lookup
    mac_address = test_mac_lookup(ip_address)
    
    # Test DHCP server selection
    if mac_address:
        test_dhcp_server_selection(ip_address, mac_address)
    
    # Test IP change detection
    test_ip_change_detection()
    
    print_header("TEST COMPLETED")
