# RUNBOOKS — Incident Response Procedures
**Last Updated**: 2026-03-22 | **Status**: Active

---

## 📋 Quick Reference

| Incident | Check | Fix | Monitor |
|----------|-------|-----|---------|
| MikroTik timeout | `docker logs hotspot_prod_flask_backend` | Restart MikroTik client pool | `docker exec ... redis-cli GET mikrotik:pool:state` |
| DLQ backlog > 100 | `docker exec ... redis-cli LLEN celery:dlq` | Check celery_worker logs | Alert configured at 100+ messages |
| PostgreSQL slow | `docker stats hotspot_prod_postgres_db` | Check connections: `SELECT count(*) FROM pg_stat_activity` | Commit transaction count |
| Redis fragmentation | `docker exec ... redis-cli INFO memory` | Run `redis-cli MEMORY PURGE` | Check `mem_fragmentation_ratio` (target < 1.5) |
| User stuck in debt-block loop | Check `dhcp_self_healed` trend in Celery logs | Manual unblock via admin API | Policy parity guard remediation |
| Temporary PDF link returns 502 | Check `docker logs global-nginx-proxy` | Temp link expires, user must request new | Add retry UI or longer TTL |

---

## P0 INCIDENTS — Immediate Action

### 1. MikroTik Auth Failure (Connection Lost)

**Detection**:
```
docker logs hotspot_prod_flask_backend | grep -i "mikrotik\|connection\|auth"
# Look for: "Failed to connect", "Authentication failed", "Pool connection error"
```

**Quick Fix** (1–2 min):
```bash
# 1. Check MikroTik server is reachable
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31
ping -c 1 10.19.83.2  # MikroTik IP from config

# 2. Restart circuit breaker + pool (no manual restart needed, auto-recover on next task)
# Circuit breaker will retry in 60-120 seconds

# 3. If persists > 5 min, manually restart circuit breaker:
docker exec hotspot_prod_flask_backend python3 -c "
from app.infrastructure.gateways.mikrotik_client import reset_pool
reset_pool()
print('Circuit breaker reset. Next task will reconnect.')
"

# 4. Monitor recovery
docker logs -f hotspot_prod_flask_backend | grep "RouterOsApiPool"
```

**Monitor**: Check if `sync_unauthorized_hosts` task completes successfully in next cycle (~1 min).

---

### 2. Celery DLQ Backlog Critical (> 100 messages)

**Detection**:
```bash
# SSH to server
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31

# Check DLQ size
docker exec hotspot_prod_redis_cache redis-cli LLEN celery:dlq
# If > 100, escalate immediately
```

**Action Plan**:
```bash
# 1. Check what task failed
docker exec hotspot_prod_redis_cache redis-cli LRANGE celery:dlq 0 9
# Shows last 10 failed task payloads

# 2. Check Celery worker health
docker ps | grep celery
docker logs hotspot_prod_celery_worker | grep "ERROR\|CRITICAL" | tail -30

# 3. If worker is stuck/unhealthy, restart it
docker restart hotspot_prod_celery_worker
# This will drain DLQ on next cycle (dlq_health_monitor_task runs every 15 min)

# 4. Monitor DLQ status
watch -n 10 'docker exec hotspot_prod_redis_cache redis-cli LLEN celery:dlq'
```

**Escalation**: If DLQ doesn't drain within 30 min, contact database team to check PostgreSQL availability.

---

### 3. PostgreSQL Connection Pool Exhausted

**Detection**:
```bash
# From MikroTik error logs or Flask 500 errors
docker logs hotspot_prod_flask_backend | grep "could not translate host\|pool exhausted"

# Check active connections
docker exec hotspot_prod_postgres_db psql -U lpsaring_admin -d lpsaring_prod -c "
SELECT count(*) as active_connections FROM pg_stat_activity;
SELECT datname, count(*), state FROM pg_stat_activity GROUP BY datname, state ORDER BY count(*) DESC;
"
```

**Quick Remediation**:
```bash
# 1. Kill idle connections (safer)
docker exec hotspot_prod_postgres_db psql -U lpsaring_admin -d lpsaring_prod -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'lpsaring_prod' AND state = 'idle' AND query_start < NOW() - INTERVAL '10 minutes';"

# 2. Check connection pool size in Flask (gunicorn)
docker logs hotspot_prod_flask_backend | grep "pool_size\|max_overflow"
# Current: pool_size=5, max_overflow=10 (total 15 connections)

# 3. If exhausted, restart Flask backend
docker restart hotspot_prod_flask_backend
# Waits for healthcheck (10s timeout) before declaring healthy
```

**Recovery Time**: 15–30 seconds for restart and reconnection.

---

## P1 INCIDENTS — Within 1 Hour

### 4. Redis Memory Fragmentation > 3.0

**Detection**:
```bash
docker exec hotspot_prod_redis_cache redis-cli INFO memory | grep mem_fragmentation_ratio
```

**Action**:
```bash
# During LOW TRAFFIC HOUR (preferably night)
# This command is slow (~1-2 seconds)
docker exec hotspot_prod_redis_cache redis-cli MEMORY PURGE

# Monitor the change
watch -n 5 'docker exec hotspot_prod_redis_cache redis-cli INFO memory | grep mem_fragmentation'
# Should drop from 3.x to ~1.2–1.5 range

# If ratio still > 2.0 after 1 hour:
docker restart hotspot_prod_redis_cache
# This clears all in-memory sessions (OTP tokens) but short-lived anyway (~30 min expiry)
```

---

### 5. DHCP Self-Heal Loop (dhcp_self_healed > 20 per cycle)

**Detection**:
```bash
docker logs hotspot_prod_celery_worker | grep "dhcp_self_healed" | tail -10
```

**Investigation**:
```bash
# 1. Check if users repeatedly reconnecting (LAA MAC randomization)
docker logs hotspot_prod_celery_worker --since 1h | grep "DHCP\|waiting\|LAA"

# 2. Check if DHCP leases cleanup working
docker logs hotspot_prod_celery_worker --since 30m | grep "cleanup_waiting_dhcp"
# Look for: "lease_removed=X" — should reflect waiting_candidates

# 3. If abnormal, check MikroTik logs
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31
ssh -u admin 10.19.83.2  # SSH into MikroTik
/ip dhcp-server lease print where dynamic=true status=waiting
# Count waiting leases — if > 30, problem is lease expiry queue
```

**Fix**: Usually self-resolving after 1–2 hrs as DHCP waits list drains. If persistent, restart parity guard at low traffic:
```bash
docker exec hotspot_prod_celery_worker celery -A app.celery_app call policy_parity_guard_task
```

---

## P2 INCIDENTS — Within Business Day

### 6. Temp PDF Link Returns 502 During Deploy

**Context**: Happens when user clicks "Download Report" link from email right as deployment happens (5–10 min window).

**Prevention**: Document in help center that links expire after 1 hour. Reopen report from admin panel instead of email link.

**Fix**: None needed — links auto-expire and user can re-request. Consider:
- Longer link TTL (1 hour → 24 hours) for easier access
- Link "Refresh" button in email template

---

## Runbook Maintenance

**Update When**:
- New incident occurs and handled
- New service/dependency added
- Threshold changes (DLQ limit, fragmentation ratio, etc.)
- New automatic remediation added (tasks, alerts)

**Owner**: On-call engineer for current deployment (check `PRODUCTION_OPERATIONS.md`).

---

*Last Updated: 2026-03-22 by Claude Code Audit*
