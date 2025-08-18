# Hotspot Portal Patches

This directory contains patches and hotfixes for critical issues in the Hotspot Portal application.

## Available Patches

### Auth Bypass Patch
**File**: `fixed_auth_patch.py`

**Purpose**: Fixes login loop issue by bypassing device authorization requirements.

**Usage**:
```bash
# From project root directory
docker-compose exec backend python /app/patches/fixed_auth_patch.py

# Restart backend service after applying patch
docker-compose restart backend
```

### Environment Variables Patch
**File**: `env_patch.py`

**Purpose**: Directly sets critical environment variables in memory for troubleshooting.

**Usage**:
```bash
# Use this as a wrapper when starting the application
docker-compose exec backend python /app/patches/env_patch.py run.py
```

## Restoration

To restore the original behavior after applying patches:

1. Restore from the automatically created backups:
```bash
# Replace TIMESTAMP with the actual timestamp from the backup filename
docker-compose exec backend cp /app/app/infrastructure/http/auth_routes.py.bak.TIMESTAMP /app/app/infrastructure/http/auth_routes.py
docker-compose restart backend
```

2. Or set the correct environment variables in `.env.override`:
```
# To re-enable device authorization:
REQUIRE_EXPLICIT_DEVICE_AUTH=True
```

## Documentation

Full documentation on these patches and the issues they resolve can be found in:
- `/docs/LOGIN_LOOP_FIX.md`

## Testing Tools

For testing and diagnosis, see the testing scripts located at:
- `/backend/tests/scripts/direct_redis_test.py`
- `/backend/tests/scripts/env_monitor.py`
