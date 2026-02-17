# Architecture Diagrams (lpsaring)

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

Dokumen ini berisi diagram (Mermaid) saja, khusus untuk memvisualisasikan flow dan topology produksi.

---

## 1) Production Topology (Docker Compose)

```mermaid
flowchart LR
  U[Client Device\nHP/Laptop] -->|HTTPS| CF[Cloudflare Zero Trust\nTunnel Public Hostname]
  CF -->|tunnel ingress\nhttp://hotspot_nginx_proxy:80| FL[cloudflared\nservice: cloudflared]

  subgraph NET[Docker network: hotspot_prod_net]
    NX[nginx\nservice: nginx\nalias: hotspot_nginx_proxy]
    FE[nuxt\nservice: frontend\n:3010]
    BE[flask\nservice: backend\n:5010]
    CW[celery worker\nservice: celery_worker]
    CB[celery beat\nservice: celery_beat]
    RD[redis\nservice: redis]
    PG[postgres\nservice: db]
    BI[init backups perm\nservice: backups_init]
    MG[db migrate\nservice: migrate]
  end

  FL --> NX

  NX -->|/ (SSR/SPA)| FE
  NX -->|/api/*| BE

  BE <--> RD
  BE <--> PG
  CW <--> RD
  CW <--> PG
  CB <--> RD
  CB <--> PG

  BI --> BE
  MG --> BE

  BE -->|RouterOS API| MT[(MikroTik)]
  BE -->|HTTP| WA[(WhatsApp Gateway)]
  BE -->|HTTP webhook| MID[(Midtrans)]

  NX -->|vhost wartelpas.sobigidul.com\nproxy_pass http://10.10.83.2:8081| WP[(Wartelpas :8081)]
```

---

## 2) Nginx Routing (Prod)

```mermaid
flowchart TB
  R[Incoming request\n(port 80 inside Docker)] --> NX[Nginx\napp.prod.conf]

  NX -->|Host: lpsaring.*\nPath: /api/*| BE[backend:5010]
  NX -->|Host: lpsaring.*\nPath: /_nuxt/*| FE[frontend:3010]
  NX -->|Host: lpsaring.*\nPath: /*| FE

  NX -->|Host: wartelpas.sobigidul.com\nPath: /*| WP[10.10.83.2:8081]

  NX -.->|sets headers| H[Host, X-Real-IP,\nX-Forwarded-For,\nX-Forwarded-Proto,\nX-Request-ID]
```

---

## 3) Captive → OTP → Binding (End-user)

```mermaid
sequenceDiagram
  autonumber
  participant U as Client (HP)
  participant MT as MikroTik Captive
  participant CF as Cloudflare Tunnel
  participant FL as cloudflared
  participant NX as Nginx
  participant FE as Nuxt (frontend)
  participant BE as Flask API
  participant RD as Redis
  participant PG as Postgres

  MT-->>U: redirect /captive?ip=...&mac=...&link-login-only=...
  U->>CF: GET /captive?... (HTTPS)
  CF->>FL: tunnel ingress
  FL->>NX: HTTP
  NX->>FE: /captive
  FE-->>U: Captive UI

  U->>CF: POST /api/auth/request-otp
  CF->>NX: tunnel -> nginx
  NX->>BE: /api/auth/request-otp
  BE->>RD: store otp + cooldown
  BE-->>U: 200 (OTP sent)

  U->>CF: POST /api/auth/verify-otp (client_ip/client_mac)
  CF->>NX: tunnel -> nginx
  NX->>BE: /api/auth/verify-otp
  BE->>RD: verify otp
  BE->>PG: load user + devices + write login_history
  BE->>MT: resolve MAC/IP (host/active/ARP/DHCP)
  BE->>MT: upsert ip-binding (MAC-only)
  BE->>MT: sync address-list status
  BE-->>U: 200 + Set-Cookie auth_token + refresh_token

  U->>CF: GET /captive/terhubung
  CF->>NX: tunnel
  NX->>FE: /captive/terhubung
  FE-->>U: success page (optional redirect)
```

---

## 4) Auth Cookie Auto-Refresh (Rotating Refresh Token)

```mermaid
sequenceDiagram
  autonumber
  participant U as Browser
  participant NX as Nginx
  participant FE as Nuxt SSR
  participant BE as Flask API
  participant PG as Postgres

  Note over U,BE: Access token missing/expired, refresh cookie still valid
  U->>NX: GET /dashboard (Cookie: refresh_token)
  NX->>FE: SSR page render
  FE->>BE: GET /api/auth/me (Cookie forwarded)

  BE->>PG: rotate refresh_token (single-use)
  BE-->>FE: 200 user + Set-Cookie auth_token + refresh_token(new)
  FE-->>NX: HTML
  NX-->>U: HTML + Set-Cookie
```

---

## 5) Quota Sync (Celery Beat)

```mermaid
sequenceDiagram
  autonumber
  participant CB as Celery Beat
  participant CW as Celery Worker
  participant BE as Flask App Context
  participant RD as Redis
  participant PG as Postgres
  participant MT as MikroTik

  CB-->>CW: schedule sync_hotspot_usage_task (<=60s)
  CW->>BE: create_app() + app_context
  BE->>RD: throttle quota_sync:last_run_ts
  alt Skip interval
    BE-->>CW: return
  else Continue
    BE->>PG: load active approved users + devices
    BE->>MT: fetch /ip/hotspot/host (bytes per MAC)
    loop per user/device
      BE->>RD: read/write quota:last_bytes:mac:<MAC>
      BE->>PG: update total_quota_used_mb + DailyUsageLog
      BE->>MT: set profile + sync address-list status
    end
    BE->>PG: commit
    BE->>RD: set quota_sync:last_run_ts
  end
```
