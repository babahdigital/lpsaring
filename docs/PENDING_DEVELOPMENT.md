# PENDING DEVELOPMENT — LPSaring Hotspot Portal

Dokumen ini mencatat semua pengembangan yang sudah dianalisis, didesain, atau sebagian diimplementasi
tapi **belum selesai penuh** atau **perlu tindakan lanjutan**. Update setiap kali item selesai atau di-skip.

> **Update terakhir**: 2026-03-20 (Session 5 — Post-Deploy: celery healthcheck fix, settings env.prod, analisa no_authorized_device)

---

## STATUS LEGENDA

| Simbol | Arti |
|--------|------|
| ✅ | Selesai & di-deploy |
| ⚙️ | Sudah diimplementasi, perlu deploy |
| ⏳ | Dianalisis, belum diimplementasi |
| ❌ | Dibatalkan / tidak relevan |
| ⚠️ | Butuh tindakan manual admin |

---

## P0 — SEGERA (Ops Blocker)

### ✅ Setup Settings Untuk Task Baru
**Status**: SELESAI — ditambahkan ke `.env.prod` (20 Mar 2026, Session 5)
- `AKSES_BANKING_ENABLED=True` → di `.env.prod` server
- `ENABLE_OVERDUE_DEBT_BLOCK=True` → di `.env.prod` server
- `AKSES_BANKING_DOMAINS` dikomen (tersedia, default 10 bank umum sudah cukup)
- Trigger manual `sync_access_banking_task` akan berjalan besok jam 02:00 otomatis
- **Tidak perlu settings DB** — `settings_service.get_setting(key, default)` fallback ke `os.environ` jika tidak ada di DB

---

### ℹ️ 5 User Tanpa Device Terdaftar — SELF-RESOLVE, Bukan Urgent
**Ditemukan**: Audit 19 Mar 2026 via policy_parity_guard_task
**Dikonfirmasi**: Live log 20 Mar 2026 — muncul setiap 10 menit di parity guard log

**Analisa root cause** (20 Mar 2026):
- Parity guard flag `no_authorized_device` = user tidak punya device dengan `is_authorized=True` di DB
- Ini kemungkinan besar user lama yang ganti HP/MAC (device lama tidak ter-authorized atau sudah dihapus)
- `auto_fixable: false` — admin tidak bisa add device karena MAC baru tidak diketahui
- **Tindakan admin "tambah MAC manual" TIDAK TEPAT** — admin tidak tahu MAC HP user saat ini

**Perilaku sistem yang benar**:
- User TETAP BISA login ke portal (`/login`) — tidak ada block di autentikasi
- Saat user konek ke hotspot dengan HP barunya → MikroTik redirect → user login → device baru auto-register → parity guard otomatis fix binding di siklus berikutnya
- **Sistem self-heal tanpa intervensi admin**

User yang terdampak (hanya informatif):
- `+6285752083738`, `+6285751420446`, `+6281528670170`, `+6282294570374`, `+6281348822424`

**Tindakan yang perlu**: Informasikan ke user untuk konek via hotspot dan login ulang.

**Future improvement**: Downgrade `no_authorized_device` priority dari `high` ke `low` di
`access_parity_service.py` `_build_action_plan()` — agar tidak muncul sebagai alert prioritas tinggi.

---

### ✅ `price_rp` — Otomatis dari Harga Paket (RESOLVED via Migration)
**Ditemukan**: Audit 19 Mar 2026 — `price_rp` semua NULL di record lama
**Solusi**: Migration `20260319_d_backfill_price_rp_from_note` — backfill otomatis via SQL regex.
**Tindakan manual**: TIDAK DIPERLUKAN — seluruhnya otomatis via alembic upgrade.
**Catatan**: Record tanpa note yang cocok tetap NULL → frontend fallback ke `estimated_rp` (by design).

---

## P1 — PENTING (Fungsional Gap)

### ✅ 7.3 Akses-Banking Scheduler — `sync_access_banking_task`
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5). `AKSES_BANKING_ENABLED=True` di `.env.prod`.
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Populate `Bypass_Server` address-list MikroTik dengan banking domain IPs setiap hari jam 02:00
**Code fixes (20 Mar 2026)**:
- `socket.getaddrinfo()` sekarang dibatasi `setdefaulttimeout(5)` selama DNS resolution loop
- Restore ke `None` setelah loop agar tidak pengaruhi socket op lain

**Config settings DB yang perlu dibuat post-deploy**:
- `AKSES_BANKING_ENABLED` — default `True`
- `AKSES_BANKING_DOMAINS` — default: `klikbca.com,bri.co.id,bankmandiri.co.id,bni.co.id,...`
- `AKSES_BANKING_LIST_NAME` — default `Bypass_Server`
- Cron env: `AKSES_BANKING_CRON_HOUR=2`, `AKSES_BANKING_CRON_MINUTE=0`

**MASALAH YANG DI-SOLVE**: User expired/inactive tidak bisa akses banking untuk bayar tagihan.

---

### ✅ Auto-Block Overdue Debt — `enforce_overdue_debt_block_task`
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5). `ENABLE_OVERDUE_DEBT_BLOCK=True` di `.env.prod`.
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Blokir user yang debt-nya melewati `due_date`. Berjalan harian jam 08:00 lokal.
**Code fixes (20 Mar 2026)**:
- Hardcoded `lpsaring.babahdigital.net` → `app.config.get("APP_PUBLIC_BASE_URL")`
- `total_debt_mb // 1024 GB` display → MB/GB otomatis sesuai ukuran (< 1 GB tampil MB)
- `finally: pass` → proper exception handling + `db.session.remove()` cleanup

**Config**:
- `ENABLE_OVERDUE_DEBT_BLOCK` — default `True` (DB setting)
- `OVERDUE_DEBT_BLOCK_CRON_HOUR=8`, `OVERDUE_DEBT_BLOCK_CRON_MINUTE=0`

---

### ✅ Auto-Unblock Setelah Debt Lunas (19 Mar 2026 — Session 4)
**Status**: SELESAI diimplementasi
**File**: `backend/app/infrastructure/http/admin/user_management_routes.py`, `backend/app/utils/block_reasons.py`
**Fungsi**: `settle_single_manual_debt` auto-unblock user jika semua debt lunas
**Fix**: `is_debt_block_reason` sekarang cover `tunggakan_overdue|` prefix dari overdue block task

---

### ✅ `price_rp` Auto-Fill dari Paket (RESOLVED — tindakan manual dihapus)
**Status**: SELESAI — tidak ada validasi manual yang diperlukan

---

## P2 — NICE TO HAVE (Improvement)

### ✅ Docker Compose Celery Healthcheck + Redis activedefrag
**Status**: SELESAI & DEPLOYED (20 Mar 2026, Session 5)
**File**: `docker-compose.prod.yml`
**Perubahan**:
- `celery_worker`: healthcheck via `celery inspect ping` setiap 60s — ✅ healthy
- `celery_beat`: healthcheck via `/proc/1/cmdline` (pgrep tidak tersedia di image) — ✅ healthy setelah fix
- `redis`: tambah `--activedefrag yes` (measured 3.13, defrag aktif sejak deploy)

---

### ✅ Naikkan Beat Interval sync_hotspot_usage ke 300s
**Status**: SELESAI — `extensions.py` diubah dari `min(sync_interval, 60)` ke `max(60, sync_interval)`

---

### ✅ Log Level "Skip sync address-list" dari INFO ke DEBUG
**Status**: SELESAI — `hotspot_sync_service.py` diubah dari `logger.info` ke `logger.debug`

---

### ⚙️ Fix Bug DHCP Loop: 28 Static Lease Dibuat Ulang Terus
**Status**: Diimplementasi & deployed (Session 5). PARTIALLY FIXED — sedang settle.
**Root Cause**: `_snapshot_dhcp_ips_by_mac` dan `_collect_dhcp_lease_snapshot` skip semua waiting lease.
**Dikonfirmasi dari live log 20 Mar**: dhcp_self_healed: 31-34 sebelum deploy → 26 → 16 post-deploy (53% turun).
**Investigasi lanjutan perlu** jika tidak turun ke ~0 dalam beberapa siklus.

---

### ✅ Endpoint `/api/admin/mikrotik/verify-rules` (19 Mar 2026 — Session 4)
**Status**: SELESAI diimplementasi (backend route)
**Catatan**: Admin UI panel belum dibuat (backend only).

---

### ⏳ Downgrade `no_authorized_device` Priority di Parity Guard
**Status**: Belum diimplementasi
**Background**: Parity guard saat ini mark `no_authorized_device` sebagai `priority: "high"` dengan
action `authorize_device_from_admin`. Ini misleading — admin tidak tahu MAC user, dan sistem self-heals saat user konek ulang.
**Tindakan**: Di `access_parity_service.py` `_build_action_plan()`, ubah priority ke `low` dan action ke
`wait_for_user_reconnect` untuk kasus `no_authorized_device`.
**Impact**: Parity guard log jadi lebih bersih; tidak ada false alarm "high priority" setiap 10 menit.

---

### ⏳ Admin UI Panel untuk `/api/admin/mikrotik/verify-rules`
**Status**: Belum diimplementasi — endpoint backend sudah ada
**Tindakan**: Buat halaman/card di admin dashboard untuk menampilkan hasil verify-rules

---

### ⏳ Investigasi `skipped_not_allowed: 27-31`
**Status**: Belum diinvestigasi
**Ditemukan**: Audit log dari `sync_unauthorized_hosts_task`
**Pertanyaan**: Apakah ada subnet host yang seharusnya masuk `MIKROTIK_UNAUTHORIZED_CIDRS` tapi tidak?
**Tindakan**: Cek `/ip/hotspot/activity print` di MikroTik → lihat IP yang masuk skipped_not_allowed

---

### ⏳ Rate Limiting OTP yang Lebih Agresif
**Status**: Rate limiting OTP sudah ada — `5 per minute; 20 per hour` per phone
**Catatan**: Sudah adequate. Tidak perlu perubahan kecuali ada insiden brute force aktual.

---

### ⏳ MAC Randomization: Session-Storage Fallback Binding (P1 dari insiden Mar 07)
**Status**: Belum diimplementasi
**Background**: Insiden `2026-03-07-mac-randomization-analisa-6282213631573.md`
**Yang sudah ada**: Deteksi LAA bit + warning dialog di `hotspot-required.vue`
**Yang belum**: Auto-binding menggunakan `session_mac_token` untuk MAC randomization first-time device
**Dampak aktual**: User `+6281255962309` (MAC `16:5B:A4:E2:9C:1F` = LAA) → `dhcp_lease_missing` loop

---

## MONITORING ONGOING

### Circuit Breaker MikroTik
- Monitor via `dlq_health_monitor_task` (setiap 15 menit)
- Alert WA dikirim ke SUPER_ADMIN jika circuit breaker open

### Policy Parity Guard
- Berjalan setiap 10 menit, duration ~156-174s untuk 89 user
- 5 user `no_authorized_device`: **self-resolve** — tidak butuh admin action, akan fix sendiri saat user konek ulang ke hotspot
- `+6281255962309` (MAC randomization) → `dhcp_lease_missing` auto-fixable, akan normal setelah DHCP fix #39 deploy

### WA Debt Reminders
- Task `send_manual_debt_reminders_task` setiap 30 menit
- 3 tahap: 3 hari, 1 hari, 3 jam sebelum due_date
- WA quota Fonnte: ~9472 remaining (19 Mar 2026)

### Redis Fragmentation
- `mem_fragmentation_ratio: 3.13` (20 Mar 2026) — tinggi, target < 1.5
- Fix: `--activedefrag yes` deployed (20 Mar 2026 Session 5), defrag berjalan di background
- Monitor: cek `redis-cli info memory | grep mem_fragmentation_ratio` dalam 1-2 hari

---

## ARSIP ITEM YANG SUDAH SELESAI

### ✅ Code Bugs Audit 20 Mar 2026 (Session 5)
- **Bug #1**: Hardcoded `lpsaring.babahdigital.net` di WA overdue block → `APP_PUBLIC_BASE_URL`
- **Bug #2**: `total_debt_mb // 1024 GB` → display MB/GB auto sesuai ukuran
- **Bug #3**: `socket.getaddrinfo()` tanpa timeout → `setdefaulttimeout(5)` + restore
- **Bug #4**: `finally: pass` di overdue block → proper exception + `db.session.remove()`
- **Bug #5**: No Celery healthcheck → healthcheck worker + beat ditambahkan
- **Bug #6**: Redis fragmentation ratio 3.13 → `--activedefrag yes`
- **Docs**: `DEVELOPMENT.md` 5.3.1 (docker down warning) + 5.3.2 (CI error resolved)

### ✅ WA Template + Block-Reasons Bugfix (19 Mar 2026 — Session 4)
- `user_debt_added` template diperbaiki: tambah `{package_name}`, `{price_rp_display}`, suffix ` GB`
- Template baru `user_debt_partial_payment_unblock` untuk notif saat user di-unblock setelah bayar debt
- `block_reasons.py` bug kritis: `is_debt_block_reason` tidak cover `tunggakan_overdue|` → diperbaiki
- Smoke test `test_smoke_session_2026_03_19_s4.py` — 13 tests, semua PASS

### ✅ Bug #28 — Nginx Resolver Race Condition (8.8.8.8)
- Fix: hapus `8.8.8.8` dari resolver, hanya `127.0.0.11 ipv6=off valid=2s`

### ✅ Bug #34 — MAC Randomization Cascade (Bug 2+3)
- Fix: `session_mac_token` dikirim ke `bind-current`, login_handlers.py session_mac_fallback

### ✅ Debt UX Major Overhaul
- `due_date` otomatis akhir bulan, `price_rp` column baru, dialog lengkap

### ✅ Frontend Display Improvements
- `formatDataSize()` → KB/MB/GB dengan presisi 2dp, locale id-ID

### ✅ Nginx Deploy Safety
- `PERINGATAN: JANGAN docker compose down sebelum --recreate`

### ✅ WA Debt Payment Notification Fix (19 Mar 2026 — Session 2)
- `total_quota_until` → `quota_expiry_date`, tambah `debt_date` dan `paid_at`

### ✅ CI Lint Fix + price_rp Backfill Migration Deploy (19 Mar 2026 — Session 3)
- 7 ruff F401/F841 errors fixed; migration backfill applied; Docker images pushed ke Hub
