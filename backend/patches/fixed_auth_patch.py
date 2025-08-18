"""
Fixed hotfix script to properly fix indentation when patching auth_routes.py file.
"""
import os
import sys
import re
import shutil
from datetime import datetime

BACKUP_SUFFIX = f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"

def patch_auth_routes():
    """Patch the auth_routes.py file to bypass device authorization check with correct indentation"""
    try:
        # Paths
        auth_routes_path = "/app/app/infrastructure/http/auth_routes.py"
        backup_path = f"{auth_routes_path}{BACKUP_SUFFIX}"
        
        # Check if file exists
        if not os.path.exists(auth_routes_path):
            print(f"Error: {auth_routes_path} does not exist")
            return False
        
        # Read file and restore from previous backup if needed
        try:
            # Check if we need to restore from the previous backup
            previous_backups = [f for f in os.listdir("/app/app/infrastructure/http") if f.startswith("auth_routes.py.bak")]
            if previous_backups:
                # Sort by timestamp to get the most recent
                previous_backups.sort(reverse=True)
                latest_backup = os.path.join("/app/app/infrastructure/http", previous_backups[0])
                print(f"Restoring from backup: {latest_backup}")
                shutil.copy2(latest_backup, auth_routes_path)
                print(f"Restored from backup at {latest_backup}")
        except Exception as e:
            print(f"Warning: Could not restore from backup: {e}")
        
        # Create a new backup
        shutil.copy2(auth_routes_path, backup_path)
        print(f"Created new backup at {backup_path}")
        
        # Read the file
        with open(auth_routes_path, 'r') as f:
            content = f.read()
        
        # Define precise replacements with correct indentation
        replacements = [
            (
                "                if current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH', True):",
                "                if False:  # HOTFIX: Bypass device authorization check"
            ),
            (
                "                    if not current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH', True):",
                "                    if True:  # HOTFIX: Always allow auto-bypass"
            ),
            (
                "                    require_explicit = current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH', True)",
                "                    require_explicit = False  # HOTFIX: Bypass device authorization requirement"
            )
        ]
        
        # Apply replacements
        modified = False
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"Replaced: {old} -> {new}")
        
        if not modified:
            print("Warning: No target lines found for modification")
            return False
        
        # Write modified content back
        with open(auth_routes_path, 'w') as f:
            f.write(content)
        
        print(f"Successfully patched {auth_routes_path}")
        
        # Create a marker file to indicate patch was applied
        marker_path = "/app/HOTFIX_APPLIED_AUTH.txt"
        with open(marker_path, 'w') as f:
            f.write(f"Auth bypass hotfix applied at {datetime.now()}\n")
            f.write(f"Original file backed up at: {backup_path}\n")
        print(f"Created marker file at {marker_path}")
        
        return True
        
    except Exception as e:
        print(f"Error patching file: {e}")
        return False

if __name__ == "__main__":
    print(f"\n{'=' * 80}")
    print(f" FIXED AUTH BYPASS PATCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ".center(80))
    print(f"{'=' * 80}")
    
    success = patch_auth_routes()
    
    if success:
        print(f"\n{'=' * 80}")
        print(" PATCH SUCCESSFULLY APPLIED ".center(80))
        print(" Please restart the backend container: docker-compose restart backend ".center(80))
        print(f"{'=' * 80}")
    else:
        print(f"\n{'=' * 80}")
        print(" PATCH FAILED ".center(80))
        print(f"{'=' * 80}")
