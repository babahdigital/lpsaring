# 2026-03-26 Security Audit — Error Information Leakage & Hardening

## Severity: High (P0/P1/P2)

## Summary

Comprehensive security audit of production logs and codebase revealed multiple categories of issues:

1. **P0**: 11 locations leaking raw `str(e)` (exception details) to HTTP responses — exposing SQL errors, file paths, internal service details to end users/admins
2. **P0**: Vivo SDK spam (113K+ requests/day) via captive portal redirect — not blocked at nginx level
3. **P1**: Telegram webhook secret comparison vulnerable to timing attack (`==` instead of `hmac.compare_digest()`)
4. **P1**: JWT error details leaked in auth decorator response
5. **P2**: f-string interpolation in `sa.text()` SQL fragment (sanitized integer, low risk but bad pattern)

## Impact

- **Security**: Internal exception messages (DB errors, connection strings, file paths) exposed to unauthenticated users
- **Performance**: 113K+ spam requests/day from Vivo SDK consuming backend resources
- **Auth**: Timing side-channel on Telegram webhook secret could allow brute-force token recovery

## Root Cause Analysis

### RC-1: str(e) in HTTP responses (P0 — 11 locations)

Pattern: `except Exception as e:` → `abort(500, description=str(e))` or `jsonify({"error": str(e)})`.

These catch broad `Exception` and return the raw exception message in the HTTP response. A database error, network timeout, or internal logic failure could expose:
- SQL queries and table names
- File system paths
- Internal service URLs and credentials
- Stack trace fragments

### RC-2: Vivo SDK spam not blocked at nginx (P0)

Captive portal redirects all HTTP traffic to `lpsaring.babahdigital.net`. Vivo phones send SDK telemetry to paths like `/client/upload/reportSingleDelay`, which nginx proxies to the frontend (404 but still consumes resources).

### RC-3: Telegram webhook timing attack (P1)

`provided == expected` Python string comparison is not constant-time. An attacker could measure response time differences to recover the webhook secret byte-by-byte.

### RC-4: sa.text() f-string (P2)

`sa.text(f"INTERVAL '{offset_hours} hours'")` — although `offset_hours` was already cast to `int` and clamped to [-12, 14], using f-strings in `sa.text()` is a SQL injection anti-pattern.

## Fixes Applied

### 1. Error message sanitization (11 files)

All `str(e)` in HTTP responses replaced with generic messages. Logger calls preserved for debugging.

| File | Line(s) | Before | After |
|------|---------|--------|-------|
| `initiation_routes.py` | 549, 857 | `abort(500, description=str(e))` | `"Terjadi kesalahan internal..."` |
| `packages_routes.py` | 189 | `"error": str(e)` | Key removed |
| `profile_routes.py` | 90, 174 | `str(e)` in message | Generic messages |
| `authenticated_routes.py` | 159, 246 | `f"Kesalahan tak terduga: {e}"` | Generic message |
| `invoice_routes.py` | 100 | `f"...saat membuat invoice: {e}"` | Generic message |
| `user_management_routes.py` | 1809 | `f"Gagal koneksi MikroTik: {str(e)}"` | Generic message |
| `request_management_routes.py` | 364 | `f"...Error: {str(e)}"` | Generic message |
| `admin_contexts/transactions.py` | 560 | `f"Gagal menghubungi Midtrans: {str(e)}"` | Generic message |
| `decorators.py` | 299 | `f"Invalid token: {str(e)}"` | `"Token tidak valid..."` |

### 2. Nginx SDK spam blocking

Added to `lpsaring.conf`:
```nginx
location ~* ^/(client/upload|taboola|ad/|huawei|reportSingleDelay) {
    access_log off;
    return 444;
}
```
Returns 444 (drop connection) — no response body, no access log noise.

### 3. Telegram webhook timing-safe comparison

```python
import hmac
# Before: return provided == expected
# After:
return hmac.compare_digest(provided, expected)
```

### 4. sa.text() parameterized

```python
# Before: sa.text(f"INTERVAL '{offset_hours} hours'")
# After:
sa.text("INTERVAL '1 hour'") * sa.literal(offset_hours)
```

## Files Changed

| File | Change |
|------|--------|
| `backend/.../transactions/initiation_routes.py` | Sanitize 2 error messages |
| `backend/.../transactions/authenticated_routes.py` | Sanitize 2 error messages |
| `backend/.../transactions/invoice_routes.py` | Sanitize 1 error message |
| `backend/.../packages_routes.py` | Remove `error` key from response |
| `backend/.../user/profile_routes.py` | Sanitize 2 error messages |
| `backend/.../admin/user_management_routes.py` | Sanitize 1 error message |
| `backend/.../admin/request_management_routes.py` | Sanitize 1 error message |
| `backend/.../admin_contexts/transactions.py` | Sanitize 1 error message + fix sa.text() |
| `backend/.../decorators.py` | Sanitize JWT error message |
| `backend/.../telegram_webhook_routes.py` | hmac.compare_digest() |
| `nginx/conf.d/lpsaring.conf` | Block SDK spam paths |

## Testing

- All backend tests: PASS (100%)
- TypeScript check (vue-tsc --noEmit): PASS
- Python compile check: PASS (all 11 files)
- VS Code diagnostics: No new errors

## Rate Limiting Status

Already in place via Flask-Limiter:
- Global default: `200/day; 50/hour; 10/minute` (all endpoints)
- Auth routes: custom per-endpoint limits (5-60/min)
- Transaction routes: `10/min` initiation, `60/min` status
- Midtrans webhook: covered by global default
- Admin endpoints: covered by global default

## Timeline

- **26 Mar 2026** — Security audit initiated from production log analysis
- **26 Mar 2026** — All findings identified and fixed in single session
