"""
Patch script to fix DHCP server selection based on operation mode
(testing vs production) and optimize MAC address caching.

This script addresses:
1. DHCP server selection when adding static leases
2. MAC address caching and invalidation issues
3. IP change detection and handling

Run this script with:
docker-compose exec backend python /app/patches/fix_dhcp_server_selection.py
"""
import os
import sys
import re
import shutil
from datetime import datetime

BACKUP_SUFFIX = f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"

def patch_mikrotik_client():
    """Patch the MikroTik client implementation to use proper server selection"""
    try:
        # Paths
        mikrotik_client_path = "/app/app/infrastructure/gateways/mikrotik_client.py"
        backup_path = f"{mikrotik_client_path}{BACKUP_SUFFIX}"
        
        # Check if file exists
        if not os.path.exists(mikrotik_client_path):
            print(f"Error: {mikrotik_client_path} does not exist")
            return False
        
        # Create backup
        shutil.copy2(mikrotik_client_path, backup_path)
        print(f"Created backup at {backup_path}")
        
        # Read file
        with open(mikrotik_client_path, 'r') as f:
            content = f.read()
        
        # Define replacements with better server selection logic
        replacements = [
            # Fix 1: Improve the ensure_dhcp_static_lease function to use proper server selection
            (
                "def ensure_dhcp_static_lease(address, mac_address, comment=None, use_cache=True):",
                """def ensure_dhcp_static_lease(address, mac_address, comment=None, use_cache=True, server=None):
    \"\"\"
    Ensures a DHCP static lease exists for the given IP and MAC.
    Now supports explicit server selection.
    \"\"\"
    # Use the explicitly provided server or get from config
    if not server:
        # If SYNC_TEST_MODE_ENABLED is True, use the testing server
        if current_app.config.get('SYNC_TEST_MODE_ENABLED', False):
            server = current_app.config.get('MIKROTIK_SERVER_TESTING')
        else:
            # Default servers for production modes
            server = current_app.config.get('MIKROTIK_SERVER_USER')"""
            ),
            
            # Fix 2: Update the function call to add server parameter
            (
                "def add_static_dhcp_lease(address, mac_address, comment=None):",
                """def add_static_dhcp_lease(address, mac_address, comment=None, server=None):
    \"\"\"
    Add a static DHCP lease for the given IP and MAC with proper server selection.
    \"\"\"
    # Use the explicitly provided server or get from config
    if not server:
        # If SYNC_TEST_MODE_ENABLED is True, use the testing server
        if current_app.config.get('SYNC_TEST_MODE_ENABLED', False):
            server = current_app.config.get('MIKROTIK_SERVER_TESTING')
        else:
            # Default servers for production modes
            server = current_app.config.get('MIKROTIK_SERVER_USER')"""
            ),
            
            # Fix 3: Update the command construction to include server parameter
            (
                "    command = f'/ip/dhcp-server/lease/add =address={address} =mac-address={mac_address}'",
                """    # Use the proper server parameter if provided
    command = f'/ip/dhcp-server/lease/add =address={address} =mac-address={mac_address}'
    
    # Add server parameter if provided
    if server:
        command += f' =server={server}'"""
            )
        ]
        
        # Apply replacements
        modified = False
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"Modified: {old[:50]}...")
        
        if not modified:
            print("Warning: No target code found for modification in mikrotik_client.py")
            return False
        
        # Write modified content back
        with open(mikrotik_client_path, 'w') as f:
            f.write(content)
        
        print(f"Successfully patched {mikrotik_client_path}")
        return True
        
    except Exception as e:
        print(f"Error patching MikroTik client file: {e}")
        return False

def patch_client_detection_service():
    """Patch the client detection service to improve MAC caching and invalidation"""
    try:
        # Paths
        detection_service_path = "/app/app/services/client_detection_service.py"
        backup_path = f"{detection_service_path}{BACKUP_SUFFIX}"
        
        # Check if file exists
        if not os.path.exists(detection_service_path):
            print(f"Error: {detection_service_path} does not exist")
            return False
        
        # Create backup
        shutil.copy2(detection_service_path, backup_path)
        print(f"Created backup at {backup_path}")
        
        # Read file
        with open(detection_service_path, 'r') as f:
            content = f.read()
        
        # Define replacements to improve MAC caching behavior
        replacements = [
            # Fix 1: Improve MAC cache invalidation logic when IP changes
            (
                "    def get_client_info(frontend_ip=None, frontend_mac=None, use_cache=True, force_refresh=False):",
                """    def get_client_info(frontend_ip=None, frontend_mac=None, use_cache=True, force_refresh=False, previous_ip=None):
        \"\"\"
        Get client information with improved caching logic.
        Now supports tracking IP changes with previous_ip parameter.
        \"\"\"
        # Force cache invalidation if IP has changed
        if previous_ip and frontend_ip and previous_ip != frontend_ip:
            force_refresh = True
            logger.info(f"[CLIENT-DETECT] 🔄 IP changed from {previous_ip} to {frontend_ip}, forcing cache refresh")"""
            ),
            
            # Fix 2: Add IP change detection in the MAC lookup function
            (
                "    def find_mac_for_ip(ip, is_browser=True, use_cache=True, force_refresh=False):",
                """    def find_mac_for_ip(ip, is_browser=True, use_cache=True, force_refresh=False, previous_ip=None):
        \"\"\"
        Find MAC address for an IP with improved IP change handling.
        \"\"\"
        # Force cache invalidation if IP has changed
        if previous_ip and ip and previous_ip != ip:
            force_refresh = True
            logger.info(f"[CLIENT-DETECT] 🔄 IP changed from {previous_ip} to {ip}, forcing cache refresh")"""
            )
        ]
        
        # Apply replacements
        modified = False
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"Modified: {old[:50]}...")
        
        if not modified:
            print("Warning: No target code found for modification in client_detection_service.py")
            return False
        
        # Write modified content back
        with open(detection_service_path, 'w') as f:
            f.write(content)
        
        print(f"Successfully patched {detection_service_path}")
        return True
        
    except Exception as e:
        print(f"Error patching client detection service file: {e}")
        return False

def patch_auth_routes():
    """Patch the auth_routes.py to improve IP change handling and DHCP server selection"""
    try:
        # Paths
        auth_routes_path = "/app/app/infrastructure/http/auth_routes.py"
        backup_path = f"{auth_routes_path}{BACKUP_SUFFIX}"
        
        # Check if file exists
        if not os.path.exists(auth_routes_path):
            print(f"Error: {auth_routes_path} does not exist")
            return False
        
        # Create backup
        shutil.copy2(auth_routes_path, backup_path)
        print(f"Created backup at {backup_path}")
        
        # Read file
        with open(auth_routes_path, 'r') as f:
            content = f.read()
        
        # Define replacements for auth_routes.py
        replacements = [
            # Fix 1: Update sync-device to track IP changes
            (
                "        # Obtain trusted IP detected by server (proxy headers) and override stale frontend IP when mismatch",
                """        # Get the previously detected IP for this device if available
        previous_ip = None
        try:
            if client_mac:
                # Try to get previous IP from session or device record
                from app.services.auth_session_service import AuthSessionService
                session_data = AuthSessionService.get_session_data(client_mac=client_mac)
                if session_data:
                    previous_ip = session_data.get('client_ip')
        except Exception:
            pass
            
        # Obtain trusted IP detected by server (proxy headers) and override stale frontend IP when mismatch"""
            ),
            
            # Fix 2: Pass previous_ip to client detection service
            (
                "        detection_result = ClientDetectionService.get_client_info(",
                """        detection_result = ClientDetectionService.get_client_info(
            frontend_ip=effective_ip or requested_ip,
            frontend_mac=requested_mac,
            force_refresh=bool(requested_ip or requested_mac),
            use_cache=False if (requested_ip or requested_mac) else True,
            previous_ip=previous_ip
        )"""
            ),
            
            # Fix 3: Update DHCP lease call to use server parameter
            (
                "                                find_and_update_address_list_entry(list_name, client_ip, comment)",
                """                                # Use proper server selection based on mode
                                test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
                                server = None
                                if test_mode:
                                    server = current_app.config.get('MIKROTIK_SERVER_TESTING')
                                
                                find_and_update_address_list_entry(list_name, client_ip, comment)"""
            ),
            
            # Fix 4: Update ensure_dhcp_static_lease call to use server parameter
            (
                "                        ok = ensure_dhcp_static_lease(client_ip, client_mac, comment=comment)",
                """                        # Use proper server selection based on mode
                        test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
                        server = None
                        if test_mode:
                            server = current_app.config.get('MIKROTIK_SERVER_TESTING')
                        
                        ok = ensure_dhcp_static_lease(client_ip, client_mac, comment=comment, server=server)"""
            )
        ]
        
        # Apply replacements
        modified = False
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"Modified: {old[:50]}...")
            else:
                print(f"Pattern not found: {old[:50]}...")
                
        # Fix the ClientDetectionService.get_client_info call - using regex for complex replacements
        pattern = r"detection_result = ClientDetectionService.get_client_info\(\s*frontend_ip=effective_ip or requested_ip,\s*frontend_mac=requested_mac,\s*force_refresh=bool\(requested_ip or requested_mac\),\s*use_cache=False if \(requested_ip or requested_mac\) else True\s*\)"
        if re.search(pattern, content):
            content = re.sub(pattern, """detection_result = ClientDetectionService.get_client_info(
            frontend_ip=effective_ip or requested_ip,
            frontend_mac=requested_mac,
            force_refresh=bool(requested_ip or requested_mac),
            use_cache=False if (requested_ip or requested_mac) else True,
            previous_ip=previous_ip
        )""", content)
            modified = True
            print("Modified: ClientDetectionService.get_client_info call")
        
        if not modified:
            print("Warning: No target code found for modification in auth_routes.py")
            return False
        
        # Write modified content back
        with open(auth_routes_path, 'w') as f:
            f.write(content)
        
        print(f"Successfully patched {auth_routes_path}")
        return True
        
    except Exception as e:
        print(f"Error patching auth_routes.py file: {e}")
        return False

def create_marker_file():
    """Create a marker file to indicate the patch was applied"""
    try:
        marker_path = "/app/DHCP_SERVER_MAC_PATCH_APPLIED.txt"
        with open(marker_path, 'w') as f:
            f.write(f"DHCP server selection and MAC caching patch applied at {datetime.now()}\n")
            f.write("This patch fixes:\n")
            f.write("1. DHCP server selection based on test/production mode\n")
            f.write("2. MAC address caching for IP changes\n")
            f.write("3. IP change detection and handling\n")
            f.write("\nBackups were created with timestamp suffix\n")
        print(f"Created marker file at {marker_path}")
        return True
    except Exception as e:
        print(f"Error creating marker file: {e}")
        return False

if __name__ == "__main__":
    print(f"\n{'=' * 80}")
    print(f" DHCP SERVER SELECTION AND MAC CACHING PATCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ".center(80))
    print(f"{'=' * 80}")
    
    success = True
    
    # Patch MikroTik client
    success = patch_mikrotik_client() and success
    
    # Patch client detection service
    success = patch_client_detection_service() and success
    
    # Patch auth routes
    success = patch_auth_routes() and success
    
    # Create marker file
    if success:
        create_marker_file()
    
    if success:
        print(f"\n{'=' * 80}")
        print(" PATCH SUCCESSFULLY APPLIED ".center(80))
        print(" Please restart the backend container: docker-compose restart backend ".center(80))
        print(f"{'=' * 80}")
    else:
        print(f"\n{'=' * 80}")
        print(" PATCH PARTIALLY APPLIED OR FAILED ".center(80))
        print(" Please check the logs and fix any issues manually ".center(80))
        print(f"{'=' * 80}")
