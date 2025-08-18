# Hotspot Portal Test Scripts

This directory contains diagnostic and testing scripts for the Hotspot Portal application.

## Available Test Scripts

### Redis Connection Test
**File**: `direct_redis_test.py`

**Purpose**: Tests Redis connectivity, checks environment variables, and can create a `.env.override` file to fix common issues.

**Usage**:
```bash
# From project root directory
docker-compose exec backend python /app/tests/scripts/direct_redis_test.py
```

### Environment Monitor
**File**: `env_monitor.py`

**Purpose**: Monitors and logs critical environment variables during application startup and shutdown.

**Usage**: This script is imported in `app/__init__.py` and runs automatically on application start/stop.

## Related Documentation

Full documentation on these scripts and the issues they help diagnose can be found in:
- `/docs/LOGIN_LOOP_FIX.md`

## Related Patches

For patches that fix issues diagnosed by these scripts, see:
- `/backend/patches/fixed_auth_patch.py`
- `/backend/patches/env_patch.py`
