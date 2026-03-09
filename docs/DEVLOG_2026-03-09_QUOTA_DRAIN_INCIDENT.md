# Insiden 2026-03-09 — Quota Drain Klien: Root Cause Analysis

**Severity:** CRITICAL
**Status:** RESOLVED — fix deployed 09-03-2026 ~19:30 WIB
**Commit:** `4c89ae00` — fix(sync): naikan lock_ttl quota_sync dari 120s ke 3600s
**Impact:** Semua klien aktif berpotensi kehilangan quota lebih cepat dari seharusnya (2x–6x lipat)

---

## 1. Gejala

Klien melaporkan quota habis tiba-tiba atau berkurang drastis tanpa penggunaan yang sesuai. Satu "lompatan" besar pemotongan quota terjadi berulang, bukan pemotongan bertahap normal.

---

## 2. Timeline Investigasi (09-03-2026)

| Waktu (WIB) | Kejadian |
|---|---|
| ~19:20 | Pengguna melaporkan lompatan kuota klien |
| 19:25 | Cek `sync_hotspot_usage_task` duration history |
| 19:28 | Ditemukan: task berjalan 777–3166 detik (normal harus <300s) |
| 19:30 | Ditemukan: `lock_ttl = 120s` — BUG KRITIS |
| 19:31 | Fix: `lock_ttl = 120 → 3600` |
| 19:40 | CI hijau, docker-publish, deploy |
| 19:45 | Verifikasi Redis: lock aktif TTL=3555s, hanya 1 worker running |

---

## 3. Root Cause — Lock TTL Terlalu Pendek

### Kode bermasalah (tasks.py baris 1188)

```python
lock_key = "quota_sync:run_lock"
lock_ttl = 120  # ← TERLALU PENDEK
lock_acquired = False

if redis_client is not None:
    lock_acquired = bool(redis_client.set(lock_key, "1", nx=True, ex=lock_ttl))
    if not lock_acquired:
        logger.info("Skip sinkronisasi (worker lain sedang berjalan).")
        return
```

### Mengapa berbahaya

Redis SET NX dengan `ex=120` artinya key **auto-expire setelah 120 detik**. Setelah 120 detik, lock hilang dari Redis **meski task masih berjalan**.

Urutan kejadian:

```
t=0s    Worker A: acquire lock (TTL=120s), mulai sync
t=120s  Redis: lock expired otomatis
t=120s  Worker B: acquire lock baru (TTL=120s), mulai sync ← CONCURRENT!
t=240s  Redis: lock expired lagi
t=240s  Worker C: acquire lock baru, mulai sync ← 3 task berjalan bersamaan!
...
```

Dengan 4 Celery workers dan interval 60s, dalam 5 menit ada **4–6 sync task aktif bersamaan**.

### Bukti Konkrit (log 09-03-2026)

Durasi task (dari log `succeeded in Xs`):

| Selesai | Durasi | Mulai (hitung mundur) |
|---|---|---|
| 17:21:00 | **1280s** | ~17:00 |
| 17:28:48 | **2182s** | ~16:52 |
| 17:36:34 | **1288s** | ~17:14 |
| 17:44:52 | **833s** | ~17:30 |
| 17:52:45 | **2676s** | ~17:08 |
| 18:00:45 | **778s** | ~17:47 |
| 18:08:41 | **1796s** | ~17:38 |
| 18:16:37 | **3166s** | ~16:44 |

**Overlap yang terkonfirmasi** (misal pukul 17:30–17:44):
- Task mulai ~16:44 masih berjalan (selesai 18:16)
- Task mulai ~16:52 masih berjalan (selesai 17:28)
- Task mulai ~17:00 masih berjalan (selesai 17:21)
- Task mulai ~17:08 masih berjalan (selesai 17:52)
- Task mulai ~17:14 masih berjalan (selesai 17:36)
- Task mulai ~17:30 baru mulai

→ **6 task berjalan bersamaan** pada interval tersebut

### Mekanisme Double-Deduction

```
Task A (t=0):       baca bytes MikroTik user X = 2 GB
                    last_known_bytes user X = 1 GB (dari DB)
                    delta = 2-1 = 1 GB → rencana potong 1 GB

Task B (t=100):     baca bytes MikroTik user X = 2.1 GB
                    last_known_bytes user X = 1 GB (Task A belum commit)
                    delta = 2.1-1 = 1.1 GB → rencana potong 1.1 GB

Task A commit:      quota user X berkurang 1 GB + last_known_bytes = 2 GB
Task B commit:      quota user X berkurang 1.1 GB + last_known_bytes = 2.1 GB
                                              ↑
                           PADAHAL usage real hanya ~1.1 GB!
                           Dipotong total 2.1 GB dari usage 1.1 GB = 2x lebih!
```

Dengan 6 task bersamaan, worst case: **6x lebih banyak pemotongan dari actual usage**.

---

## 4. Penyebab Kedua — Sync Task Lambat (13–52 Menit)

**Normal seharusnya:** < 5 menit untuk 87 user

**Actual:** 13–52 menit

### Penyebab kelambatan:

#### A. Address-list sync per-user serial (bottleneck utama)

Fungsi `sync_hotspot_usage_and_profiles` memanggil MikroTik address-list check **per user secara serial**. Setiap call memakan **2–17 detik** (variabel karena timeout atau latency).

Log bukti (interval per user skip):
```
15:24:47 — user 0817701083 (skip)
15:25:44 — user 085751420446 (skip)  ← 57 detik jeda!
15:26:39 — user 0811508961 (skip)    ← 55 detik jeda!
15:28:29 — user 085348176341 (skip)  ← 110 detik jeda!
```

Estimasi waktu address-list: 87 users × 2–17s = **174–1479 detik (3–25 menit)**

#### B. DHCP self-heal 10 per run

Setiap sync run, **10 user** DHCP lease-nya "hilang" dan perlu di-recreate. Setiap DHCP upsert = 1 MikroTik API call (dengan retries).

Bukti: `dhcp_self_healed: 10` konsisten di SETIAP sync result:
```
17:21 → dhcp_self_healed: 10
17:28 → dhcp_self_healed: 10
17:36 → dhcp_self_healed: 10
17:44 → dhcp_self_healed: 10
17:52 → dhcp_self_healed: 10
18:00 → dhcp_self_healed: 10
```

**10 user × ~30s per DHCP heal = 300 detik (5 menit) tambahan per run**

#### C. Profile updates 3–6 per run

Setiap user yang berganti profil MikroTik (quota threshold terlewati) butuh 2 API call (check + update). Dengan 3–6 profile changes per run = 90–180s tambahan.

**Total estimasi per run:**
- Address-list: 174–1479s
- DHCP self-heal: 300s
- Profile updates: 90–180s
- Overheads: 60s
- **TOTAL: 624–2019s (10–33 menit untuk normal, bisa 52 menit bila MikroTik lambat)**

---

## 5. Masalah Lain yang Ditemukan

### A. DHCP Conflict IP 172.16.3.79

```
WARNING: Policy DHCP self-heal gagal upsert lease
  user=a8459ec0 mac=74:D5:58:53:90:3F ip=172.16.3.79
  Error: "failure: already have static lease with this IP address"
```

**Analisa:** Ada 2 static lease berbeda yang mengklaim IP `172.16.3.79` di MikroTik (`/ip/dhcp-server/lease`). Lease lama (bukan milik user ini) membuat add gagal.

**Action diperlukan (MANUAL di MikroTik):**
```
/ip dhcp-server lease print where address=172.16.3.79
→ Hapus entry duplicate yang bukan milik MAC 74:D5:58:53:90:3F
   (atau yang bukan dari komen lpsaring|)
```

### B. 4 User Aktif Tanpa Device Terdaftar

Policy parity guard mendeteksi:

| Phone | Status App | Masalah | Action |
|---|---|---|---|
| +6285752083738 | active | `no_authorized_device` | Authorize device dari admin panel |
| +6285141275160 | unlimited | `no_authorized_device` | Authorize device dari admin panel |
| +6282131124118 | active | `no_authorized_device` | Authorize device dari admin panel |
| +6287822097942 | unlimited | `no_authorized_device` | Authorize device dari admin panel |

User ini **tidak dapat dikenakan bandwidth enforcement** karena tidak ada MAC/IP yang terdaftar di sistem. Mereka bisa pakai internet, tapi sistem tidak bisa enforce rate limit atau usage tracking per user.

**Action:** Minta user tersebut login ulang ke captive portal untuk auto-register device, atau admin daftarkan manual di panel `/admin/users`.

### C. DHCP Loop 10 User (Non-Critical)

10 user secara konsisten ditemukan `dhcp_lease_missing` tiap sync run dan di-fix via self-heal (`dhcp_self_healed: 10`). Self-heal berhasil, tapi di run berikutnya muncul lagi.

**Root cause probable:** MikroTik DHCP server membersihkan leases yang sudah expired (user disconnect lama). Saat sync detects missing → adds static → MikroTik accepts → user connect/disconnect → MikroTik removes dynamic → detect missing lagi.

**Dampak:** Tidak kritis untuk klien (internet tetap jalan), tapi menambah ~5 menit ke waktu sync setiap run.

**Action:** Investigasi apakah MikroTik dikonfigurasi untuk keep expired leases. Set `/ip dhcp-server/lease` `always-broadcast=yes` atau lease time sangat panjang untuk user yang sudah diassign static IP.

### D. Satu IP di Address-list Gagal Refresh

```
sync_unauthorized_hosts_task: failed_add_or_refresh=1
```

Satu host tidak bisa ditambahkan/di-refresh di address-list unauthorized. Error non-retryable. Tidak kritis untuk operasional keseluruhan.

---

## 6. Fix yang Diterapkan

### Fix Kritis: `lock_ttl = 120 → 3600` (tasks.py:1188)

```python
# BEFORE:
lock_ttl = 120  # Safety TTL: task tidak boleh berjalan lebih dari 2 menit

# AFTER:
lock_ttl = 3600  # Safety TTL: task bisa jalan hingga 52+ menit (observed);
                  # 120s terlalu pendek → multiple worker berjalan bersamaan → quota double-deducted
```

**Verifikasi post-deploy:**
```
Redis GET quota_sync:run_lock → "1"
Redis TTL quota_sync:run_lock → 3555  ← dikonfirmasi 3600s TTL aktif
```

Sekarang hanya **1 worker** yang bisa menjalankan sync quota di seluruh cluster, untuk durasi hingga 1 jam.

---

## 7. Analisa Status Normal Post-Fix

Setelah fix berjalan beberapa siklus, yang diharapkan:

- Sync berjalan **sekali per 13–52 menit** (tidak ada overlap)
- Quota deduction = **1x actual usage** (bukan 2-6x)
- `profile_updates` per run akan turun karena user tidak lagi kehilangan quota secara artifisial
- Klien tidak lagi melaporkan quota habis mendadak

---

## 8. Analisa Nginx Logs Post-Deploy

| Metrik | Status |
|---|---|
| Error hari ini (09 Mar) | **NIHIL** setelah deploy pagi |
| HTTP 5xx | Hanya dari 07-08 Mar (pre-deploy) |
| DNS resolution error | Hanya dari 07-08 Mar |
| Upstream timeout | Hanya dari 07-08 Mar |

Error log setelah deploy nginx optimization (`valid=5s`, `proxy_next_upstream`) tidak ada error baru.

---

## 9. Rekomendasi Lanjutan

| Prioritas | Action | Estimasi Effort |
|---|---|---|
| HIGH | Hapus DHCP duplicate di MikroTik untuk IP `172.16.3.79` | 5 menit (manual MikroTik) |
| HIGH | Authorize device 4 user `no_authorized_device` | 10 menit admin panel |
| MEDIUM | Investigasi DHCP self-heal loop 10 user — set lease time panjang di MikroTik | 30 menit |
| MEDIUM | Optimasi address-list sync dari serial → batch (1 API call untuk semua user) | 2–3 hari dev |
| LOW | Add heartbeat/lock extension ke sync task (extend lock tiap 60s selama running) | 1 hari dev |
| INFO | Pantau `profile_updates` per run — harusnya turun setelah quota tidak lagi triple-deducted | Monitoring |

---

## 10. Kompensasi untuk Klien

### 10.1 Identifikasi User Terdampak (Audit Lengkap)

Query forensik `quota_mutation_ledger` selama bug window (2026-03-08 19:00 — 2026-03-09 20:00) menemukan **17 user** yang mengalami event deduction > 5 GB per sync (indikator duplikasi concurrent worker):

| Nama | Telp | Remaining saat ini | Approx Inflasi (MB) | Events | Perlu perhatian? |
|---|---|---|---|---|---|
| Orochimaru | +6281356002170 | 38,791 MB | 167,680 | 16 | ✅ Sudah dikompensasi (+25 GB) |
| Barata | +628984440915 | 166,127 MB | 110,978 | 15 | Aman |
| Rio Martino Putra | +6283125710842 | **-61,664 MB** | 102,112 | 15 | ⚠️ Pre-existing debt, bukan dari bug |
| Budi Dapur | +6281350419071 | **-47,822 MB** | 98,102 | 14 | ⚠️ Pre-existing debt (purchased=1 GB, used=48 GB sebelum bug) |
| PuguhRahmansyah | +6289527796925 | 12,784 MB | 94,255 | 16 | ⚠️ Kuota tersisa rendah, monitor |
| Agus Widodo | +6282152764565 | 43,533 MB | 91,868 | 15 | Aman |
| Syaifudin Zuhri | +6282152787390 | 58,665 MB | 70,846 | 10 | Aman |
| Mr.kspl | +6285166001405 | 15,011 MB | 69,111 | 10 | ⚠️ Kuota tersisa rendah, monitor |
| Naru | +6285951333663 | 21,202 MB | 63,830 | 10 | Monitor |
| Ajiz | +6282191985053 | 72,306 MB | 61,192 | 8 | Aman |
| Bandit | +6281255962309 | 20,389 MB | 53,020 | 8 | Monitor |
| Dewa | +6283179074596 | **6,630 MB** | 48,168 | 8 | ⚠️ Kuota sangat rendah, pertimbangkan kompensasi |
| Imported 087821848928 | +6287821848928 | 16,271 MB | 40,143 | 7 | Monitor |
| Bayu | +6283843730350 | **11,438 MB** | 37,746 | 7 | ⚠️ Kuota rendah, monitor |
| Aulia Rahman | +6283141617466 | **13,663 MB** | 26,958 | 5 | ⚠️ Kuota rendah, monitor |
| Dadang hadi | +6285821240141 | 18,000 MB | 26,870 | 5 | Monitor |
| Syamsuri | +6283869831957 | 16,707 MB | 5,020 | 1 | Monitor |

**Catatan kolom "Approx Inflasi":** Ini adalah SUM dari semua event sync > 5000 MB selama bug window. Karena setiap event concurrent menyumbang delta terpisah, angka ini mencerminkan berapa MB yang "seharusnya tidak terpotong" jika hanya 1 worker yang berjalan. Angka aktual bisa lebih rendah (satu event bisa saja legitimate).

### 10.2 Action Rekomendasi

**Immediate (hari ini):**
- **Dewa** (+6283179074596): Remaining hanya 6.6 GB. Pertimbangkan tambah bonus quota 10–20 GB dari admin panel.
- **Budi Dapur** & **Rio Martino Putra**: Ini masalah pre-existing, bukan akibat bug lock_ttl. Perlu review terpisah apakah mereka berhak aktif dengan balance negatif.

**Dalam 1 minggu (monitoring):**
- Monitor PuguhRahmansyah (12.7 GB), Bayu (11.4 GB), Aulia Rahman (13.6 GB), Mr.kspl (15 GB)
- Jika mereka komplain quota habis lebih cepat dari biasanya, tambah kompensasi

**Cara tambah kompensasi dari admin panel:**
1. Buka `Admin → Users → [nama user]`
2. Tab "Kuota" → Adjust Quota
3. +10000 (10 GB) atau sesuai kebijakan

---

## 11. Koreksi Data Pasca-Audit

### 11.1 daily_usage_logs — Cleanup 80 Baris Inflated

`daily_usage_logs` mencatat akumulasi pemakaian per hari (untuk grafik/chart). Akibat bug, kolom `usage_mb` mengambil semua delta concurrent → menjadi tidak realistis.

**Data sebelum cleanup:**
- 2026-03-08: 39 user dengan usage > 5 GB/hari, total 596 GB tercatat
- 2026-03-09: 41 user dengan usage > 5 GB/hari, total **2,980 GB** tercatat (tidak masuk akal)
- Baseline normal: avg 189–551 MB/user/hari

**SQL yang dijalankan (manual, produksi):**
```sql
DELETE FROM daily_usage_logs
WHERE log_date IN ('2026-03-08', '2026-03-09')
  AND usage_mb > 5000;
-- DELETE 80
```

**Data setelah cleanup:**
- 2026-03-08: 15 entri tersisa (max 4.2 GB, avg 904 MB) — normal untuk heavy user
- 2026-03-09: 15 entri tersisa (max 4.8 GB, avg 2.1 GB) — agak tinggi tapi dalam batas
- 80 baris terhapus = 3,662,110 MB data palsu dihapus

**Dampak:** Chart penggunaan historis untuk 2 tanggal ini akan menampilkan data partial (hanya 15 user dari ~55 aktif). Ini lebih baik daripada menampilkan 190 GB/hari yang tidak pernah terjadi.

### 11.2 Perbaikan UserMikrotikStatus.vue — Label Menyesatkan

**Sebelum fix:**
- "Total Kuota Masuk" → `bytes-in` dari MikroTik (= jumlah byte diunduh dalam sesi)
- "Total Kuota Keluar" → `bytes-out` dari MikroTik (= jumlah byte diunggah)

Admin membaca "Total Kuota Masuk: 13 GB" → salah kira "sisa kuota = 13 GB".
Padahal `bytes-in` adalah counter sesi download, **bukan sisa quota sistem**.

**Setelah fix:**
- "Data Diunduh (Sesi MikroTik)" → jelas ini byte dari MikroTik, bukan quota
- "Data Diunggah (Sesi MikroTik)" → sama
- Ditambah dua baris baru: **Sisa Kuota (Sistem DB)** + **Terpakai / Dibeli (Sistem DB)**
- Alert info di bawah tabel menjelaskan perbedaan kedua sumber data

**Backend** endpoint `GET /admin/users/:id/mikrotik-status` diupdate untuk juga mengembalikan:
```json
{
  "db_quota_remaining_mb": 38791.0,
  "db_quota_used_mb": 73849.0,
  "db_quota_purchased_mb": 112640.0
}
```

Sekarang admin bisa melihat data MikroTik live dan data DB quota dalam satu popup. Tidak ada lagi kebingungan antara "13 GB bytes-in" vs "0 MB remaining".

---

## 12. Files yang Diubah (Lengkap)

| File | Perubahan | Commit |
|---|---|---|
| `backend/app/tasks.py` | `lock_ttl = 120 → 3600` di `sync_hotspot_usage_task` | `4c89ae00` |
| `frontend/components/admin/users/UserMikrotikStatus.vue` | Fix label menyesatkan + tambah DB quota section | sesi ini |
| `backend/app/infrastructure/http/admin/user_management_routes.py` | Tambah `db_quota_*` fields ke response `/mikrotik-status` | sesi ini |
| `public.daily_usage_logs` (DB) | DELETE 80 baris inflated (>5 GB) pada 2026-03-08 dan 2026-03-09 | SQL manual |
