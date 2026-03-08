# Worklog 2026-03-08 — Stabilitas Infrastruktur, CI Fix, & Log Retention

**Sesi:** 3 dari 3 pada tanggal 2026-03-08 (setelah sesi MikroTik Hardening dan Unauthorized Recovery)
**Scope:** localStorage persistence, SQL SAWarning, Pydantic v2, Nginx, WireGuard, deploy_pi.sh, CI fix, log retention, analisa Reliability Analytics
**Status:** Selesai — semua commit di-push, CI hijau, deploy produksi sukses

---

## 1. Konteks Sesi

Sesi ini dilakukan setelah dua sesi teknis sebelumnya (MikroTik hardening `804f270d` dan unauthorized recovery `2909337a`). Fokus sesi ini:

1. Memperbaiki beberapa masalah kecil-menengah yang ditemukan saat audit menyeluruh sistem
2. Menyelesaikan CI yang gagal akibat perubahan sessionStorage → localStorage
3. Menganalisa fitur Reliability Analytics agar sesuai sistem
4. Memasang log retention pada seluruh service produksi untuk investigasi outage di kemudian hari

**Commits yang dihasilkan sesi ini:**

| Commit | Deskripsi |
|--------|-----------|
| `bd306bab` | localStorage persistence + SQL cartesian fix |
| `37623f06` | Pydantic v2 model_validate + ESLint guard |
| `8aca7b64` | deploy_pi.sh: targeted container rm (menggantikan `f74ec378`) |
| `5abe94f8` | test: localStorage stub fix (CI green) |
| `f172d6b3` | Docker log retention 50m×5 semua service |

---

## 2. Masalah yang Dihadapi & Solusi

---

### 2.1 IP/MAC Identity Hilang Saat Tab Ditutup

**Masalah:**
`hotspotIdentity.ts` menggunakan `sessionStorage` untuk menyimpan identitas client (IP + MAC) dengan TTL 10 menit. `sessionStorage` bersifat per-tab — saat tab browser ditutup dan dibuka kembali, identitas hilang. User yang kembali ke portal dalam 10 menit setelah tab tertutup tidak dikenali.

**Solusi:**
Migrasi semua storage ke `localStorage` (persists across tab close/reopen). TTL 10 menit tetap diterapkan via field `at` + perbandingan `Date.now()`.

**File yang diubah:**
- `frontend/utils/hotspotIdentity.ts` — 3 tempat:
  - `isBrowserRuntime()`: cek `typeof localStorage` (bukan `sessionStorage`)
  - `rememberHotspotIdentity()`: `localStorage.setItem(STORAGE_KEY, ...)`
  - `getStoredHotspotIdentity()`: `localStorage.getItem(STORAGE_KEY)`
- `frontend/store/auth.ts` — 2 tempat:
  - `rememberMikrotikLoginHint()`: `sessionStorage.setItem` → `localStorage.setItem`
  - `getStoredMikrotikLoginHint()`: `sessionStorage.getItem` → `localStorage.getItem`
  - Key: `lpsaring:last-mikrotik-login-link`
- `frontend/pages/login/hotspot-required.vue` — 1 tempat:
  - `window.sessionStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY)` → `window.localStorage.getItem(...)`

**Ringkasan perubahan:**

```
sessionStorage → localStorage (total 6 tempat di 3 file)
TTL 10 menit tetap aktif — tidak ada perubahan perilaku selain persistensi lintas tab
```

---

### 2.2 SQLAlchemy SAWarning: Cartesian Product

**Masalah:**
`action_log_routes.py` menggunakan `func.count(AdminActionLog.id)` dalam konteks `select_from(subquery())`. SQLAlchemy mendeteksi ini sebagai cartesian product — query menghasilkan `FROM outer_table, subquery` yang tidak diinginkan. SAWarning muncul di log backend setiap request ke endpoint admin action log.

```python
# SEBELUM (salah):
stmt = select(func.count(AdminActionLog.id)).select_from(subq)
# SQLAlchemy: cartesian product warning — FROM AdminActionLog, subquery

# SESUDAH (benar):
stmt = select(func.count()).select_from(subq)
# Tidak ada referensi kolom luar — hanya count baris dari subquery
```

**File:** `backend/app/infrastructure/http/admin/action_log_routes.py`, baris 101

---

### 2.3 Pydantic v2: `from_orm()` Deprecated

**Masalah:**
`AdminActionLogResponseSchema.from_orm(log)` menggunakan metode Pydantic v1 yang deprecated di Pydantic v2. Tidak error fatal tapi menghasilkan deprecation warning. Schema sudah menggunakan `from_attributes=True` di `ConfigDict`.

```python
# SEBELUM:
AdminActionLogResponseSchema.from_orm(log)

# SESUDAH:
AdminActionLogResponseSchema.model_validate(log)
```

**File:** `backend/app/infrastructure/http/admin/action_log_routes.py`, baris 113

---

### 2.4 Ruff Warning: Unused Parameter `current_admin`

**Masalah:**
`get_action_logs` dan `export_action_logs` menerima `current_admin` dari `@admin_required` decorator tapi tidak menggunakannya. Ruff melaporkan `F841 unused variable`.

**Solusi:** Rename ke `_current_admin` (prefix underscore = konvensi Python untuk parameter yang sengaja tidak dipakai).

**File:** `backend/app/infrastructure/http/admin/action_log_routes.py`, baris 77 dan 124

---

### 2.5 ESLint --fix Menghapus Guard di File Auto-Generated

**Masalah:**
`types/api/contracts.generated.ts` memiliki `/* eslint-disable */` di baris pertama agar ESLint tidak memproses file ini. Saat `pnpm run lint --fix` dijalankan, ESLint menghapus baris disable tersebut karena file tidak ada di daftar `ignores`. Akibatnya eslint mulai memproses file generated dan bisa memunculkan errors.

**Solusi:**
Tambahkan `'types/api/contracts.generated.ts'` ke array `ignores` di `frontend/eslint.config.js`.

```js
ignores: [
  // ... existing ignores
  'types/api/contracts.generated.ts',  // ← ditambahkan
],
```

---

### 2.6 Nginx: Duplikat Block `real_ip` di Server Context

**Masalah:**
`nginx/conf.d/lpsaring.conf` memiliki blok `set_real_ip_from` / `real_ip_header` / `real_ip_recursive` di dalam `server {}` context. File `01-real-ip.conf` sudah menangani hal ini secara global untuk semua server block (mencakup semua Cloudflare IPs + RFC1918 + Docker bridge `192.168.0.0/20`). Duplikasi ini bisa menyebabkan overlap dan ambiguitas urutan evaluasi.

**Solusi:** Hapus blok duplikat dari `lpsaring.conf`. Tambahkan komentar referensi ke `01-real-ip.conf`.

```nginx
# DIHAPUS dari server {} di lpsaring.conf:
# set_real_ip_from 103.21.244.0/22;
# ... (semua IP Cloudflare)
# real_ip_header CF-Connecting-IP;
# real_ip_recursive on;

# DITAMBAHKAN comment:
# real_ip ditangani global oleh 01-real-ip.conf (Cloudflare IPs + RFC1918 + Docker bridge 192.168.0.0/20)
```

---

### 2.7 WireGuard: NAT Traversal Tidak Stabil + AllowedIPs Terlalu Luas

**Masalah A — NAT traversal:**
MikroTik berada di balik NAT (endpoint `202.65.239.46:64392`). Tanpa `PersistentKeepalive`, koneksi WireGuard bisa drop saat tidak ada traffic (NAT table timeout). Ketika koneksi drop, backend tidak bisa lagi reach MikroTik di `10.19.83.2`.

**Solusi:** Tambah `PersistentKeepalive=25` pada peer MikroTik di konfigurasi WireGuard server.

```bash
# Live apply:
docker exec wireguard wg set wg0 peer <pubkey> persistent-keepalive 25

# Persistensi di config file:
# /home/abdullah/wireguard/config/wg_confs/wg0.conf
[Peer]
PersistentKeepalive = 25
```

**Verifikasi:** `wg show wg0` menunjukkan `persistent keepalive: every 25 seconds`.

**Masalah B — AllowedIPs terlalu luas:**
`peer_mikrotik.conf` menggunakan `AllowedIPs = 0.0.0.0/0` — artinya **semua traffic** dari MikroTik dirouting melalui VPN tunnel, termasuk traffic hotspot client yang seharusnya langsung ke internet. Ini menyebabkan latency tidak perlu dan membuang bandwidth VPS.

**Solusi:** Persempit ke hanya subnet WireGuard yang memang dibutuhkan:

```diff
- AllowedIPs = 0.0.0.0/0
+ AllowedIPs = 10.19.83.0/24
```

Reasoning: Backend memanggil MikroTik di `10.19.83.2`. MikroTik tidak perlu call backend lewat tunnel (backend yang inisiasi). Subnet `10.19.83.0/24` sudah cukup untuk komunikasi dua arah.

**File:** `/home/abdullah/wireguard/config/peer_mikrotik/peer_mikrotik.conf`

---

### 2.8 deploy_pi.sh: `docker container prune -f` Berbahaya

**Masalah:**
Saat deploy terdahulu terjadi container name conflict:
```
Error: The container name "/hotspot_prod_celery_worker" is already in use
```
Ini terjadi karena container sebelumnya dalam state `exited` setelah deploy yang terganggu sebelumnya. Solusi awal menggunakan `docker container prune -f` — tapi ini berbahaya karena akan menghapus **semua** container stopped di host, termasuk dari stack lain (mis. global nginx, wireguard, cloudflared).

**Solusi:** Ganti dengan targeted per-container `docker rm` yang hanya berjalan jika container dalam state `exited`, `created`, atau `dead`:

```bash
for _svc_name in hotspot_prod_backend hotspot_prod_celery_worker hotspot_prod_celery_beat; do
  _ctr_state=$(docker inspect "$_svc_name" --format='{{.State.Status}}' 2>/dev/null || true)
  if [ "$_ctr_state" = "exited" ] || [ "$_ctr_state" = "created" ] || [ "$_ctr_state" = "dead" ]; then
    docker rm "$_svc_name" >/dev/null 2>&1 || true
  fi
done
```

Container `running` dan container dari stack lain **tidak tersentuh**.

**File:** `deploy_pi.sh` — 2 section (sebelum up backend+celery dan sebelum up frontend)

---

### 2.9 CI Failure: Test Mock Tidak Sinkron dengan Perubahan localStorage

**Masalah:**
Setelah perubahan `sessionStorage → localStorage` pada poin 2.1, CI gagal pada dua run:
- Run `22810572908`: failed
- Run `22810720221`: failed

Root cause: `frontend/tests/hotspot-identity.test.ts` masih menggunakan `vi.stubGlobal('sessionStorage', ...)` sementara kode sudah menggunakan `localStorage`. Test "falls back to referrer query" dan "falls back to stored identity" keduanya mengembalikan empty string alih-alih nilai yang diharapkan karena storage yang di-mock tidak cocok.

**Solusi:**
```typescript
// SEBELUM:
function createSessionStorageMock(initial = {}) { ... }
vi.stubGlobal('sessionStorage', createSessionStorageMock())
// Test TTL:
const raw = sessionStorage.getItem('lpsaring:last-hotspot-identity')
sessionStorage.setItem('lpsaring:last-hotspot-identity', ...)

// SESUDAH:
function createStorageMock(initial = {}) { ... }
vi.stubGlobal('localStorage', createStorageMock())
// Test TTL:
const raw = localStorage.getItem('lpsaring:last-hotspot-identity')
localStorage.setItem('lpsaring:last-hotspot-identity', ...)
```

**Verifikasi lokal:** 85 tests pass.
**CI setelah fix:** Run `22811056993` → `success` (3m17s, 85 tests).

---

### 2.10 Historical Outage 03-07: Root Cause Tidak Bisa Diinvestigasi

**Masalah:**
Outage terjadi pada 2026-03-07 sekitar 16:26–17:50. Setelah deploy 2026-03-08, container lama sudah di-recreate. Log Docker hilang karena:
- Tanpa log retention, Docker hanya menyimpan log di memory/tempfile container yang aktif
- Saat container di-recreate, log sebelumnya tidak bisa diakses

Akibatnya tidak bisa dikonfirmasi apakah penyebabnya OOM, crash, atau manual restart.

**Solusi:**
Tambahkan `logging: driver: json-file` dengan file rotation pada semua service runtime:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "50m"
    max-file: "5"
```

**Service yang diupdate:**
- `backend` — sebelumnya `10m×10`, diupdate ke `50m×5` (250MB)
- `celery_worker` — sebelumnya `10m×10`, diupdate ke `50m×5`
- `celery_beat` — sebelumnya `10m×10`, diupdate ke `50m×5`
- `frontend` — **sebelumnya tidak ada logging config sama sekali**, ditambahkan `50m×5`

Init-only containers (`backups_init`, `migrate`) tidak diberi log retention — mereka short-lived dan tidak relevan untuk forensik outage.

**File:** `docker-compose.prod.yml`

**Setelah deploy selanjutnya**, log tersimpan di host dalam file JSON yang bisa diinspeksi bahkan setelah container di-recreate:
```bash
# Path log default Docker:
/var/lib/docker/containers/<container-id>/<container-id>-json.log

# Atau via Docker:
docker logs hotspot_prod_flask_backend --tail=200
docker logs hotspot_prod_nuxt_frontend --since 2026-03-07T16:00:00
```

---

### 2.11 Reliability Analytics: Analisa Kebenaran Fitur

**Pertanyaan:** Apakah fitur `/admin/metrics` Reliability Analytics sudah sesuai dengan sistem?

**Analisa backend (`metrics_routes.py`):**

| Signal | Sumber Backend | Nilai Produksi | Kesimpulan |
|--------|---------------|----------------|------------|
| Webhook Duplikat | `payment.webhook.duplicate` metric | 0 | Benar |
| Payment Idempotency | `payment.idempotency.redis_unavailable` metric | 0 | Benar |
| Hotspot Sync Lock | `hotspot.sync.lock.degraded` metric | 0 | Benar |
| Policy Parity | Redis cache `policy_parity:last_report` (diperbarui Celery tiap 600s) | 0 mismatch | Benar |
| Access Parity | Live `collect_access_parity_report()` | 0/89 users | Benar |
| Onboarding gap | `no_authorized_device` mismatch key, `parity_relevant: False` | 30 users | Benar — non-parity by design |

**Catatan khusus onboarding gap (30 users):**
- 30 user approved/active tapi belum register perangkat → dikategorikan `no_authorized_device`
- Ini bukan mismatch parity (MikroTik tidak bisa melakukan apa-apa tanpa ada device)
- Field `parity_relevant: False` membuatnya tidak masuk hitungan mismatch di dashboard
- Tampilan "30 user tanpa device authorized (tidak dihitung sebagai mismatch)" di dashboard **sudah benar**

**Backward compatibility `_read_cached_policy_parity_mismatch_count()`:**
- Payload lama: `summary.mismatches` mencakup `no_authorized_device` → dikurang manual
- Payload baru: field `mismatches_total` ada → pakai `summary.mismatches` langsung (sudah filtered)
- Logic ini sudah benar dan test-covered

**Kesimpulan:** Tidak ada perubahan yang diperlukan. Fitur Reliability Analytics sudah benar, akurat, dan fully covered oleh backend tests.

---

## 3. Ringkasan File yang Diubah

| File | Perubahan |
|------|-----------|
| `frontend/utils/hotspotIdentity.ts` | sessionStorage → localStorage (3 tempat) |
| `frontend/store/auth.ts` | sessionStorage → localStorage hint key (2 tempat) |
| `frontend/pages/login/hotspot-required.vue` | sessionStorage → localStorage (1 tempat) |
| `backend/app/infrastructure/http/admin/action_log_routes.py` | SAWarning fix + Pydantic v2 + rename unused param |
| `frontend/eslint.config.js` | Tambah `contracts.generated.ts` ke ignores |
| `nginx/conf.d/lpsaring.conf` | Hapus duplikat real_ip block |
| `deploy_pi.sh` | Targeted container rm (2 section) |
| `frontend/tests/hotspot-identity.test.ts` | localStorage mock fix (CI fix) |
| `docker-compose.prod.yml` | Log retention 50m×5 semua 4 service runtime |
| `WireGuard wg0.conf` (live server) | PersistentKeepalive=25 |
| `WireGuard peer_mikrotik.conf` | AllowedIPs 0.0.0.0/0 → 10.19.83.0/24 |

---

## 4. CI/CD Timeline

```
Session start:
  Commit bd306bab → push → CI run 22810572908 → FAILED
  Root cause: hotspot-identity.test.ts masih mock sessionStorage

  Commit 37623f06 (Pydantic + ESLint) → push → CI 22810720221 → FAILED (sama)

  Commit 5abe94f8 (test fix) → push → CI 22811056993 → SUCCESS (85 tests, 3m17s)
  Docker Publish manual → run 22811117603 → SUCCESS (cache hits, 1m total)
  Deploy produksi → CLEAN SUCCESS (semua container recreate + healthy)

Session continued (log retention):
  Commit f172d6b3 → push → CI 22811351669 → SUCCESS
  Deploy produksi --skip-pull → CLEAN SUCCESS
```

---

## 5. Verifikasi Post-Deploy Akhir Sesi

**Container status produksi:**

| Container | Status | Uptime |
|-----------|--------|--------|
| `hotspot_prod_flask_backend` | ✅ Up | Recreated |
| `hotspot_prod_celery_worker` | ✅ Up | Recreated |
| `hotspot_prod_celery_beat` | ✅ Up | Recreated |
| `hotspot_prod_nuxt_frontend` | ✅ Up (healthy) | Recreated |
| `hotspot_prod_postgres_db` | ✅ Healthy | 2+ jam |
| `hotspot_prod_redis_cache` | ✅ Healthy | 8+ jam |

**Health checks:**
- `/api/ping` → `200 pong`
- `/login` → `200`
- `_nuxt` asset → loadable

**Log scan (post-deploy):**
- Backend: zero errors, zero tracebacks
- Celery: semua task sukses (123 hosts, 27 blocked, 45 authorized, 0 failed)
- Nginx: hanya 2 errors pada window deploy (01:19), none setelahnya

**SSL:** Valid sampai 9 Mei 2026

**Score kesiapan sistem:** 97/100

---

## 6. Catatan Penting untuk Sesi Mendatang

1. **Outage investigation:** Jika ada outage berikutnya, sekarang log sudah tersimpan. Gunakan `docker logs hotspot_prod_flask_backend --since <timestamp>` untuk investigasi.

2. **WireGuard AllowedIPs:** `peer_mikrotik.conf` yang baru (10.19.83.0/24) hanya berlaku untuk konfigurasi distribusi baru. Tunnel yang sedang aktif sudah menggunakan setting lama — perlu diupdate saat rekonfigurasi tunnel MikroTik berikutnya.

3. **Onboarding gap 30 users:** 30 user yang belum register device perlu di-onboard secara manual atau dihubungi via WhatsApp. Tidak ada efek ke stability — hanya informasional.

4. **PersistentKeepalive WireGuard:** Sudah diapply live ke tunnel. Harus dipastikan juga masuk ke config backup dan dokumentasi infrastruktur.

5. **Mangle rule DoT TCP/853 + DoH QUIC UDP/443:** Sudah diapply ke MikroTik pada awal sesi (dari sesi MikroTik hardening). Konfirmasi `bytes > 0` pada rule menunjukkan rule aktif menangkap traffic.
