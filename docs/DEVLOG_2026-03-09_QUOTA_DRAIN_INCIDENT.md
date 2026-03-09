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

Klien yang kehilangan quota akibat bug ini perlu diidentifikasi dan quota-nya dipulihkan secara manual.

**Cara estimasi dampak per klien:**
- Lihat log `updated_usage` dari `sync_result` antara jam yang terindikasi
- Bandingkan dengan penggunaan real MikroTik (`/ip hotspot active print detail`)
- Bila ada klien yang quota-nya 0 padahal baru beli, tambah manual dari admin panel

**Periode dampak:** Bug ada sejak kode dengan `lock_ttl=120` pertama kali di-deploy. Berdasarkan git log, perlu dicek tanggal commit pertama yang memasukkan nilai 120 ini.

---

## 11. Files yang Diubah

| File | Perubahan | Commit |
|---|---|---|
| `backend/app/tasks.py` | `lock_ttl = 120 → 3600` di `sync_hotspot_usage_task` | `4c89ae00` |
