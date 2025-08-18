"""
This script manually patches the Python application to ensure environment variables
from .env.override are loaded properly. Place it in the backend directory and run:

docker-compose exec backend python scripts/apply_env_fix.py
"""

import os
import sys
import importlib.util
from pathlib import Path

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def load_env_override():
    """Manually load .env.override file"""
    override_path = Path('.env.override')
    if not override_path.exists():
        print(f"{RED}[ERROR]{RESET} .env.override file not found")
        return False
    
    print(f"{YELLOW}[LOADING]{RESET} .env.override file")
    try:
        with open(override_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    if key:  # Skip empty keys
                        os.environ[key] = value
                        print(f"  {key}={value}")
        
        print(f"{GREEN}[SUCCESS]{RESET} Loaded environment variables from .env.override")
        return True
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to load .env.override: {e}")
        return False

def patch_config_file():
    """Patch config.py to load .env.override file directly"""
    config_file = Path('config.py')
    if not config_file.exists():
        print(f"{RED}[ERROR]{RESET} config.py file not found")
        return False
    
    print(f"{YELLOW}[PATCHING]{RESET} config.py file")
    
    # Read the current content
    with open(config_file, 'r') as f:
        content = f.read()
    
    # Check if already patched
    if "load_env_override()" in content:
        print(f"{YELLOW}[ALREADY PATCHED]{RESET} config.py already has the override function")
        return True
    
    # Create a backup
    backup_path = Path('config.py.bak')
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"{BLUE}[BACKUP]{RESET} Created backup at {backup_path}")
    
    # Add the patch
    patch = """
# Function to load environment variables from .env.override
def load_env_override():
    \"\"\"Manually load .env.override file to ensure it takes precedence\"\"\"
    import os
    from pathlib import Path
    
    override_path = Path('.env.override')
    if override_path.exists():
        print(f"Loading environment overrides from .env.override")
        with open(override_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\\'')
                    if key:  # Skip empty keys
                        os.environ[key] = value
                        print(f"  Set {key}={value}")

# Load .env.override at import time
load_env_override()
"""
    
    # Find the best insertion point - after imports but before class definitions
    lines = content.splitlines()
    import_section_end = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            import_section_end = i + 1
    
    # Insert after imports
    patched_content = '\n'.join(lines[:import_section_end]) + '\n' + patch + '\n' + '\n'.join(lines[import_section_end:])
    
    # Write the patched file
    with open(config_file, 'w') as f:
        f.write(patched_content)
    
    print(f"{GREEN}[SUCCESS]{RESET} Patched config.py to load .env.override")
    return True

def verify_environment_variables():
    """Verify that critical environment variables are properly set"""
    print(f"\n{YELLOW}[VERIFYING ENVIRONMENT]{RESET}")
    
    critical_vars = [
        "REQUIRE_EXPLICIT_DEVICE_AUTH",
        "SESSION_TYPE",
        "REDIS_URL"
    ]
    
    # First load the variables directly
    load_env_override()
    
    all_set = True
    for var in critical_vars:
        value = os.environ.get(var)
        if value is None:
            print(f"{RED}[MISSING]{RESET} {var} is not set in environment")
            all_set = False
        else:
            print(f"{GREEN}[SET]{RESET} {var}={value}")
    
    if all_set:
        print(f"{GREEN}[SUCCESS]{RESET} All critical environment variables are set")
    else:
        print(f"{RED}[WARNING]{RESET} Some critical environment variables are missing")
    
    return all_set

def modify_app_init():
    """Patch app/__init__.py to ensure environment variables are loaded"""
    init_file = Path('app/__init__.py')
    if not init_file.exists():
        print(f"{RED}[ERROR]{RESET} app/__init__.py file not found")
        return False
    
    print(f"{YELLOW}[PATCHING]{RESET} app/__init__.py file")
    
    # Read the current content
    with open(init_file, 'r') as f:
        content = f.read()
    
    # Check if already patched
    if "load_env_override()" in content:
        print(f"{YELLOW}[ALREADY PATCHED]{RESET} app/__init__.py already has the override function")
        return True
    
    # Create a backup
    backup_path = Path('app/__init__.py.bak')
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"{BLUE}[BACKUP]{RESET} Created backup at {backup_path}")
    
    # Add the patch at the beginning of the file
    patch = """# Ensure environment variables are loaded first thing
import os
from pathlib import Path

def load_env_override():
    \"\"\"Manually load .env.override file at app initialization\"\"\"
    override_path = Path('../.env.override')
    if override_path.exists():
        print(f"Loading environment overrides from .env.override in app/__init__.py")
        with open(override_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\\'')
                    if key:
                        os.environ[key] = value
    else:
        print(f"Warning: .env.override file not found in app/__init__.py")

# Load environment variables at the earliest possible moment
load_env_override()

"""
    
    # Insert at the beginning
    patched_content = patch + content
    
    # Write the patched file
    with open(init_file, 'w') as f:
        f.write(patched_content)
    
    print(f"{GREEN}[SUCCESS]{RESET} Patched app/__init__.py to load .env.override")
    return True

def create_env_monitor():
    """Create a script that monitors and reports on environment variables during app startup"""
    monitor_path = Path('app/env_monitor.py')
    
    print(f"{YELLOW}[CREATING]{RESET} Environment monitor script")
    
    monitor_content = """
import os
import logging
import atexit

logger = logging.getLogger("env_monitor")

def log_environment_variables():
    \"\"\"Log critical environment variables\"\"\"
    logger.info("===== ENVIRONMENT VARIABLES =====")
    critical_vars = [
        "REQUIRE_EXPLICIT_DEVICE_AUTH",
        "SESSION_TYPE", 
        "REDIS_URL",
        "FLASK_ENV",
        "FLASK_DEBUG"
    ]
    
    for var in critical_vars:
        value = os.environ.get(var)
        if value is None:
            logger.warning(f"❌ {var} is not set")
        else:
            logger.info(f"✓ {var}={value}")
    
    # Also log Redis-related variables
    redis_vars = [k for k in os.environ.keys() if "REDIS" in k]
    if redis_vars:
        logger.info("Redis-related variables:")
        for var in redis_vars:
            value = os.environ.get(var)
            if "PASSWORD" in var.upper() or "SECRET" in var.upper():
                value = "********"
            logger.info(f"  {var}={value}")
    
    logger.info("================================")

# Log environment at startup
log_environment_variables()

# Also register to log environment at exit
atexit.register(log_environment_variables)
"""
    
    with open(monitor_path, 'w') as f:
        f.write(monitor_content)
    
    print(f"{GREEN}[SUCCESS]{RESET} Created environment monitor at {monitor_path}")
    
    # Now update app/__init__.py to import the monitor
    init_file = Path('app/__init__.py')
    if not init_file.exists():
        print(f"{RED}[ERROR]{RESET} app/__init__.py file not found")
        return False
    
    # Read the current content
    with open(init_file, 'r') as f:
        content = f.read()
    
    # Check if already importing the monitor
    if "import app.env_monitor" in content:
        print(f"{YELLOW}[ALREADY IMPORTING]{RESET} app/__init__.py already imports env_monitor")
        return True
    
    # Find the appropriate insertion point - after other imports
    lines = content.splitlines()
    import_section_end = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            import_section_end = i + 1
    
    # Insert the import
    patched_content = '\n'.join(lines[:import_section_end]) + '\n\n# Monitor environment variables\nimport app.env_monitor  # noqa\n\n' + '\n'.join(lines[import_section_end:])
    
    # Write the patched file
    with open(init_file, 'w') as f:
        f.write(patched_content)
    
    print(f"{GREEN}[SUCCESS]{RESET} Updated app/__init__.py to import environment monitor")
    return True

def main():
    """Main function"""
    print(f"{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}[ENVIRONMENT VARIABLE LOADING FIX]{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")
    
    # First verify environment variables
    verify_environment_variables()
    
    # Apply patches
    patch_config_file()
    modify_app_init()
    create_env_monitor()
    
    print(f"\n{YELLOW}[FIX COMPLETE]{RESET}")
    print(f"{YELLOW}[NEXT STEPS]{RESET}")
    print(f"1. Restart the backend: {BLUE}docker-compose restart backend{RESET}")
    print(f"2. Check logs to verify environment loading: {BLUE}docker-compose logs -f backend{RESET}")
    print(f"3. Test WebSocket connection: {BLUE}python test_websocket_simple.py{RESET}")
    print(f"4. Test login functionality in the frontend")

if __name__ == "__main__":
    main()
