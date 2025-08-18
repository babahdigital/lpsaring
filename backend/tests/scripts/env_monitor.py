"""
Environment monitoring module that tracks critical environment variables
during application startup and shutdown to help diagnose configuration issues.
"""
import os
import logging
import atexit

logger = logging.getLogger("env_monitor")

def log_environment_variables():
    """Log critical environment variables"""
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
