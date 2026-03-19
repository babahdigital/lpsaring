# PENDING DEVELOPMENT — LPSaring Hotspot Portal

Dokumen ini mencatat semua pengembangan yang sudah dianalisis, didesain, atau sebagian diimplementasi
tapi **belum selesai penuh** atau **perlu tindakan lanjutan**. Update setiap kali item selesai atau di-skip.

> **Update terakhir**: 2026-03-19 (Session 4 — WA Debt Template Fix + P1 Auto-Unblock + P2 Verify-Rules + block_reasons bugfix)

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

### ⚠️ Register Device untuk 5 User "no_authorized_device"
**Ditemukan**: Audit 19 Mar 2026 via policy_parity_guard_task
**Akibat**: 5 user unlimited/active TIDAK BISA akses internet meski status aktif
**Tindakan**: Admin login ke `/admin/users` → cari user berikut → tambah device MAC/IP

User yang terdampak (dari log parity guard):
- `+6285752083738` — status active, expected binding: bypassed, tidak punya device
- `+6285751420446` — status unlimited, expected binding: bypassed, tidak punya device
- `+6281528670170` — status unlimited, expected binding: bypassed, tidak punya device
- `+6282294570374` — status unlimited, expected binding: bypassed, tidak punya device
- `+6281348822424` — status unlimited, expected binding: bypassed, tidak punya device

**Catatan**: `auto_fixable: false` — tidak bisa di-fix otomatis oleh parity guard.

---

### ✅ `price_rp` — Otomatis dari Harga Paket (RESOLVED via Migration)
**Ditemukan**: Audit 19 Mar 2026 — `price_rp` semua NULL di record lama
**Root cause**: Column `price_rp` baru ditambahkan migration `20260319_add_price_rp_to_user_quota_debts`;
  record lama belum punya nilai. Record BARU sudah auto-filled dari `pkg.price` saat debt dibuat.
**Solusi**: Migration `20260319_d_backfill_price_rp_from_note` — backfill otomatis regex dari
  note field format `"Paket: ... (... , Rp 50.000)"` untuk semua record lama.
**Tindakan manual**: TIDAK DIPERLUKAN — seluruhnya otomatis via alembic upgrade.
**Catatan**: Record tanpa note yang cocok tetap NULL → frontend fallback ke `estimated_rp` (by design).

---

## P1 — PENTING (Fungsional Gap)

### ✅ 7.3 Akses-Banking Scheduler — `sync_access_banking_task`
**Status**: SELESAI diimplementasi, siap deploy (commit pending push)
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Populate `Bypass_Server` address-list MikroTik dengan banking domain IPs setiap hari jam 02:00
**Config settings DB yang perlu dibuat**:
- `AKSES_BANKING_ENABLED` — default `True`
- `AKSES_BANKING_DOMAINS` — default: `klikbca.com,bri.co.id,bankmandiri.co.id,bni.co.id,...`
- `AKSES_BANKING_LIST_NAME` — default `Bypass_Server`
- Cron: `AKSES_BANKING_CRON_HOUR=2`, `AKSES_BANKING_CRON_MINUTE=0`

**MASALAH YANG DI-SOLVE**: User expired/inactive tidak bisa akses banking untuk bayar tagihan.
**Workaround sementara** (sebelum deploy): Tambah banking IPs secara manual di MikroTik `Bypass_Server`.

---

### ✅ Auto-Block Overdue Debt — `enforce_overdue_debt_block_task`
**Status**: SELESAI diimplementasi, siap deploy (commit pending push)
**File**: `backend/app/tasks.py`, `backend/app/extensions.py`
**Fungsi**: Blokir user yang debt-nya melewati `due_date` (bukan hanya akhir bulan).
Berjalan harian jam 08:00 lokal. Kirim WA warning sebelum block.
**Config**:
- `ENABLE_OVERDUE_DEBT_BLOCK` — default `True`
- `OVERDUE_DEBT_BLOCK_CRON_HOUR=8`, `OVERDUE_DEBT_BLOCK_CRON_MINUTE=0`

**Gap yang di-solve**: Debt dari bulan lalu yang lewat jatuh tempo tidak di-enforce secara otomatis.

---

### ✅ Auto-Unblock Setelah Debt Lunas (19 Mar 2026 — Session 4)
**Status**: SELESAI diimplementasi
**File**: `backend/app/infrastructure/http/admin/user_management_routes.py`, `backend/app/utils/block_reasons.py`
**Fungsi**: `settle_single_manual_debt` sekarang auto-unblock user jika semua debt lunas dan block reason adalah debt (quota_debt_limit|, quota_manual_debt_end_of_month|, tunggakan_overdue|)
**Bonus Fix**: Bug kritis di `is_debt_block_reason` — prefix `tunggakan_overdue|` (dipakai `enforce_overdue_debt_block_task`) tidak di-cover → auto-unblock di `settle_all_debts` pun tidak pernah work untuk user diblokir task overdue. Fixed dengan tambah `OVERDUE_DEBT_PREFIX` + `is_overdue_debt_reason()`.
**WA**: Kirim `user_debt_partial_payment_unblock` (template baru) saat user di-unblock, atau `user_debt_partial_payment` jika partial payment saja.
**Catatan**: Response `settle_single_manual_debt` sekarang include field `unblocked: bool`.

---

### ✅ `price_rp` Auto-Fill dari Paket (RESOLVED — tindakan manual dihapus)
**Status**: SELESAI — tidak ada validasi manual yang diperlukan
**Analisis**: `price_rp` SELALU di-auto-fill oleh backend dari `pkg.price` saat debt dibuat
  via `debt_package_id`. Admin tidak pernah mengisi manual. Validator form tidak diperlukan.
**Record lama (NULL)**: Di-handle via migration backfill `20260319_d_backfill_price_rp_from_note`.
**Frontend**: Sudah handle fallback `price_rp ?? estimated_rp` dengan benar.

---

## P2 — NICE TO HAVE (Improvement)

### ✅ Naikkan Beat Interval sync_hotspot_usage ke 300s
**Status**: SELESAI — `extensions.py` diubah dari `min(sync_interval, 60)` ke `max(60, sync_interval)`
**Efek**: Beat tidak lagi membuang task setiap menit yang 80% langsung di-skip Redis lock

---

### ✅ Log Level "Skip sync address-list" dari INFO ke DEBUG
**Status**: SELESAI — `hotspot_sync_service.py` line ~1964 diubah dari `logger.info` ke `logger.debug`
**Efek**: Log tidak lagi dipenuhi 20+ baris identik per menit untuk user tanpa ip-binding compatible

---

### ✅ Fix Bug DHCP Loop: 28 Static Lease Dibuat Ulang Terus
**Status**: SELESAI — 2 file diubah
**Root Cause**: `_snapshot_dhcp_ips_by_mac` dan `_collect_dhcp_lease_snapshot` skip semua waiting lease.
Akibatnya self-heal menganggap device yang offline tidak punya static lease → rekrasi setiap sync.
**Fix**:
- `hotspot_sync_service.py::_snapshot_dhcp_ips_by_mac` — lpsaring-tagged waiting lease TIDAK di-skip
- `sync_unauthorized_hosts_command.py::_collect_dhcp_lease_snapshot` — lpsaring waiting MAC masuk ke `lpsaring_macs` untuk perlindungan dari `klient_unauthorized`

---

### ✅ Endpoint `/api/admin/mikrotik/verify-rules` (19 Mar 2026 — Session 4)
**Status**: SELESAI diimplementasi (backend route)
**File**: `backend/app/infrastructure/http/admin/user_management_routes.py`
**URL**: `GET /api/admin/mikrotik/verify-rules`
**Fungsi**: Verifikasi bahwa 4 firewall filter rule kritis ada dan urutannya benar
**Response**: `{status, all_found, order_ok, total_forward_rules, checks: [{rule, found, index}]}`
**Catatan**: Admin UI panel belum dibuat (backend only).

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
**Config**: Bisa tuning via `OTP_REQUEST_RATE_LIMIT` di env

---

## MONITORING ONGOING

### Circuit Breaker MikroTik
- Monitor via `dlq_health_monitor_task` (setiap 15 menit)
- Alert WA dikirim ke SUPER_ADMIN jika circuit breaker open
- Key Redis: `cb:open_alerts`

### Policy Parity Guard
- Berjalan setiap 10 menit, duration ~156s untuk 95 user
- 5 mismatch `no_authorized_device` perlu tindakan manual (lihat P0)
- Jika user bertambah → pertimbangkan optimalkan query

### WA Debt Reminders
- Task `send_manual_debt_reminders_task` setiap 30 menit
- 3 tahap: 3 hari, 1 hari, 3 jam sebelum due_date
- Dedup via Redis key per debt per stage
- WA quota Fonnte: ~9472 remaining (19 Mar 2026)

---

## ARSIP ITEM YANG SUDAH SELESAI

### ✅ WA Template + Block-Reasons Bugfix (19 Mar 2026 — Session 4)
- `user_debt_added` template diperbaiki: tambah `{package_name}`, `{price_rp_display}`, suffix ` GB` di semua nilai kuota
- Template baru `user_debt_partial_payment_unblock` untuk notif saat user di-unblock setelah bayar debt
- `user_profile.py` — 2 payload call diperbaiki (path debt_package_id dan path debt_add_mb)
- `block_reasons.py` — bug kritis: `is_debt_block_reason` tidak cover `tunggakan_overdue|` → diperbaiki
- Smoke test `test_smoke_session_2026_03_19_s4.py` — 13 tests, semua PASS

### ✅ Bug #28 — Nginx Resolver Race Condition (8.8.8.8)
- Fix: hapus `8.8.8.8` dari resolver, hanya `127.0.0.11 ipv6=off valid=2s`
- Incident doc: `docs/incidents/2026-03-19-nginx-resolver-race-condition-8.8.8.8.md`

### ✅ Bug #34 — MAC Randomization Cascade (Bug 2+3)
- Fix: `session_mac_token` dikirim ke `bind-current`
- Files: `auth.ts`, `hotspot-required.vue`, `profile_routes.py`, `login_handlers.py`

### ✅ Debt UX Major Overhaul
- `due_date` otomatis akhir bulan, `price_rp` column baru, dialog lengkap
- Migration: `20260319_add_price_rp_to_user_quota_debts` + `20260319_c_populate_null_due_dates`

### ✅ Frontend Display Improvements
- `formatDataSize()` → KB/MB/GB dengan presisi 2dp
- `UserDebtLedgerDialog` dan `riwayat/index` redesign

### ✅ Nginx Deploy Safety
- `PERINGATAN: JANGAN docker compose down sebelum --recreate`
- Post-deploy: `--recreate` saja sudah cukup

### ✅ WA Debt Payment Notification Fix (19 Mar 2026 — Session 2)
- **Bug**: `total_quota_until` (attr tidak ada) → `quota_expiry_date` di `user_management_routes.py`
- **Tambah**: `debt_date` (tunggakan mana yang dilunasi) + `paid_at` (waktu WITA pelunasan)
- **Template**: `user_debt_partial_payment` di `app/notifications/templates.json` diperbarui
- **Files**: `user_management_routes.py`, `templates.json`

### ✅ Pylance Errors Fixed — tasks.py (19 Mar 2026 — Session 2)
- Line ~2978: `str(addr_info[4][0])` — IP cast to str untuk type safety
- Lines ~3199-3202: `send_whatsapp_message(recipient_number=..., message_body=...)` — kwarg fix

### ✅ Smoke Test Suite — Session 2026-03-19 (19 Mar 2026 — Session 2)
- File: `backend/tests/test_smoke_session_2026_03_19.py` (13 tests)
- Coverage: DHCP loop fix, banking task, overdue block task, WA template, route source checks
- Semua 13 tests PASS, full suite tidak regresi

### ✅ CI Lint Fix + price_rp Backfill Migration Deploy (19 Mar 2026 — Session 3)
- **CI**: 7 ruff F401/F841 errors fixed — unused imports di smoke test, unused `app_tz` di `tasks.py`, unused `sqlalchemy` import di migration baru
- **Migration**: `20260319_d_backfill_price_rp_from_note` — SQL regex backfill `price_rp` dari note field `"Rp 200,000"` untuk semua record lama (NULL)
- **Produksi**: Migration applied via `deploy_pi.sh --recreate` → `total_unpaid=11, with_price_rp=11, still_null=0`
- **Docker**: Multi-arch images pushed ke Docker Hub (`babahdigital/sobigidul_backend`, `babahdigital/sobigidul_frontend`)
- **CI runs**: `23287511682` (ci=success), `23287299801` (docker-publish=success)
- **Post-deploy**: Semua 6 container healthy, no errors in production logs
