# PENDING DEVELOPMENT — LPSaring Hotspot Portal

Dokumen ini mencatat semua pengembangan yang sudah dianalisis, didesain, atau sebagian diimplementasi
tapi **belum selesai penuh** atau **perlu tindakan lanjutan**. Update setiap kali item selesai atau di-skip.

> **Update terakhir**: 2026-03-27 (Session 7 — Rate limiting, log retention, WA tracking, DR docs, gap implementation)

---

## STATUS LEGENDA

| Simbol | Arti |
|--------|------|
| ✅ | Selesai & di-deploy |
| ⚙️ | Sudah diimplementasi, perlu deploy |
| 🔍 | Deployed, dalam pemantauan / belum confirmed selesai |
| ⏳ | Dianalisis, belum diimplementasi |
| ℹ️ | Informatif / self-resolve, bukan tindakan admin |
| ❌ | Dibatalkan / tidak relevan |
| ⚠️ | Butuh tindakan manual admin |

---

## P0 — SEGERA (Ops Blocker)

> Tidak ada item P0 aktif saat ini. Semua resolved.

### ✅ Setup Settings Untuk Task Baru
**Status**: SELESAI — ditambahkan ke `.env.prod` (20 Mar 2026, Session 5)
- `AKSES_BANKING_ENABLED=True` → di `.env.prod` server
- `ENABLE_OVERDUE_DEBT_BLOCK=True` → di `.env.prod` server
- `AKSES_BANKING_DOMAINS` dikomen — default 10 bank umum sudah cukup
- **Tidak perlu settings DB** — `settings_service.get_setting(key, default)` resolve: DB → `os.environ` → default

---

### ✅ `price_rp` — Otomatis dari Harga Paket (RESOLVED via Migration)
**Status**: SELESAI — migration `20260319_d_backfill_price_rp_from_note` berjalan otomatis saat deploy.
**Catatan**: Record tanpa note yang cocok tetap NULL → frontend fallback ke `estimated_rp` (by design).

---

## P1 — PENTING (Fungsional Gap)

### ✅ 7.3 Akses-Banking Scheduler — `sync_access_banking_task`
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5)
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Populate `Bypass_Server` address-list MikroTik dengan banking domain IPs setiap hari jam 02:00

**Config aktual (sudah aktif)**:
- `AKSES_BANKING_ENABLED=True` — di `.env.prod` server
- `AKSES_BANKING_DOMAINS` — default hardcode di tasks.py: `klikbca.com,bri.co.id,bankmandiri.co.id,bni.co.id,cimbniaga.co.id,permatabank.co.id,ocbcnisp.com,bca.co.id,danamon.co.id,btn.co.id`
- `AKSES_BANKING_LIST_NAME` — default `Bypass_Server` (tidak perlu di-set)
- Jadwal: `AKSES_BANKING_CRON_HOUR=2` (hardcode di `extensions.py`, bisa override via DB/env)

**MASALAH YANG DI-SOLVE**: User expired/inactive tidak bisa akses banking untuk bayar tagihan.

---

### ✅ Auto-Block Overdue Debt — `enforce_overdue_debt_block_task`
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5)
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Blokir user yang debt-nya melewati `due_date`. Berjalan harian jam 08:00.

**Config aktual (sudah aktif)**:
- `ENABLE_OVERDUE_DEBT_BLOCK=True` — di `.env.prod` server (default code juga `True`)
- Jadwal: `OVERDUE_DEBT_BLOCK_CRON_HOUR=8` (hardcode di `extensions.py`)

---

### ✅ Auto-Unblock Setelah Debt Lunas (19 Mar 2026 — Session 4)
**Status**: SELESAI & DEPLOYED
**File**: `backend/app/infrastructure/http/admin/user_management_routes.py`, `backend/app/utils/block_reasons.py`
**Fungsi**: `settle_single_manual_debt` auto-unblock user jika semua debt lunas.
**Fix**: `is_debt_block_reason` sekarang cover `tunggakan_overdue|` prefix dari overdue block task.

---

### ✅ `price_rp` Auto-Fill dari Paket (RESOLVED)
**Status**: SELESAI — tidak ada validasi manual yang diperlukan.

---

## P2 — NICE TO HAVE (Improvement)

### ✅ Docker Compose Celery Healthcheck + Redis activedefrag
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5)
**File**: `docker-compose.prod.yml`
**Perubahan**:
- `celery_worker`: healthcheck via `celery inspect ping` setiap 60s — **healthy** ✓
- `celery_beat`: healthcheck via `/proc/1/cmdline` (pgrep tidak ada di image) — **healthy** ✓
- `redis`: `--activedefrag yes` — defrag berjalan background sejak deploy

---

### ✅ Naikkan Beat Interval sync_hotspot_usage ke 300s
**Status**: SELESAI — `extensions.py`: `min(sync_interval, 60)` → `max(60, sync_interval)`.

---

### ✅ Log Level "Skip sync address-list" dari INFO ke DEBUG
**Status**: SELESAI — `hotspot_sync_service.py` diubah dari `logger.info` ke `logger.debug`.

---

### ✅ Fix Bug DHCP Loop: Static Lease Dibuat Ulang Terus
**Status**: SELESAI (26 Mar 2026, Session 6) — root cause kedua ditemukan & fixed.
**Root Cause #1** (fix #39): `_snapshot_dhcp_ips_by_mac` skip semua waiting lease → fixed Session 5.
**Root Cause #2** (fix baru): `cleanup_waiting_dhcp_arp_task` punya guard `if last_seen_seconds and ...`
yang falsy ketika `last_seen_seconds=0` (lease baru, never seen). Lease yang baru dicreate oleh self-heal
langsung dihapus → loop 33 device setiap siklus.
**Fix**: Ubah guard menjadi `if last_seen_seconds == 0 or last_seen_seconds < min_last_seen_seconds` —
lease never-seen dianggap "recent" dan di-skip, bukan dihapus.
**File**: `backend/app/tasks.py` line 2565

---

### ✅ Endpoint `/api/admin/mikrotik/verify-rules` (19 Mar 2026 — Session 4)
**Status**: SELESAI (backend route). Admin UI panel belum dibuat.

---

### ✅ Downgrade `no_authorized_device` Priority di Parity Guard
**Status**: SELESAI (20 Mar 2026, sesi ini)
**File**: `backend/app/services/access_parity_service.py`
**Perubahan**: `_build_action_plan()` — `priority: "high"` → `"low"`, `action: "authorize_device_from_admin"` → `"wait_for_user_reconnect"`, `mode: "manual"` → `"informational"`.
Tambah komentar inline di `_is_auto_fixable()` untuk klarifikasi self-heal behavior.

---

### ✅ Admin UI Panel untuk `/api/admin/mikrotik/verify-rules`
**Status**: SELESAI (20 Mar 2026, sesi ini)
**File**: `frontend/pages/admin/mikrotik.vue` (baru), `frontend/navigation/horizontal/admin.ts`
**Fitur**: Halaman `/admin/mikrotik` — verifikasi 4 forward chain firewall rules MikroTik.
Responsive (2-col di md+, stacked di mobile). Chip status, VTable rules, panduan membaca hasil.
Fix type: `MikrotikRuleCheck.rule/index` → `label/position` di `contracts.generated.ts`.

---

### ❌ Investigasi `skipped_not_allowed: 27-31` — BY DESIGN
**Status**: DIBATALKAN — perilaku ini disengaja.
Host hotspot di luar `MIKROTIK_UNAUTHORIZED_CIDRS=['172.16.2.0/23']` memang di-skip oleh
`sync_unauthorized_hosts_task`. Subnet manajemen atau VLAN lain tidak dimonitor karena tidak
dalam scope guard. Bukan bug.
Penjelasan sudah tersedia di Admin UI → halaman MikroTik (card "Panduan Membaca Hasil").

---

### ⏳ Rate Limiting OTP
**Status**: Sudah ada (`5/menit; 20/jam` per phone). Tidak perlu perubahan kecuali ada insiden brute force.

---

### 🔍 MAC Randomization: Proactive Session Token (20 Mar 2026)
**Status**: Deployed (sesi ini), **dalam pemantauan**.
**Background**: Insiden `2026-03-07-mac-randomization-analisa-6282213631573.md`.
**Yang sudah ada**: Deteksi LAA bit + warning dialog di `hotspot-required.vue`.
**Fix diterapkan**: Proactive `session_mac_token` di `onMounted` — token di-set segera jika MAC
terdeteksi randomized & belum ada session binding (sebelum bind pertama berhasil).
File: `frontend/pages/login/hotspot-required.vue` (4 baris setelah `if (sessionBinding)` block).
**Yang masih perlu dipantau**: User `+6281255962309` (MAC `16:5B:A4:E2:9C:1F` = LAA) — apakah
`dhcp_lease_missing` loop berhenti setelah deploy.

---

## MONITORING ONGOING

### Circuit Breaker MikroTik
- Monitor via `dlq_health_monitor_task` (setiap 15 menit)
- Alert WA dikirim ke SUPER_ADMIN jika circuit breaker open

### Policy Parity Guard
- Berjalan setiap 10 menit, durasi ~156–174s untuk 89 user
- **5 user `no_authorized_device`**: self-resolve — sistem fix otomatis saat user konek ulang ke hotspot. Tidak butuh admin action. (lihat ℹ️ bawah)
- `+6281255962309` (MAC randomization LAA) → `dhcp_lease_missing` loop — belum selesai, pending MAC randomization fallback fix

### ℹ️ 6 User Tanpa Device Terdaftar
User berikut muncul di log parity guard tiap 10 menit sebagai `no_authorized_device`:
`+6285752083738`, `+6285751420446`, `+6281528670170`, `+6282294570374`, `+6281348822424`, `+62811508961`

**Root cause**: User lama ganti HP/MAC — tidak punya device `is_authorized=True` di DB.
**Perilaku**: User BISA login ke portal. Saat konek ke hotspot → device baru auto-register → binding fix otomatis.
**Tindakan admin**: Tidak perlu add MAC manual. Informasikan ke user untuk konek via hotspot dan login ulang.

### WA Debt Reminders
- Task `send_manual_debt_reminders_task` setiap 30 menit
- 3 tahap reminder: 3 hari, 1 hari, 3 jam sebelum `due_date`
- WA quota Fonnte: ~9472 remaining (19 Mar 2026)

### DHCP Self-Heal
- Pre-fix#39: 31–34/siklus → Post-fix#39: ~16/siklus → **Post-fix#2 (26 Mar): target ~0/siklus**
- Root cause kedua (last_seen=0 falsy guard) fixed → lease never-seen tidak lagi dihapus oleh cleanup
- Monitor setelah deploy: `dhcp_self_healed` harus ~0 dan `skipped_recent` harus naik ~33

### Redis Fragmentation
- `mem_fragmentation_ratio: 3.13` (20 Mar 2026) → **1.99** (26 Mar 2026) — turun 36%
- `--activedefrag yes` aktif sejak deploy Session 5
- Target < 1.5 — masih perlu monitor
- Monitor: `docker exec hotspot_prod_redis_cache redis-cli info memory | grep mem_fragmentation_ratio`

---

## GAP ANALYSIS — Masukan Penyempurnaan (27 Maret 2026)

Detail lengkap tersedia di [docs/GAP_ANALYSIS_2026_03_27.md](GAP_ANALYSIS_2026_03_27.md).

### ⏳ P1 — Automated E2E Test untuk Critical Path
**Status**: Infrastruktur siap (`docker-compose.e2e.yml` + `scripts/e2e/lib/`). Test script belum dibuat.
**Gap**: Semua validasi saat ini manual (lint + unit test + smoke). Tidak ada E2E test otomatis yang menguji flow captive → login → OTP → beli paket → aktivasi internet end-to-end.
**Risiko**: Regression pada integrasi antar-komponen yang lolos unit test tapi gagal di produksi.
**Saran**: Playwright/Cypress E2E minimal untuk: (1) login OTP sukses, (2) captive portal redirect, (3) admin CRUD user, (4) debt settle flow.

### ✅ P1 — Structured Error Response Consistency (27 Mar 2026, Session 7)
**Status**: SELESAI — normalizer `after_request` sudah aktif untuk semua API 4xx/5xx.
**Perubahan**:
- `after_request` hook di `__init__.py` otomatis menormalisasi semua JSON error response ke format standar:
  `{"success": false, "error": "...", "message": "...", "status_code": N, "code": "HTTP_N", "request_id": "..."}`
- Skip normalization jika response sudah canonical (punya `success` + `code`)
- Fallback khusus untuk 422 validation errors (`{"errors": [...]}`) → message "Validasi gagal."
- Extra keys dari payload asli (contoh: `errors`, `isValid`, `whatsapp_sent`) tetap dipertahankan

### ✅ P2 — Rate Limiting per Endpoint (27 Mar 2026, Session 7)
**Status**: SELESAI & DEPLOYED.
**Perubahan**: `Flask-Limiter` diterapkan pada endpoint admin sensitif:
- `POST /admin/users/{id}/reset-password` → `ADMIN_RESET_PASSWORD_RATE_LIMIT` (5/min; 20/hour)
- `POST /admin/users/{id}/reset-hotspot-password` → `ADMIN_RESET_PASSWORD_RATE_LIMIT`
- `POST /admin/users/{id}/reset-login` → `ADMIN_RESET_LOGIN_RATE_LIMIT` (5/min; 20/hour)
- `POST /admin/users/{id}/generate-admin-password` → `ADMIN_GENERATE_PASSWORD_RATE_LIMIT` (5/min; 20/hour)
- `POST /admin/users/{id}/debts/{id}/settle` → `ADMIN_DEBT_SETTLE_RATE_LIMIT` (10/min; 60/hour)
- `POST /admin/users/{id}/debts/settle-all` → `ADMIN_DEBT_SETTLE_RATE_LIMIT`
**Catatan**: `POST /auth/admin/login` sudah ada rate limit sebelumnya (`ADMIN_LOGIN_RATE_LIMIT`).

### ✅ P2 — Backup & Disaster Recovery Test (27 Mar 2026, Session 7)
**Status**: SELESAI — prosedur restore didokumentasikan.
**Perubahan**:
- Dokumentasi lengkap restore DB dari backup: `docs/workflows/disaster-recovery.md`
- Prosedur DR drill via E2E stack (restore ke environment lokal)
- Backup off-site (S3/R2) belum diimplementasi → tetap di PENDING sebagai enhancement

### ✅ P2 — Admin Audit Log Retention & Export (27 Mar 2026, Session 7)
**Status**: SELESAI & DEPLOYED.
**Perubahan**:
- Celery task `purge_old_admin_action_logs_task` — otomatis hapus log > 90 hari (configurable `ADMIN_ACTION_LOG_RETENTION_DAYS`)
- Endpoint DELETE `/api/admin/action-logs?before_date=YYYY-MM-DD` — purge log sebelum tanggal tertentu
- CSV/TXT export sudah ada sebelumnya (tidak berubah)

### ✅ P3 — WA Notification Delivery Tracking (27 Mar 2026, Session 7)
**Status**: SELESAI — tracking via AdminActionLog (bukan dashboard terpisah).
**Perubahan**:
- `AdminActionType.SEND_WHATSAPP_NOTIFICATION` ditambahkan
- Setiap pengiriman WA via `_send_whatsapp_notification()` otomatis tercatat di AdminActionLog
- Detail log: template, recipient, success/fail
- Frontend: chip WhatsApp hijau + format detail otomatis di halaman admin Log Aktivitas
- Admin bisa filter/search "SEND_WHATSAPP_NOTIFICATION" di halaman log

### ⏳ P3 — User Self-Service Password Reset (tanpa Admin)
**Status**: Reset password hanya via admin. **Tidak diubah (by design).**
**Gap**: User yang lupa password harus menghubungi admin secara manual.
**Saran**: Flow OTP-based self-service password reset untuk user reguler.

---

## ARSIP ITEM YANG SUDAH SELESAI

### ✅ Production Audit & 3 Fixes (26 Mar 2026 — Session 6)
- **Fix #1** (TINGGI): `expire_stale_transactions_task` schedule 60s → 300s (5 menit). Mengurangi ~80% DB query dan Celery task overhead. File: `backend/app/extensions.py`
- **Fix #2** (MEDIUM): DHCP self-heal loop 33 device — root cause: `if last_seen_seconds and ...` falsy ketika 0 (never-seen lease). Fix: `if last_seen_seconds == 0 or ...` — lease never-seen di-skip. File: `backend/app/tasks.py`
- **Fix #3** (MEDIUM): MikroTik `no such item (4)` TOCTOU race — `upsert_address_list_entry` fallback ke `add()` jika `set()` gagal karena entry expired antara `get()` dan `set()`. File: `backend/app/infrastructure/gateways/mikrotik_client.py`
- System status: 6/6 container healthy, 0 nginx error, DB 193 MB, Redis frag 1.99 (turun dari 3.13)

### ✅ Code Bugs Audit 20 Mar 2026 (Session 5)
- **Bug #1**: Hardcoded `lpsaring.babahdigital.net` di WA overdue block → `APP_PUBLIC_BASE_URL`
- **Bug #2**: `total_debt_mb // 1024 GB` → display MB/GB auto sesuai ukuran
- **Bug #3**: `socket.getaddrinfo()` tanpa timeout → `setdefaulttimeout(5)` + restore
- **Bug #4**: `finally: pass` di overdue block → proper exception + `db.session.remove()`
- **Bug #5**: Celery beat healthcheck `pgrep` → `/proc/1/cmdline` (pgrep tidak ada di image)
- **Bug #6**: Redis fragmentation ratio 3.13 → `--activedefrag yes`
- **Docs**: `DEVELOPMENT.md` 5.3.1 (docker down warning) + 5.3.2 (CI error resolved)

### ✅ WA Template + Block-Reasons Bugfix (19 Mar 2026 — Session 4)
- `user_debt_added` template: tambah `{package_name}`, `{price_rp_display}`, suffix ` GB`
- Template baru `user_debt_partial_payment_unblock` untuk notif unblock setelah bayar debt
- `block_reasons.py`: `is_debt_block_reason` tidak cover `tunggakan_overdue|` → diperbaiki
- Smoke test `test_smoke_session_2026_03_19_s4.py` — 13 tests, semua PASS

### ✅ Bug #28 — Nginx Resolver Race Condition (8.8.8.8)
- Fix: hapus `8.8.8.8` dari resolver, hanya `127.0.0.11 ipv6=off valid=2s`

### ✅ Bug #34 — MAC Randomization Cascade (Bug 2+3)
- Fix: `session_mac_token` dikirim ke `bind-current`, login_handlers.py session_mac_fallback

### ✅ Debt UX Major Overhaul
- `due_date` otomatis akhir bulan, kolom `price_rp` baru, dialog lengkap

### ✅ Frontend Display Improvements
- `formatDataSize()` → KB/MB/GB dengan presisi 2dp, locale id-ID

### ✅ Nginx Deploy Safety
- Guardrail: JANGAN `docker compose down` sebelum `--recreate`. Documented di `DEVELOPMENT.md`.

### ✅ WA Debt Payment Notification Fix (19 Mar 2026 — Session 2)
- `total_quota_until` → `quota_expiry_date`, tambah `debt_date` dan `paid_at`

### ✅ CI Lint Fix + price_rp Backfill Migration Deploy (19 Mar 2026 — Session 3)
- 7 ruff F401/F841 errors fixed; migration backfill applied; Docker images pushed ke Hub
