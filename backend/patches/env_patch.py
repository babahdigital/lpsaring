"""
Direct environment patch to be run before starting the server.
This script directly modifies the environment variables in memory.
"""
import os
import sys
from datetime import datetime

print(f"\n{'=' * 80}")
print(f"DIRECT ENVIRONMENT PATCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'=' * 80}")

# Set critical environment variables directly
os.environ['REQUIRE_EXPLICIT_DEVICE_AUTH'] = 'False'
os.environ['SESSION_TYPE'] = 'redis'
os.environ['REDIS_URL'] = 'redis://redis:6379/1'
os.environ['FLASK_DEBUG'] = 'True'

print("Environment variables set:")
print(f"REQUIRE_EXPLICIT_DEVICE_AUTH: {os.environ.get('REQUIRE_EXPLICIT_DEVICE_AUTH')}")
print(f"SESSION_TYPE: {os.environ.get('SESSION_TYPE')}")
print(f"REDIS_URL: {os.environ.get('REDIS_URL')}")
print(f"FLASK_DEBUG: {os.environ.get('FLASK_DEBUG')}")
print(f"{'=' * 80}\n")

# Continue with normal execution
if len(sys.argv) > 1:
    # If this script is called with arguments, try to execute them
    from runpy import run_module
    module_name = sys.argv[1]
    print(f"Continuing execution with module: {module_name}")
    sys.argv = sys.argv[1:]
    run_module(module_name, run_name="__main__")
