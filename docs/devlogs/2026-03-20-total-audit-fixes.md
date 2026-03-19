# Devlog: 2026-03-20 — Session 5: Total Audit Fixes & Production Deploy

**Tanggal**: 20 Maret 2026
**Sesi**: 5 (lanjutan dari Session 4, 19 Mar 2026)
**Author**: Abdullah (via Claude Code)
**Commit-scope**: Code fixes + Docker config + documentasi + deploy

---

## Konteks

Setelah analisis komprehensif project (baca semua docs + live SSH log produksi),
ditemukan beberapa bug code aktif yang belum diperbaiki meski task sudah diimplementasi,
serta gap konfigurasi infrastruktur dan dokumentasi yang perlu diselesaikan sebelum deploy.

Sesi ini menyelesaikan semua temuan tersebut dan melakukan deploy penuh.

---

## 1. Temuan Live Log Produksi (Pre-Fix)

### DHCP Self-Heal Loop Masih Aktif
Dari log Celery worker (03:23-03:36 WITA):
```json
{"dhcp_self_healed": 31}  // 03:23
{"dhcp_self_healed": 34}  // 03:27
{"dhcp_self_healed": 0}   // 03:31 -- setelah cleanup_waiting_dhcp_arp
{"dhcp_self_healed": 26}  // 03:35
```
```json
{"lease_removed": 34}  // cleanup_waiting_dhcp_arp setiap 5 menit
```
Konfirmasi bahwa fix #39 (DHCP loop) **belum di-deploy** dan loop masih berjalan.
34 write request tidak perlu ke MikroTik setiap 10 menit.

### Policy Parity Guard — 5 User No Device
WARNING muncul setiap 10 menit, 5 user `no_authorized_device` dikonfirmasi dari live log.
Termasuk user `+6281255962309` dengan MAC `16:5B:A4:E2:9C:1F` (LAA = MAC randomization).

### Redis Fragmentation Ratio Tinggi
`mem_fragmentation_ratio: 3.13` — redis mengalokasikan ~3x dari data actual.
Normal threshold < 1.5. Penyebab: banyak key creation/deletion dari Redis lock task Celery.

### Nginx Access Log Noise
Ratusan `405 Method Not Allowed` dari `10.19.83.2` (MikroTik) dengan path `/client/upload/reportSingleDelay`.
Ini Android SDK telemetry yang di-intercept karena `Bypass_Server` belum berisi IP endpoint tersebut.
Konfirmasi bahwa `sync_access_banking_task` (fix #42) memang dibutuhkan segera.

---

## 2. Code Fixes (tasks.py)

### Bug #1: Hardcoded Domain URL di WA Notification
**File**: `backend/app/tasks.py` — `enforce_overdue_debt_block_task`
**Sebelum**:
```python
f"Lunasi tagihan di: lpsaring.babahdigital.net\n\n"
```
**Sesudah**:
```python
_portal_url = str(app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
f"Lunasi tagihan di: {_portal_url}\n\n"
```
**Dampak**: URL selalu up-to-date dari config. Tidak perlu update code jika domain berubah.

### Bug #2: Debt Display "0 GB" untuk Tunggakan < 1 GB
**File**: `backend/app/tasks.py` — WA message body
**Sebelum**:
```python
f"Tunggakan kuota Anda sebesar *{total_debt_mb // 1024} GB* "
```
**Sesudah**:
```python
_debt_gb = total_debt_mb / 1024
_debt_display = f"{_debt_gb:.1f} GB" if _debt_gb >= 1 else f"{total_debt_mb} MB"
f"Tunggakan kuota Anda sebesar *{_debt_display}* "
```
**Dampak**: Debt 900 MB tidak lagi tampil "0 GB" di pesan WA ke user.

### Bug #3: `socket.getaddrinfo()` Tanpa Timeout (Potential Worker Hang)
**File**: `backend/app/tasks.py` — `sync_access_banking_task`
**Sebelum**: DNS lookup per domain tanpa timeout → bisa hang 20-30 detik per domain → 10+ domain = 5+ menit potensi blokir Celery worker slot.
**Sesudah**:
```python
_socket.setdefaulttimeout(5)   # 5s timeout per DNS lookup
try:
    for domain in banking_domains:
        try:
            for addr_info in _socket.getaddrinfo(domain, None, _socket.AF_INET):
                ...
        except Exception as exc:
            logger.warning("Banking sync: gagal resolve domain=%s: %s", domain, exc)
finally:
    _socket.setdefaulttimeout(None)  # restore: jangan pengaruhi socket op lain
```
**Dampak**: Worst case DNS slow → 5s timeout per domain, bukan 30s. 10 domain = max 50s, bukan 5 menit.

### Bug #4: `finally: pass` Tanpa Session Cleanup
**File**: `backend/app/tasks.py` — `enforce_overdue_debt_block_task` query block
**Sebelum**:
```python
try:
    overdue_debts = db.session.query(...).all()
finally:
    pass  # ← dead code, session tidak di-cleanup jika exception
```
**Sesudah**:
```python
try:
    overdue_debts = db.session.query(...).all()
except Exception:
    logger.exception("Overdue debt block: gagal query overdue debts dari DB.")
    db.session.remove()
    return {"checked": 0, "blocked": 0, "error": "db_query_failed"}
finally:
    db.session.remove()  # always cleanup session setelah query
```
**Dampak**: Session SQLAlchemy selalu di-cleanup setelah query. Tidak ada session leak jika DB error.

---

## 3. Docker Compose Fixes (docker-compose.prod.yml)

### Fix #5: Celery Worker Healthcheck
**Masalah**: `celery_worker` tidak punya healthcheck — jika worker diam (stuck/OOM internal),
Docker tidak detect sebagai unhealthy dan tidak restart otomatis.
**Fix**:
```yaml
healthcheck:
  test:
    - CMD-SHELL
    - "/opt/venv/bin/celery -A app.extensions inspect ping -d celery@$$HOSTNAME --timeout 10 2>&1 | grep -q pong || exit 1"
  interval: 60s
  timeout: 15s
  retries: 3
  start_period: 30s
```

### Fix #5b: Celery Beat Healthcheck
**Masalah**: `celery_beat` tidak punya healthcheck. Beat tidak support inspect ping.
**Fix**: Gunakan `pgrep` untuk cek apakah proses beat masih running:
```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f 'celery.*beat' > /dev/null || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 15s
```

### Fix #6: Redis Active Defragmentation
**Masalah**: `mem_fragmentation_ratio: 3.13` — Redis menyia-nyiakan ~3x dari kebutuhan.
**Fix**: Tambah `--activedefrag yes` ke Redis command.
```yaml
command: >
  redis-server
  --maxmemory 256mb
  --maxmemory-policy allkeys-lru
  --save ""
  --activedefrag yes        # ← baru: defrag otomatis background
```
**Catatan**: `activedefrag` tersedia sejak Redis 4.0. Aman untuk Redis 7-alpine yang dipakai.

---

## 4. Dokumentasi Fixes

### DEVELOPMENT.md — Section 5.3.1
**Sebelum**: Masih mention `docker compose down --remove-orphans` sebagai bagian dari deploy job.
**Sesudah**: Hapus step yang salah, tambah WARNING kritis tentang larangan `docker compose down`.

### DEVELOPMENT.md — Section 5.3.2
**Sebelum**: Masih berisi error CI 2026-02-15 yang "perlu observasi".
**Sesudah**: Update dengan status CI saat ini (stabil hijau) dan panduan debug jika CI merah.

### PENDING_DEVELOPMENT.md
**Update**: Timestamp update ke Session 5, tambah temuan code bugs audit, update status semua items,
tambah `⚠️ Setup Settings DB` sebagai P0 post-deploy action.

### docs/devlogs/README.md
**Update**: Tambah entry devlog sesi ini.

---

## 5. Urutan Deploy

```bash
# 1. Push ke origin (WAJIB sebelum trigger-build)
git push origin main

# 2. Trigger CI + wait hijau → trigger build image → wait → deploy
cd lpsaring
bash deploy_pi.sh --trigger-build
```

**Expected setelah deploy**:
- `dhcp_self_healed` turun ke ~0 (fix #39 aktif)
- `celery_worker` dan `celery_beat` muncul di `docker ps` dengan status `(healthy)`
- `redis` dengan flag `--activedefrag yes` mulai defrag background

---

## 6. Post-Deploy Actions (Manual Admin)

1. **Buat settings DB**:
   - `AKSES_BANKING_ENABLED=True`
   - `ENABLE_OVERDUE_DEBT_BLOCK=True`
   - `AKSES_BANKING_DOMAINS` (opsional jika ingin custom domain list)

2. **Trigger banking task** (populate Bypass_Server):
   ```
   POST /api/admin/tasks/trigger { "task": "sync_access_banking_task" }
   ```
   atau via admin panel jika ada tombol trigger.

3. **Register device** untuk 5 user `no_authorized_device`:
   - Buka `/admin/users` → search tiap nomor → add device.

4. **Monitor** di log Celery worker:
   - Pastikan `dhcp_self_healed` turun ke 0 dalam 2 siklus pertama (10 menit)
   - Pastikan `celery_worker` healthcheck muncul di `docker ps`

---

## 7. File yang Berubah di Sesi Ini

| File | Perubahan |
|------|-----------|
| `backend/app/tasks.py` | 4 code fixes: URL, MB display, socket timeout, finally block |
| `docker-compose.prod.yml` | Celery worker + beat healthcheck, Redis activedefrag |
| `DEVELOPMENT.md` | Fix section 5.3.1 (docker down warning) + 5.3.2 (CI resolved) |
| `docs/PENDING_DEVELOPMENT.md` | Full update: status semua items, tambah temuan baru |
| `docs/devlogs/2026-03-20-total-audit-fixes.md` | File ini |
| `memory/MEMORY.md` | Update production status + next priorities |
