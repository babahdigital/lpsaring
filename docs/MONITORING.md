# MONITORING & ALERTING INFRASTRUCTURE
**Last Updated**: 2026-03-22 | **Status**: Partial (upgrade in progress)

---

## Current Monitoring Stack

```
✅ Active
├─ Docker health checks        (5-60 sec intervals)
├─ Celery DLQ monitoring      (every 15 min, WA alert)
├─ Flask error logging        (JSON format to stdout)
├─ Nginx access/error logs    (files: /home/abdullah/nginx/logs/)
├─ Redis INFO metrics         (manual: redis-cli INFO)
└─ PostgreSQL activity        (manual: CHECK via psql)

⚠️  Partial
├─ Metrics export             (NO Prometheus)
├─ Dashboards                 (NO Grafana/DataDog)
└─ APM                        (NO tracing, just logs)

❌ Missing
├─ Slack/Discord webhooks
├─ SMS alerts for P0 issues
├─ Uptime/SLA monitoring
└─ Distributed tracing
```

---

## Key Metrics & Thresholds

### System Health

| Metric | Current | Alert (Yellow) | Critical (Red) |
|--------|---------|---|---|
| **CPU Usage** | — | > 70% | > 90% |
| **Memory Usage** | 3.8 GB / 7.8 GB (49%) | > 80% | > 95% |
| **Disk Usage** | 27 GB / 77 GB (35%) | > 80% | > 95% |
| **Redis Fragmentation** | 3.21 | > 2.0 | > 4.0 |
| **Swap Used** | 2.5 MB | > 10 MB | > 100 MB |

### Application Health

| Metric | Current | Alert | Critical |
|--------|---------|-------|----------|
| **Celery DLQ Length** | 0–2 | > 10 | > 100 |
| **Task Failure Rate** | 0.8% | > 2% | > 5% |
| **API Response Time (p95)** | 245 ms | > 500 ms | > 2000 ms |
| **API Error Rate (5xx)** | < 0.1% | > 0.5% | > 1% |
| **PostgreSQL Connections** | ~5–10 | > 12 | > 15 |
| **Nginx Error Count (5min)** | 0–5 | > 20 | > 50 |

---

## DLQ Alert System (ACTIVE)

**How it Works**:
```
Every 15 minutes:
  1. dlq_health_monitor_task runs (Celery beat)
  2. Check Redis DLQ size: LLEN celery:dlq
  3. If > 0: Send WhatsApp to superadmin
  4. Throttle alerts: 1 per 60 min to avoid spam
```

**WA Alert Format**:
```
⚠️ *ALERT: Celery DLQ tidak kosong*

📊 **Data**:
- DLQ Length: 15 messages
- Last Error: enforce_overdue_debt_block_task
- Timestamp: 2026-03-22 07:30 UTC

🔧 **Action**:
1. Check logs: docker logs hotspot_prod_celery_worker
2. Restart worker if stuck: docker restart hotspot_prod_celery_worker
3. Monitor recovery: redis-cli LLEN celery:dlq

⏰ Next alert: 2026-03-22 08:30 (if DLQ not cleared)
```

**Configuration**:
```
Setting: TASK_DLQ_ALERT_THROTTLE_MINUTES = 60
Admin WA: stored in DB (settings table)
Retry: 3 attempts if WA send fails
```

---

## Logging & Log Analysis

### Log Locations

```
Files:
  /home/abdullah/nginx/logs/error.log              (Nginx global)
  /home/abdullah/nginx/logs/lpsaring_access.log    (Lpsaring HTTP)
  /home/abdullah/nginx/logs/lpsaring_error.log     (Lpsaring errors — if any)
  Docker stdout (streamed via docker logs):
    hotspot_prod_flask_backend   → Flask app + gunicorn
    hotspot_prod_celery_worker   → Worker tasks
    hotspot_prod_celery_beat     → Beat scheduler
    hotspot_prod_postgres_db     → PostgreSQL logs
    hotspot_prod_redis_cache     → Redis logs
```

### Log Format (JSON)

```json
{
  "timestamp": "22-03-2026 07:17:01",
  "level": "INFO",
  "logger": "app.tasks",
  "message": "Celery Task: Memulai sinkronisasi kuota...",
  "request_id": "uuid-or-N/A_NoRequestCtx",
  "exc_info": null
}
```

### Useful Log Queries

```bash
# Filter error spike in last 1 hour
docker logs --since 1h hotspot_prod_flask_backend | grep "ERROR\|CRITICAL" | wc -l

# Track sync task performance
docker logs -f hotspot_prod_celery_worker | grep "sync_hotspot_usage"

# Monitor webhook processing
docker logs -f hotspot_prod_flask_backend | grep "webhook\|Midtrans"

# Check DLQ activity
docker logs -f hotspot_prod_celery_worker | grep "DLQ"
```

---

## Proposed Alerting Upgrades (Q2 2026)

### 1. Slack Integration

```python
# backend/app/services/slack_service.py (NEW)
def send_slack_alert(channel: str, severity: str, message: str):
    """Send alert to Slack #ops channel."""
    webhook_url = settings_service.get_setting("SLACK_WEBHOOK_URL")
    # POST to webhook with timestamp, severity color, message
```

**Configuration**:
```
Setting: SLACK_WEBHOOK_URL = "https://hooks.slack.com/..."
Channel: #ops (or #p0-alerts for critical)
Severity colors: green (info), yellow (warning), red (critical)
```

### 2. Prometheus Metrics Export

```yaml
# backend/config.py (NEW)
from prometheus_client import Counter, Histogram, Gauge

# Metrics
task_execution_time = Histogram("celery_task_duration_seconds", "Task duration")
dql_length = Gauge("celery_dlq_length", "Dead Letter Queue size")
mikrotik_failures = Counter("mikrotik_connection_failures_total", "Failed connects")
```

**Endpoints**:
```
/metrics  → Prometheus-format metrics
/health   → Health check (200 if all systems OK)
```

### 3. Uptime Monitoring

```python
# Create synthetic checks every 5 min
# Check: GET /api/me (requires auth)
# Check: GET /health (health endpoint)
# If fails 2x consecutively → Alert
```

---

## Dashboard Recommendations

### Grafana Dashboard (future)

**Panels**:
1. **System Health** (top-left)
   - CPU, Memory, Disk usage (gauges)

2. **API Performance** (top-right)
   - Response time p50/p95/p99 (line chart)
   - Request rate (req/sec)

3. **Task Stats** (bottom-left)
   - Task count per type (bar chart)
   - Failure vs success ratio (pie chart)
   - DLQ length (time series)

4. **Database** (bottom-right)
   - Active connections (gauge)
   - Query latency (histogram)
   - Replication lag (if applicable)

### Manual Dashboard (current)

```bash
# Watch key metrics every 10 seconds
watch -n 10 bash -c '
echo "=== SYSTEM HEALTH ==="
docker stats --no-stream | head -5

echo -e "\n=== REDIS MEMORY ==="
docker exec hotspot_prod_redis_cache redis-cli INFO memory | grep "used_memory_human\|mem_fragmentation"

echo -e "\n=== CELERY DLQ ==="
docker exec hotspot_prod_redis_cache redis-cli LLEN celery:dlq

echo -e "\n=== POSTGRES CONNECTIONS ==="
docker exec hotspot_prod_postgres_db psql -U lpsaring_admin -d lpsaring_prod -c "SELECT count(*) FROM pg_stat_activity"
'
```

---

## Alert Fatigue Prevention

**Current Approach**:
- Throttle: 1 DLQ alert per 60 min
- Filter: Only alert if metric truly abnormal
- Escalate: P0 → SMS only if repeated (not implemented yet)

**Future**:
- Correlate related alerts (don't alert both "high RAM" AND "high swap" separately)
- Alert cooldown: 15 min between same alert type
- Smart escalation: page on-call only for P0 + not-auto-recoverable

---

## Monitoring Checklist — Weekly

**Every Monday 09:00**:
- [ ] Review last 7 days of error logs for patterns
- [ ] Check if any alerts were missed (compare alert log vs actual failures)
- [ ] Update threshold if needed based on new normal

**Every Friday EOD**:
- [ ] Generate 1-week uptime report
- [ ] Check SLA: target 99.9% → actual?
- [ ] List any incidents for post-mortem

---

## Integration with RUNBOOKS.md

When incident detected, refer to runbook:
- **DLQ > 100** → See "P0: Celery DLQ Backlog Critical"
- **Redis fragmentation > 3.0** → See "P1: Redis Memory Fragmentation"
- **Postgres connection pool exhausted** → See "P0: PostgreSQL Connection Pool"

---

## Configuration Values (Prod)

```
# backend/.env.prod
TASK_DLQ_ALERT_THROTTLE_MINUTES=60
ADMIN_WA_SUPERADMIN=<stored in DB>
LOG_LEVEL=INFO
LOG_TO_FILE=True
LOG_DIR=/app/logs
SQLALCHEMY_ECHO=False
```

```
# docker-compose.prod.yml
environment:
  # Logging
  LOG_FORMAT_JSON=True
  LOG_LEVEL=INFO
  # Monitoring/Health
  HEALTHCHECK_TIMEOUT=10
  HEALTHCHECK_INTERVAL=30
```

---

## Next Steps

1. **This Week**: Verify all current metrics are accessible via logs
2. **Next Month**: Implement Slack webhook integration
3. **Q2 2026**: Add Prometheus metrics + basic Grafana dashboard

---

*Maintained by: DevOps Team | Last Review: 2026-03-22*
