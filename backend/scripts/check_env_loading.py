"""
This script diagnoses environment variable loading issues in the Flask backend
by checking how variables from .env and .env.override are being loaded.
Run with: docker-compose exec backend python scripts/check_env_loading.py
"""

import os
import sys
import glob
import importlib.util

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_env_var(name):
    """Print environment variable value"""
    value = os.environ.get(name, "Not set")
    print(f"{BLUE}{name}{RESET}: {value}")

def load_dotenv(file_path):
    """Load and print contents of a dotenv file"""
    if not os.path.exists(file_path):
        print(f"{RED}[ERROR]{RESET} File {file_path} does not exist")
        return {}
    
    print(f"{YELLOW}[LOADING]{RESET} {file_path}")
    env_vars = {}
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    env_vars[key] = value
                    # Don't show sensitive values
                    if any(x in key.upper() for x in ['SECRET', 'PASSWORD', 'KEY']):
                        print(f"  {key}=********")
                    else:
                        print(f"  {key}={value}")
        
        return env_vars
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to load {file_path}: {e}")
        return {}

def check_flask_dotenv_loading():
    """Check how Flask loads environment variables"""
    print(f"\n{YELLOW}[CHECKING FLASK ENVIRONMENT LOADING]{RESET}")
    
    # Check app initialization files
    init_files = [
        "app/__init__.py",
        "app/bootstrap.py",
        "config.py",
        "run.py"
    ]
    
    dotenv_loaded = False
    for file_path in init_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    if "dotenv" in content or "load_dotenv" in content:
                        print(f"{GREEN}[FOUND]{RESET} dotenv loading in {file_path}")
                        dotenv_loaded = True
                        
                        # Show relevant code snippet
                        for i, line in enumerate(content.splitlines(), 1):
                            if "dotenv" in line or "load_dotenv" in line:
                                print(f"  Line {i}: {line.strip()}")
            except Exception as e:
                print(f"{RED}[ERROR]{RESET} Failed to check {file_path}: {e}")
    
    if not dotenv_loaded:
        print(f"{RED}[WARNING]{RESET} No dotenv loading found in main initialization files")

def check_module_availability():
    """Check if python-dotenv is installed"""
    print(f"\n{YELLOW}[CHECKING PYTHON-DOTENV AVAILABILITY]{RESET}")
    
    try:
        spec = importlib.util.find_spec('dotenv')
        if spec is not None:
            print(f"{GREEN}[FOUND]{RESET} python-dotenv module is available")
            
            # Try to import and check version
            try:
                import dotenv
                print(f"  Version: {dotenv.__version__}")
            except Exception:
                print(f"  Version: unknown")
        else:
            print(f"{RED}[MISSING]{RESET} python-dotenv module is not installed")
            print(f"{YELLOW}[RECOMMENDATION]{RESET} Add python-dotenv to requirements.txt")
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to check for python-dotenv: {e}")

def manually_load_env_files():
    """Manually load .env and .env.override files and compare with current env"""
    print(f"\n{YELLOW}[MANUALLY LOADING ENV FILES]{RESET}")
    
    env_file = ".env"
    override_file = ".env.override"
    
    env_vars = load_dotenv(env_file)
    override_vars = load_dotenv(override_file)
    
    # Merge with override taking precedence
    expected_vars = {**env_vars, **override_vars}
    
    # Compare with actual environment
    print(f"\n{YELLOW}[COMPARING WITH ACTUAL ENVIRONMENT]{RESET}")
    
    for key, expected_value in expected_vars.items():
        actual_value = os.environ.get(key)
        
        # Skip sensitive values
        if any(x in key.upper() for x in ['SECRET', 'PASSWORD', 'KEY']):
            continue
            
        if actual_value is None:
            print(f"{RED}[MISSING]{RESET} {key} - Expected: {expected_value}, Actual: Not set")
        elif actual_value != expected_value:
            print(f"{YELLOW}[MISMATCH]{RESET} {key} - Expected: {expected_value}, Actual: {actual_value}")
        else:
            print(f"{GREEN}[MATCH]{RESET} {key} - Value: {actual_value}")

def create_env_override_fix():
    """Create a fix to manually load .env.override in app initialization"""
    print(f"\n{YELLOW}[CREATING FIX FOR ENV LOADING]{RESET}")
    
    # Find the best place to add the fix
    target_file = None
    priority_files = ["app/__init__.py", "app/bootstrap.py", "config.py", "run.py"]
    
    for file_path in priority_files:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                if "import os" in content and ("app = " in content or "create_app" in content):
                    target_file = file_path
                    break
    
    if not target_file:
        # Default to config.py if we couldn't find a better target
        target_file = "config.py" if os.path.exists("config.py") else "run.py"
    
    print(f"{BLUE}[TARGET]{RESET} Adding .env.override loading code to {target_file}")
    
    # Create the patch file
    patch_content = f"""# Add this code to {target_file} to fix environment variable loading

# Import at the top of the file
import os
from pathlib import Path

# Add this function
def load_env_override():
    \"\"\"Manually load .env.override file to ensure it takes precedence\"\"\"
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
                    value = value.strip().strip('"\\''')
                    os.environ[key] = value

# Call this function early in the initialization process
load_env_override()
"""
    
    with open("env_override_fix.py", "w") as f:
        f.write(patch_content)
    
    print(f"{GREEN}[CREATED]{RESET} env_override_fix.py with code to manually load .env.override")
    print(f"{YELLOW}[MANUAL ACTION NEEDED]{RESET} Copy the code from env_override_fix.py into {target_file}")
    print(f"Place it early in the file, before any Flask app initialization.")

def check_boot_sequence():
    """Analyze how the Flask app is booted and environment loaded"""
    print(f"\n{YELLOW}[ANALYZING BOOT SEQUENCE]{RESET}")
    
    # Check entrypoint.sh
    entrypoint = "entrypoint.sh"
    if os.path.exists(entrypoint):
        print(f"{BLUE}[CHECKING]{RESET} {entrypoint}")
        try:
            with open(entrypoint, 'r') as f:
                content = f.read()
                print("  Found entrypoint.sh, showing contents:")
                print(f"{'-'*40}")
                print(content.strip())
                print(f"{'-'*40}")
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to read {entrypoint}: {e}")
    
    # Check Dockerfile
    dockerfile = "Dockerfile"
    if os.path.exists(dockerfile):
        print(f"{BLUE}[CHECKING]{RESET} {dockerfile}")
        try:
            with open(dockerfile, 'r') as f:
                content = f.read()
                
                # Look for CMD and ENTRYPOINT
                for i, line in enumerate(content.splitlines(), 1):
                    if line.strip().startswith(("CMD", "ENTRYPOINT")):
                        print(f"  Line {i}: {line.strip()}")
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to read {dockerfile}: {e}")

def main():
    """Main function"""
    print(f"{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}[ENVIRONMENT LOADING DIAGNOSTIC TOOL]{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")
    
    # Print current environment variables
    print(f"{YELLOW}[CURRENT ENVIRONMENT]{RESET}")
    print_env_var("REQUIRE_EXPLICIT_DEVICE_AUTH")
    print_env_var("SESSION_TYPE")
    print_env_var("REDIS_URL")
    print_env_var("FLASK_ENV")
    print_env_var("FLASK_DEBUG")
    print_env_var("PYTHONPATH")
    
    # Check dotenv module
    check_module_availability()
    
    # Check Flask dotenv loading
    check_flask_dotenv_loading()
    
    # Manually load env files
    manually_load_env_files()
    
    # Check boot sequence
    check_boot_sequence()
    
    # Create fix
    create_env_override_fix()
    
    print(f"\n{YELLOW}[RECOMMENDATIONS]{RESET}")
    print("1. Make sure python-dotenv is installed and used")
    print("2. Apply the env_override_fix.py code to ensure .env.override is loaded")
    print("3. Restart the backend container after making changes")

if __name__ == "__main__":
    main()
