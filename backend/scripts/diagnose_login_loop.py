"""
This script diagnoses login flow issues by checking:
1. Backend environment configuration 
2. Redis connectivity
3. Device authorization settings

Run this script with Docker:
docker-compose exec backend python scripts/diagnose_login_loop.py
"""

import os
import sys
import json
import socket
import requests
import redis
from datetime import datetime

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def check_file(filepath):
    """Check if a file exists and is readable"""
    exists = os.path.exists(filepath)
    print(f"{GREEN if exists else RED}[FILE]{RESET} {filepath}: {'EXISTS' if exists else 'MISSING'}")
    return exists

def check_env_vars():
    """Check critical environment variables"""
    print(f"{YELLOW}[CHECKING ENVIRONMENT VARIABLES]{RESET}")
    
    env_vars = {
        "REDIS_URL": os.getenv("REDIS_URL", "Not set"),
        "POSTGRES_URL": os.getenv("POSTGRES_URL", "Not set"),
        "SESSION_TYPE": os.getenv("SESSION_TYPE", "Not set"),
        "REQUIRE_EXPLICIT_DEVICE_AUTH": os.getenv("REQUIRE_EXPLICIT_DEVICE_AUTH", "Not set"),
        "FLASK_ENV": os.getenv("FLASK_ENV", "Not set"),
        "FLASK_DEBUG": os.getenv("FLASK_DEBUG", "Not set"),
    }
    
    all_set = True
    for var, value in env_vars.items():
        status = GREEN if value != "Not set" else RED
        print(f"{status}[ENV]{RESET} {var}: {value}")
        if value == "Not set" and var != "FLASK_DEBUG":  # FLASK_DEBUG is optional
            all_set = False
    
    # Special check for critical login vars
    if env_vars["REQUIRE_EXPLICIT_DEVICE_AUTH"] == "True":
        print(f"{YELLOW}[WARNING]{RESET} REQUIRE_EXPLICIT_DEVICE_AUTH is set to True, which may cause login loops if the device authorization flow isn't properly handled")

    # Check if .env.override exists and if REQUIRE_EXPLICIT_DEVICE_AUTH is set there
    override_path = ".env.override"
    if os.path.exists(override_path):
        try:
            with open(override_path, 'r') as f:
                override_content = f.read()
                if "REQUIRE_EXPLICIT_DEVICE_AUTH" in override_content:
                    print(f"{BLUE}[INFO]{RESET} REQUIRE_EXPLICIT_DEVICE_AUTH is overridden in .env.override")
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to read .env.override: {e}")
    
    return all_set

def check_redis_connection():
    """Check Redis connectivity"""
    print(f"\n{YELLOW}[CHECKING REDIS CONNECTION]{RESET}")
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")
    print(f"{BLUE}[INFO]{RESET} Redis URL: {redis_url}")
    
    try:
        r = redis.from_url(redis_url, decode_responses=True)
        ping_result = r.ping()
        
        if ping_result:
            print(f"{GREEN}[SUCCESS]{RESET} Redis ping successful!")
            # Check for existing keys
            key_count = len(r.keys("*"))
            print(f"{BLUE}[INFO]{RESET} Redis has {key_count} keys")
            
            # Try setting and getting a value
            test_value = f"test-{datetime.now().isoformat()}"
            r.set("diagnose_test_key", test_value, ex=60)  # Expire in 60 seconds
            get_value = r.get("diagnose_test_key")
            
            if get_value == test_value:
                print(f"{GREEN}[SUCCESS]{RESET} Redis set/get operations successful")
            else:
                print(f"{RED}[ERROR]{RESET} Redis set/get mismatch: set '{test_value}', got '{get_value}'")
            
            # Check for session keys specifically
            session_count = len(r.keys("session:*"))
            print(f"{BLUE}[INFO]{RESET} Redis has {session_count} session keys")
            
        else:
            print(f"{RED}[ERROR]{RESET} Redis ping failed!")
        
        return ping_result
    
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Redis connection failed: {e}")
        return False

def check_tcp_connectivity():
    """Check raw TCP connectivity to critical services"""
    print(f"\n{YELLOW}[CHECKING TCP CONNECTIVITY]{RESET}")
    
    services = {
        "redis": ("redis", 6379),
        "postgres": ("postgres", 5432),
        "backend": ("backend", 5000),
        "frontend": ("frontend", 3000),
        "nginx": ("nginx", 80),
    }
    
    for name, (host, port) in services.items():
        try:
            start = datetime.now()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex((host, port))
            end = datetime.now()
            duration = (end - start).total_seconds()
            
            if result == 0:
                print(f"{GREEN}[SUCCESS]{RESET} {name} ({host}:{port}) is reachable (took {duration:.3f}s)")
            else:
                print(f"{RED}[ERROR]{RESET} {name} ({host}:{port}) is NOT reachable, error code: {result}")
            
            s.close()
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to check {name}: {e}")

def check_auth_flow_status():
    """Check authorization flow configuration"""
    print(f"\n{YELLOW}[CHECKING AUTH FLOW CONFIGURATION]{RESET}")
    
    auth_routes_path = "app/infrastructure/http/auth_routes.py"
    if not os.path.exists(auth_routes_path):
        print(f"{RED}[ERROR]{RESET} Cannot find auth_routes.py file")
        return False
    
    try:
        with open(auth_routes_path, 'r') as f:
            content = f.read()
            
        # Check for explicit device authorization code
        require_auth_pattern = "if current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH')"
        device_unregistered_pattern = "DEVICE_UNREGISTERED"
        sync_device_pattern = "@auth_blueprint.route('/sync-device'"
        
        has_require_auth = require_auth_pattern in content
        has_device_unregistered = device_unregistered_pattern in content
        has_sync_device = sync_device_pattern in content
        
        if has_require_auth:
            print(f"{BLUE}[INFO]{RESET} Auth routes contains explicit device authorization check")
        else:
            print(f"{RED}[ERROR]{RESET} Missing explicit device authorization check in auth_routes.py")
        
        if has_device_unregistered:
            print(f"{BLUE}[INFO]{RESET} Auth routes has DEVICE_UNREGISTERED status")
        else:
            print(f"{RED}[ERROR]{RESET} Missing DEVICE_UNREGISTERED status in auth_routes.py")
        
        if has_sync_device:
            print(f"{BLUE}[INFO]{RESET} Auth routes has /sync-device endpoint")
        else:
            print(f"{RED}[ERROR]{RESET} Missing /sync-device endpoint in auth_routes.py")
            
        return has_require_auth and has_device_unregistered and has_sync_device
        
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to analyze auth_routes.py: {e}")
        return False

def create_override_fix():
    """Create an .env.override file to disable explicit device authorization"""
    print(f"\n{YELLOW}[CREATING FIX FOR LOGIN LOOP]{RESET}")
    
    override_path = ".env.override"
    
    try:
        # Check if file already exists and read its content
        existing_content = ""
        if os.path.exists(override_path):
            with open(override_path, 'r') as f:
                existing_content = f.read()
                print(f"{BLUE}[INFO]{RESET} Existing .env.override file found")
        
        # Check if already has REQUIRE_EXPLICIT_DEVICE_AUTH setting
        if "REQUIRE_EXPLICIT_DEVICE_AUTH=" in existing_content:
            print(f"{BLUE}[INFO]{RESET} .env.override already contains REQUIRE_EXPLICIT_DEVICE_AUTH setting")
            print(f"{YELLOW}[ACTION]{RESET} To fix login loop, ensure it's set to REQUIRE_EXPLICIT_DEVICE_AUTH=False")
            return
        
        # Add our setting
        with open(override_path, 'w') as f:
            if existing_content and not existing_content.endswith("\n"):
                existing_content += "\n"
            
            new_content = existing_content + "# Added by diagnostic script to fix login loop issue\nREQUIRE_EXPLICIT_DEVICE_AUTH=False\n"
            f.write(new_content)
        
        print(f"{GREEN}[SUCCESS]{RESET} Created .env.override with REQUIRE_EXPLICIT_DEVICE_AUTH=False")
        print(f"{YELLOW}[IMPORTANT]{RESET} You need to restart the backend container for this to take effect:")
        print(f"{BLUE}docker-compose restart backend{RESET}")
        
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to create .env.override: {e}")

def print_summary(results):
    """Print summary of checks"""
    print(f"\n{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}[DIAGNOSIS SUMMARY]{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")
    
    success_count = sum(1 for r in results.values() if r)
    total_count = len(results)
    
    print(f"Passed: {success_count}/{total_count} checks")
    
    for check, result in results.items():
        status = GREEN if result else RED
        print(f"{status}[{'✓' if result else '✗'}]{RESET} {check}")
    
    print(f"\n{YELLOW}[DIAGNOSIS RESULT]{RESET}")
    if results.get("env_vars", False) and not results.get("require_explicit_auth", True):
        print(f"{GREEN}[RECOMMENDATION]{RESET} Login loop likely caused by REQUIRE_EXPLICIT_DEVICE_AUTH=True")
        print(f"{GREEN}[RECOMMENDATION]{RESET} Run with --fix to create .env.override with REQUIRE_EXPLICIT_DEVICE_AUTH=False")
    elif not results.get("redis_conn", False):
        print(f"{RED}[CRITICAL ISSUE]{RESET} Redis connection failure likely causing login issues")
        print(f"{YELLOW}[RECOMMENDATION]{RESET} Check Redis container status and connectivity")
    else:
        print(f"{YELLOW}[RECOMMENDATION]{RESET} Multiple issues detected, please address them individually")

def main():
    """Main function"""
    print(f"{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}[LOGIN FLOW DIAGNOSTIC TOOL]{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")
    
    # Run checks
    env_check = check_env_vars()
    redis_check = check_redis_connection()
    auth_check = check_auth_flow_status()
    check_tcp_connectivity()
    
    # Determine if REQUIRE_EXPLICIT_DEVICE_AUTH is set to True
    require_explicit_auth = os.getenv("REQUIRE_EXPLICIT_DEVICE_AUTH", "").lower() == "true"
    
    # Store results for summary
    results = {
        "env_vars": env_check,
        "redis_conn": redis_check,
        "auth_config": auth_check,
        "require_explicit_auth": require_explicit_auth
    }
    
    # Print summary
    print_summary(results)
    
    # Apply fix if requested or device auth is required
    if "--fix" in sys.argv or require_explicit_auth:
        create_override_fix()

if __name__ == "__main__":
    main()
