# Devlog — Audit Total Holistik & Penyempurnaan — 2026-03-19 (Session 2)

Sesi ini adalah **audit total production** lpsaring hotspot portal setelah deploy `c36e9310`.
Mencakup analisis docker logs semua container, nginx logs, git history, kodebase lengkap,
dan DB state. Ditemukan 6 anomali + gap fitur, semua berbasis data riil dari server production.

---

## 1. Fix Bug: DHCP Static Lease Self-Heal Loop (28 lease konstan)

**Files**: `backend/app/services/hotspot_sync_service.py`, `backend/app/commands/sync_unauthorized_hosts_command.py`

**Anomali dari log**:
```
"dhcp_self_healed": 28    # Konstan setiap siklus sync
"lease_removed": 28       # Konstan setiap siklus cleanup (5 menit)
```

**Root Cause**: `_snapshot_dhcp_ips_by_mac` (hotspot_sync_service) dan `_collect_dhcp_lease_snapshot`
(sync_unauthorized_hosts_command) keduanya skip semua DHCP lease berstatus `waiting`.
MikroTik memberi status `waiting` pada static lease ketika device **offline** (bukan error).
Akibatnya self-heal tidak tahu lease already exists → rekrasi setiap siklus.
Cleanup lalu menghapus lease yang berstatus waiting → loop tanpa henti.

**Fix (hotspot_sync_service.py)**:
```python
# Sebelum:
if status == "waiting":
    continue

# Sesudah — lpsaring-tagged waiting lease tetap masuk snapshot:
if status == "waiting":
    comment = str(row.get("comment") or "").lower()
    if "lpsaring|static-dhcp" not in comment:
        continue
    # Fall-through: include lpsaring waiting lease dalam by_mac
```

**Fix (sync_unauthorized_hosts_command.py)**:
```python
# Sebelum:
if status == "waiting":
    continue

# Sesudah — MAC tetap dilindungi dari klient_unauthorized:
if status == "waiting":
    if mac and "lpsaring|static-dhcp" in comment:
        lpsaring_macs.add(mac)
    continue
```

**Efek**: Loop berhenti. `dhcp_self_healed` seharusnya turun ke ~0.
Incident doc: `docs/incidents/2026-03-19-dhcp-loop-self-heal.md`

---

## 2. Fix: Log Level "Skip sync address-list" INFO → DEBUG

**File**: `backend/app/services/hotspot_sync_service.py`

Log `"Skip sync address-list by username tanpa ip-binding policy-compatible"` muncul
untuk ~20 user yang sama setiap siklus (INFO level) → ratusan baris identik per jam.

**Fix**: `logger.info(` → `logger.debug(` di baris yang relevan.
Log tetap tersedia di DEBUG mode untuk diagnosis, tapi tidak mencemari production INFO log.

---

## 3. Fix: Beat Interval sync_hotspot_usage 60s → 300s

**File**: `backend/app/extensions.py`

**Sebelum**: `schedule_seconds = min(sync_interval, 60)` → beat kirim task setiap 60s
**Akibat**: 80% task langsung discarded oleh Redis lock (`last_run_ts` check: skip jika < 300s)
**Sesudah**: `schedule_seconds = max(60, sync_interval)` → beat kirim task setiap 300s

Efek: Celery tidak lagi membuang 4 dari 5 task. Log lebih bersih. Worker lebih efisien.

---

## 4. Fitur Baru: `sync_access_banking_task` (7.3 Akses-Banking Scheduler)

**Files**: `backend/app/tasks.py`, `backend/app/extensions.py`

**Masalah yang diselesaikan**: User `klient_inactive` (expired/habis) tidak bisa akses
mobile banking untuk bayar tagihan → deadlock "tidak bisa bayar karena tidak bisa akses internet".

**Implementasi**:
- Task Celery `sync_access_banking_task` — harian jam 02:00 lokal
- Resolve IP dari banking domain list via DNS (`socket.getaddrinfo`)
- Upsert ke `Bypass_Server` address-list MikroTik (comment `source=banking-sync`)
- Hapus stale entry (hanya yang ber-comment `source=banking-sync` — entri manual aman)
- Import `get_firewall_address_list_entries` ditambah ke import block tasks.py

**Config settings DB** yang perlu dibuat post-deploy:
- `AKSES_BANKING_ENABLED` (default `True`)
- `AKSES_BANKING_DOMAINS` (default: klikbca.com, bri.co.id, bankmandiri.co.id, dll)
- `AKSES_BANKING_LIST_NAME` (default: `Bypass_Server`)

**Beat schedule** di extensions.py: `sync-access-banking`, jam 02:00 (configurable via
`AKSES_BANKING_CRON_HOUR`, `AKSES_BANKING_CRON_MINUTE`)

Incident doc: `docs/incidents/2026-03-19-banking-deadlock-inactive-users.md`

---

## 5. Fitur Baru: `enforce_overdue_debt_block_task` (P1 Auto-block post-due-date)

**Files**: `backend/app/tasks.py`, `backend/app/extensions.py`

**Gap yang diselesaikan**: `enforce_end_of_month_debt_block_task` hanya berjalan di hari terakhir
bulan, jam 23:00. Debt dari bulan-bulan **sebelumnya** yang masih belum lunas tidak di-enforce
secara otomatis setelah akhir bulan.

**Implementasi**:
- Task Celery `enforce_overdue_debt_block_task` — harian jam 08:00 lokal
- Query: `UserQuotaDebt.paid_at IS NULL AND due_date < today`
- Guard: skip user yang sudah diblokir, unlimited, non-active, non-USER role
- Flow:
  1. Kirim WA warning ke user (⚠️ TAGIHAN JATUH TEMPO - AKSES AKAN DIBLOKIR)
  2. Block via hotspot profile `blocked`, limit_bytes=1, timeout=1s
  3. Set `user.is_blocked = True`, `blocked_reason = "tunggakan_overdue|..."`
  4. Upsert ip-binding `blocked` untuk semua device MAC
  5. Pindah IP ke `klient_blocked`, hapus dari address list lain
  6. Append ke quota_mutation_ledger
  7. Commit per-user (rollback per-user jika gagal)

**Beat schedule**: `enforce-overdue-debt-block`, crontab jam 08:00 (configurable via
`OVERDUE_DEBT_BLOCK_CRON_HOUR`, `OVERDUE_DEBT_BLOCK_CRON_MINUTE`)

**Config**: `ENABLE_OVERDUE_DEBT_BLOCK=True` (default)

---

## Audit Finding Summary (Tidak Diimplementasi Sesi Ini)

### ⚠️ [Manual] 5 User Tanpa Authorized Device
- `policy_parity_guard` menemukan 5 user unlimited/active tanpa device terdaftar
- `auto_fixable: false` → admin harus register device manual
- Detail: `docs/PENDING_DEVELOPMENT.md` section P0

### ⚠️ [Manual] 11 Debt Aktif dengan `price_rp=NULL`
- Semua 11 debt aktif belum diisi harga pasti
- Frontend fallback ke `estimated_rp` (dari cheapest package)
- Admin harus isi sebelum 31 Maret 2026

### ✅ [Sudah Ada] OTP Rate Limiting
- Sudah ada: `"5 per minute;20 per hour"` per phone number
- Config: `OTP_REQUEST_RATE_LIMIT` env var
- Tidak perlu perubahan

### ℹ️ [Context] Nginx Resolver Fix Terverifikasi
- `resolver 127.0.0.11 ipv6=off valid=2s` sudah benar
- Tidak ada 8.8.8.8 — fix dari Mar 18 masih valid

### ℹ️ [Context] Policy Parity Task Duration 156s
- Untuk 95 user normal — tidak ada perubahan diperlukan
- Jika user bertambah 200+, pertimbangkan optimasi query MikroTik

---

## Files Changed

| File | Perubahan |
|------|-----------|
| `backend/app/services/hotspot_sync_service.py` | Fix DHCP loop + log level |
| `backend/app/commands/sync_unauthorized_hosts_command.py` | Fix DHCP loop (lpsaring_macs protection) |
| `backend/app/tasks.py` | Import baru + 2 task baru (banking + overdue block) |
| `backend/app/extensions.py` | Beat schedule: interval fix + 2 schedule baru |
| `docs/PENDING_DEVELOPMENT.md` | Dokumen baru — semua pending items |
| `docs/incidents/2026-03-19-dhcp-loop-self-heal.md` | Incident baru |
| `docs/incidents/2026-03-19-banking-deadlock-inactive-users.md` | Incident baru |

---

## Deploy Instructions

```bash
# 1. Push ke origin
git add -A
git commit -m "fix: DHCP loop + banking scheduler + overdue debt block + beat interval"
git push origin main

# 2. Build + deploy
cd lpsaring && bash deploy_pi.sh --trigger-build

# 3. Verifikasi post-deploy
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31
docker logs hotspot_prod_celery_worker --tail=50 | grep "dhcp_self_healed"
# Expected: "dhcp_self_healed": 0

docker logs hotspot_prod_celery_beat --tail=20 | grep "sync-access-banking\|enforce-overdue"
# Expected: Banking sync di jam 02:00, Overdue block di jam 08:00

# 4. Tambah settings di admin panel setelah deploy
# AKSES_BANKING_ENABLED=True
# AKSES_BANKING_DOMAINS=klikbca.com,bri.co.id,bankmandiri.co.id,bni.co.id,...
# ENABLE_OVERDUE_DEBT_BLOCK=True
```

---

## Post-Deploy Checklist

- [ ] `dhcp_self_healed` di log turun ke ~0 (was: 28 constant)
- [ ] `sync-access-banking` muncul di celery beat schedule
- [ ] `enforce-overdue-debt-block` muncul di celery beat schedule
- [ ] Trigger manual `sync_access_banking_task` → cek `Bypass_Server` MikroTik populated
- [ ] Register device untuk 5 user `no_authorized_device` (admin action)
- [ ] Isi `price_rp` untuk 11 debt aktif sebelum 31 Mar 2026 (admin action)
- [ ] `sync-hotspot-usage` beat interval berubah dari 60s ke 300s di log beat
