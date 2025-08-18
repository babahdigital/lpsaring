# Backend Service Documentation

## Environment Variables (Extended)

Core:
- DATABASE_URL: Database connection string.
- SECRET_KEY / JWT_SECRET_KEY: Security keys.

MikroTik & Lookup:
- MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD, MIKROTIK_PORT
- MIKROTIK_CONNECT_TIMEOUT_SECONDS (default 3)
- MIKROTIK_READ_TIMEOUT_SECONDS (default 5)
- MIKROTIK_POOL_SIZE (default 1)
- MIKROTIK_LOOKUP_PARALLEL (true/false)
- MIKROTIK_ASYNC_MODE (true/false) Fallback asynchronous lookup mode via thread executor.

Caching & Grace:
- MAC_LOOKUP_CACHE_TTL (default 300)
- MAC_POSITIVE_GRACE_SECONDS (in-memory grace reuse, default 90)
- MAC_NEGATIVE_TTL (negative cache TTL, default 20)
- MIKROTIK_GRACE_MAX_ENTRIES (cap of in-memory positive cache)

Adaptive Grace:
- MAC_GRACE_MIN_SECONDS
- MAC_GRACE_ADAPT_DECAY
- MAC_GRACE_FORCE_WINDOW_SECONDS
- MIKROTIK_FORCE_REFRESH_CLEAR_GRACE

Redis / Pipelining:
- REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
- REDIS_PIPELINE_BATCH_SIZE (0 = disabled; e.g. 20 to enable pipelined setex)

Metrics:
- ENABLE_INTERNAL_METRICS (default true)
- METRICS_BASIC_AUTH (user:pass)
- METRICS_LATENCY_BUCKETS (e.g. "5,10,25,50,100,250,500,1000,2000")

Warm Cache Task:
- WARM_MAC_ENABLED (default true)
- WARM_MAC_BATCH_SIZE
- WARM_MAC_INTERVAL_MINUTES

Address List Sync:
- ADDRESS_LIST_BATCH_SIZE
- ADDRESS_LIST_BATCH_SLEEP_MS

Log Suppression:
- LOG_SUPPRESSION_THRESHOLD
- LOG_SUPPRESSION_WINDOW_SECONDS
- SUPPRESS_API_DOCS_SKIP_LOG

Ratelimit:
- RATELIMIT_ENABLED
- API_RATE_LIMIT (pattern e.g. "200 per day;50 per hour;10 per minute")

## Metrics Reference
| Metric | Type | Description |
|--------|------|-------------|
| mac_lookup_total | counter | Total MAC lookup attempts |
| mac_lookup_cache_hits | counter | Redis cache hits |
| mac_lookup_cache_grace_hits | counter | In-memory grace hits |
| mac_lookup_fail | counter | Exceptions or fatal lookup failures |
| mac_lookup_duration_ms_sum | counter | Cumulative lookup duration (ms) |
| mac_lookup_duration_bucket{le="X"} | histogram | Raw ms buckets (cumulative) |
| mac_lookup_duration_seconds_bucket{le="X"} | histogram | Prometheus seconds alias |
| mac_lookup_duration_seconds_sum | counter | Sum in seconds |
| mac_lookup_duration_seconds_count | counter | Observation count |
| mac_grace_cache_size | gauge | Current grace cache size |
| mac_lookup_failure_ratio | gauge | Fail/total ratio |

## New Lightweight Endpoints (Frontend Harmonization)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/metrics/brief` | GET | Ringkas: total lookup, rasio gagal, ukuran grace cache, durasi sum. Digunakan UI untuk polling ringan. |
| `/api/version` | GET | Versi build dan feature flags aktif (redis_pipelining, async_lookup, gauges, histogram alias). |
| `/api/users/<id>/devices/summary` | GET | Ringkasan perangkat user: daftar MAC/IP dan last_seen_at terbaru. |

All return JSON stable schema untuk konsumsi frontend; perubahan schema wajib versi baru.

### Swagger / Docs
Route telah otomatis terdaftar di Swagger ( `/api/swagger` ) bila docstring ditambah. Tambahkan docstring singkat pada view untuk muncul di spec.

## Alerting Suggestions
Example Prometheus alert (failure ratio > 0.2 for 5m):
```
alert: HighMacLookupFailureRatio
expr: mac_lookup_failure_ratio > 0.2
for: 5m
labels:
  severity: warning
annotations:
  summary: "High MAC lookup failure ratio"
  description: "Failure ratio > 20% for 5 minutes. Investigate MikroTik connectivity or cache health."
```

Grace cache size unusual growth:
```
alert: GraceCacheSizeSpike
expr: mac_grace_cache_size > 0.9 * MIKROTIK_GRACE_MAX_ENTRIES
for: 10m
labels:
  severity: info
annotations:
  summary: "Grace cache near capacity"
  description: "Consider increasing MIKROTIK_GRACE_MAX_ENTRIES or investigating churn."
```
