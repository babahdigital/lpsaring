# PENDING DEVELOPMENT — LPSaring Hotspot Portal

Dokumen ini mencatat semua pengembangan yang sudah dianalisis, didesain, atau sebagian diimplementasi
tapi **belum selesai penuh** atau **perlu tindakan lanjutan**. Update setiap kali item selesai atau di-skip.

> **Update terakhir**: 2026-03-20 (Session 5 — Final cleanup: hapus miskonsepsi config DB, pindah 5-user ke monitoring, fix DHCP status)

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

### 🔍 Fix Bug DHCP Loop: Static Lease Dibuat Ulang Terus
**Status**: Deployed (Session 5), **dalam pemantauan** — belum confirmed selesai.
**Root Cause**: `_snapshot_dhcp_ips_by_mac` dan `_collect_dhcp_lease_snapshot` skip semua waiting lease.
**Fix yang diterapkan**: Include lpsaring-tagged waiting lease → tidak di-recreate terus.
**Progress**: `dhcp_self_healed` 31–34 (pre-deploy) → 26 → 16 (post-deploy, 53% turun).
**Tindakan selanjutnya**: Monitor 1–2 siklus. Jika tidak turun ke ~0 → investigasi root cause kedua.

---

### ✅ Endpoint `/api/admin/mikrotik/verify-rules` (19 Mar 2026 — Session 4)
**Status**: SELESAI (backend route). Admin UI panel belum dibuat.

---

### ⏳ Downgrade `no_authorized_device` Priority di Parity Guard
**Status**: Belum diimplementasi.
**Background**: Parity guard mark `no_authorized_device` sebagai `priority: "high"` / action `authorize_device_from_admin`.
Ini misleading — sistem self-heals saat user konek ulang ke hotspot; admin tidak tahu MAC user sekarang.
**Tindakan**: `access_parity_service.py` `_build_action_plan()` → ubah priority ke `low`, action ke `wait_for_user_reconnect`.
**Impact**: Log parity guard lebih bersih; tidak ada false alarm "high priority" setiap 10 menit.

---

### ⏳ Admin UI Panel untuk `/api/admin/mikrotik/verify-rules`
**Status**: Belum diimplementasi — endpoint backend sudah ada.
**Tindakan**: Buat halaman/card di admin dashboard untuk menampilkan hasil verify-rules.

---

### ⏳ Investigasi `skipped_not_allowed: 27-31`
**Status**: Belum diinvestigasi.
**Ditemukan**: Audit log dari `sync_unauthorized_hosts_task`.
**Pertanyaan**: Apakah ada subnet host yang seharusnya masuk `MIKROTIK_UNAUTHORIZED_CIDRS` tapi tidak?
**Tindakan**: Cek `/ip/hotspot/activity print` di MikroTik → lihat IP yang masuk `skipped_not_allowed`.

---

### ⏳ Rate Limiting OTP
**Status**: Sudah ada (`5/menit; 20/jam` per phone). Tidak perlu perubahan kecuali ada insiden brute force.

---

### ⏳ MAC Randomization: Session-Storage Fallback Binding
**Status**: Belum diimplementasi.
**Background**: Insiden `2026-03-07-mac-randomization-analisa-6282213631573.md`.
**Yang sudah ada**: Deteksi LAA bit + warning dialog di `hotspot-required.vue`.
**Yang belum**: Auto-binding via `session_mac_token` untuk device MAC randomization first-time.
**Dampak aktual**: User `+6281255962309` (MAC `16:5B:A4:E2:9C:1F` = LAA) → `dhcp_lease_missing` loop aktif.

---

## MONITORING ONGOING

### Circuit Breaker MikroTik
- Monitor via `dlq_health_monitor_task` (setiap 15 menit)
- Alert WA dikirim ke SUPER_ADMIN jika circuit breaker open

### Policy Parity Guard
- Berjalan setiap 10 menit, durasi ~156–174s untuk 89 user
- **5 user `no_authorized_device`**: self-resolve — sistem fix otomatis saat user konek ulang ke hotspot. Tidak butuh admin action. (lihat ℹ️ bawah)
- `+6281255962309` (MAC randomization LAA) → `dhcp_lease_missing` loop — belum selesai, pending MAC randomization fallback fix

### ℹ️ 5 User Tanpa Device Terdaftar
User berikut muncul di log parity guard tiap 10 menit sebagai `no_authorized_device`:
`+6285752083738`, `+6285751420446`, `+6281528670170`, `+6282294570374`, `+6281348822424`

**Root cause**: User lama ganti HP/MAC — tidak punya device `is_authorized=True` di DB.
**Perilaku**: User BISA login ke portal. Saat konek ke hotspot → device baru auto-register → binding fix otomatis.
**Tindakan admin**: Tidak perlu add MAC manual. Informasikan ke user untuk konek via hotspot dan login ulang.

### WA Debt Reminders
- Task `send_manual_debt_reminders_task` setiap 30 menit
- 3 tahap reminder: 3 hari, 1 hari, 3 jam sebelum `due_date`
- WA quota Fonnte: ~9472 remaining (19 Mar 2026)

### DHCP Self-Heal
- Pre-deploy: 31–34/siklus → Post-deploy: ~16/siklus (sedang turun)
- Jika tidak mencapai ~0 dalam beberapa siklus → investigasi root cause kedua (diluar waiting lease fix)

### Redis Fragmentation
- `mem_fragmentation_ratio: 3.13` (20 Mar 2026) — tinggi, target < 1.5
- `--activedefrag yes` aktif sejak deploy Session 5
- Monitor: `docker exec hotspot_prod_redis_cache redis-cli info memory | grep mem_fragmentation_ratio`

---

## ARSIP ITEM YANG SUDAH SELESAI

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
