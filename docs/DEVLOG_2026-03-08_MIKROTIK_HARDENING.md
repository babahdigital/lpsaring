# Devlog: MikroTik Hardening + Celery Beat Optimization
**Tanggal:** 2026-03-08
**Scope:** MikroTik RouterOS (10.19.83.2) + backend Celery task scheduler
**Status:** ✅ Deployed (commit `804f270d`)

---

## Ringkasan Sesi

Sesi ini melakukan audit holistik dan hardening penuh sistem lpsaring setelah sesi performa sebelumnya (`e01773ab`). Fokus: stabilitas MikroTik queue, keamanan DNS, dan robustness Celery beat.

---

## 1. Perbaikan MikroTik (Langsung via API Port 8728)

### 1.1 Anti-Tethering Scope Fix

**Masalah:** Mangle rule "Anti-Tethering" (action=change-ttl set:1, chain=postrouting) memiliki `dst-address=172.16.0.0/20` yang mencakup semua VLAN (IoT, Kamtib, Privated, Registrasi, Tamu, Aula, Wartelpas, Klien). Seharusnya hanya berlaku untuk VLAN Klien.

**Perbaikan:**
```
dst-address: 172.16.0.0/20  →  172.16.2.0/23
```

**Rule ID:** `*16E` (index bergeser ke [29] setelah penambahan DoH rule)
**Efek:** TTL=1 hanya diterapkan ke traffic VLAN Klien (172.16.2.0-3.255), bukan ke subnet staf/manajemen.

**Cara kerja anti-tethering:**
- Router set TTL=1 pada paket keluar ke VLAN Klien
- HP/laptop yang menerima paket TTL=1 tidak bisa meneruskan (TTL turun ke 0 di NAT HP)
- Hanya berlaku IPv4; tethering IPv6 tidak terdeteksi (IPv6 belum aktif di VLAN Klien — aman)

---

### 1.2 Queue `limit-at` untuk VLAN Child Queues

**Masalah:** Semua child queue VLAN memiliki `limit-at=0` (tidak ada jaminan minimum bandwidth). Saat traffic heavy di `Limit-Dinamis-Per-User-*`, VLAN staf (Kamtib, Privated, Registrasi) bisa starved.

**Perbaikan — nilai `limit-at` yang diterapkan:**

| Queue | VLAN | Upload limit-at | Download limit-at |
|-------|------|-----------------|-------------------|
| IoT | 172.16.6.0/24 | 512k | 2M |
| Kamtib | 172.16.8.0/24 | 2M | 8M |
| Privated | 172.16.4.0/24 | 2M | 8M |
| Registrasi | 172.16.9.0/24 | 3M | 12M |
| Tamu | 172.16.10.0/24 | 1M | 5M |
| Aula | 172.16.11.0/24 | 2M | 6M |
| Wartelpas | 172.16.12.0/24 | 2M | 15M |

`limit-at` adalah guaranteed minimum floor — VLAN ini dijamin mendapat bandwidth minimal meskipun `Utama` (50M/200M) sedang penuh.

---

### 1.3 Burst pada PCQ Queue paket-fup

**Queue:** `Limit-Dinamis-Per-User-20M`
**packet-marks:** `paket-fup`
**Queue type:** `PCQ-Upload-10M/PCQ-Download-20M`

**Sebelum:** Tidak ada burst.

**Sesudah:**
```
burst-limit:     30M/60M   (per PCQ flow)
burst-threshold: 5M/10M
burst-time:      6s/6s
```

User FUP dapat boost awal 60M download selama 6 detik, lalu normalise ke 20M/10M setelah traffic melebihi threshold 10M. Berguna untuk loading halaman web pertama.

---

### 1.4 Burst pada PCQ Queue paket-aktif

**Queue:** `Limit-Dinamis-Per-User-30M`
**packet-marks:** `paket-aktif`
**Queue type:** `PCQ-Upload-20M/PCQ-Download-30M`

**Sesudah:**
```
burst-limit:     60M/100M
burst-threshold: 10M/20M
burst-time:      8s/8s
```

**⚠️ Catatan penting — queue ini saat ini idle:**

Semua hotspot profile (`profile-aktif`, `profile-fup`, dll.) memiliki `rate-limit=none`. Bandwidth control sepenuhnya via simple queue dengan packet mark. Profile `profile-aktif` secara **sengaja tidak di-mark** dengan `paket-aktif` di mangle (by design — user aktif bypass per-user PCQ dan share langsung dari `Utama` 50M/200M).

Konsekuensi: `Limit-Dinamis-Per-User-30M` tidak mendapat traffic, burst-nya tidak aktif.

**Jika ingin burst berlaku untuk user aktif**, tambahkan mangle rule:
```
/ip/firewall/mangle/add
  chain=forward
  src-address-list=klient_aktif
  action=mark-packet
  new-packet-mark=paket-aktif
  passthrough=no
  comment="Mark aktif untuk PCQ burst"
```

Jika desain bypass saat ini dipertahankan (aktif = share Utama), burst di queue ini tidak diperlukan dan bisa dibiarkan sebagai cadangan.

---

### 1.5 DoH_Servers Address List

**Masalah:** NAT rule memaksa port 53 ke router, tapi DNS-over-HTTPS berjalan di port 443 (HTTPS) sehingga bypass redirect DNS. User bisa pakai resolver publik (Google, Cloudflare, dll.) tanpa terdeteksi.

**Perbaikan — tambah address-list `DoH_Servers`:**

| IP | Keterangan |
|----|------------|
| 8.8.8.8 | Google DNS/DoH |
| 8.8.4.4 | Google DNS alt/DoH |
| 1.1.1.1 | Cloudflare DNS/DoH |
| 1.0.0.1 | Cloudflare DNS alt/DoH |
| 9.9.9.9 | Quad9 DNS/DoH |
| 149.112.112.112 | Quad9 DNS alt/DoH |
| 208.67.222.222 | OpenDNS/DoH |
| 208.67.220.220 | OpenDNS alt/DoH |

---

### 1.6 Forward Filter Rule: Block DoH TCP/443

**Rule yang ditambahkan:**
```
chain=forward
action=drop
in-interface-list=LIST_LAN
dst-address-list=DoH_Servers
protocol=tcp
dst-port=443
comment="STABIL: Block DNS-over-HTTPS (DoH) ke server publik"
```

Ditempatkan **sebelum** rule `FORWARD: Allow NEW` agar dievaluasi lebih awal.

**Verifikasi pasca deployment:** Rule menunjukkan `bytes=52` — sudah menangkap traffic.

**Tidak berpengaruh ke Cloudflare Tunnel:**
- Rule hanya memblok `forward chain` dari `LIST_LAN` (hotspot client 172.16.2.0/23)
- `cloudflared` berjalan di Pi/VPS terpisah (159.89.192.31), traffic-nya tidak melewati forward chain MikroTik ini
- `cloudflared` connect ke `*.argotunnel.com` / `*.cftunnel.com` — **bukan** ke 1.1.1.1/1.0.0.1

---

## 2. Perbaikan Code (Deployed commit `804f270d`)

### 2.1 Stagger Celery Beat — Cegah `failed:89`

**Masalah:** Celery Beat mendfirkan semua task MikroTik di T=0 saat container start. Empat koneksi MikroTik API simultan (`sync-hotspot-usage`, `sync-unauthorized-hosts`, `cleanup-waiting-dhcp-arp`, `policy-parity-guard`) menyebabkan timeout → `failed:89` di log pada 06:42:27.

**Perbaikan di `extensions.py`:**
```python
# sync-hotspot-usage: T+0 (baseline)
"sync-unauthorized-hosts":    { "options": {"countdown": 20} }  # T+20s
"cleanup-waiting-dhcp-arp":   { "options": {"countdown": 40} }  # T+40s
"policy-parity-guard":        { "options": {"countdown": 55} }  # T+55s
```

Koneksi MikroTik API kini tersebar dalam satu siklus 60-detik, tidak pernah simultan.

---

### 2.2 Task Baru: `purge_stale_quota_keys_task`

**Masalah:** Redis key `quota:last_bytes:mac:<MAC>` bertumbuh tanpa batas (TTL=-1). MAC randomization per-SSID menyebabkan key lama menumpuk untuk perangkat yang sudah tidak aktif.

**Solusi:**
Task harian (03:30) yang:
1. Scan semua `quota:last_bytes:mac:*` di Redis
2. Query `UserDevice.last_seen_at` dari DB, ambil MAC aktif dalam 30 hari
3. Hapus Redis key untuk MAC yang tidak ada di DB dalam 30 hari

**Konfigurasi env:**
```env
QUOTA_STALE_KEY_PURGE_ENABLED=True   # default True
QUOTA_STALE_KEY_STALE_DAYS=30
```

---

### 2.3 Task Baru: `dlq_health_monitor_task`

**Masalah:** Task yang masuk Dead Letter Queue (DLQ) di `celery:dlq` tidak ada notifikasi ke admin — error diam-diam.

**Solusi:**
Task setiap 15 menit yang:
1. Cek panjang `celery:dlq` di Redis
2. Jika non-empty DAN throttle belum aktif → kirim WA ke superadmin dengan preview 3 item terakhir DLQ
3. Set throttle key (default 60 menit) agar tidak spam

**Konfigurasi env:**
```env
TASK_DLQ_ALERT_THROTTLE_MINUTES=60   # 0 = nonaktif
TASK_DLQ_REDIS_KEY=celery:dlq
```

---

### 2.4 Perubahan `.env.prod`

```diff
- QUOTA_SYNC_INTERVAL_SECONDS=300
+ QUOTA_SYNC_INTERVAL_SECONDS=60

+ # Pembersihan Redis key quota MAC tidak aktif (harian, jam 03:30)
+ QUOTA_STALE_KEY_PURGE_ENABLED=True
+ QUOTA_STALE_KEY_STALE_DAYS=30
+
+ # Alert DLQ (menit antar alert, 0=disable)
+ TASK_DLQ_ALERT_THROTTLE_MINUTES=60
```

`QUOTA_SYNC_INTERVAL_SECONDS=60`: sinkronisasi quota tiap 1 menit.
Sebelumnya 5 menit: potensi overage 375 MB di 10 Mbps. Sekarang: max ~75 MB.

---

## 3. Arsitektur Queue Aktual (Referensi)

```
Utama (172.16.0.0/20, max 50M/200M)
├── IoT        (172.16.6.0/24,  PCQ, limit-at 512k/2M,   max 10M/20M)
├── Kamtib     (172.16.8.0/24,  PCQ, limit-at 2M/8M,     max 20M/50M)
├── Privated   (172.16.4.0/24,  PCQ, limit-at 2M/8M,     max 20M/50M)
├── Registrasi (172.16.9.0/24,  PCQ, limit-at 3M/12M,    max 20M/50M)
├── Tamu       (172.16.10.0/24, PCQ, limit-at 1M/5M,     max 10M/30M)
├── Aula       (172.16.11.0/24,      limit-at 2M/6M,     max 20M/30M)
├── Wartelpas  (172.16.12.0/24,      limit-at 2M/15M,    max 20M/100M)
├── Limit-WA-Unauthenticated  (mark: paket-whatsapp, PCQ, max 128k/256k, pri=1)
├── Limit-Dinamis-Per-User-Habis-Expired (mark: paket-habis, PCQ 256k/256k)
├── Limit-Dinamis-Per-User-20M (mark: paket-fup,   PCQ 10M/20M, burst 30M/60M 6s)
└── Limit-Dinamis-Per-User-30M (mark: paket-aktif, PCQ 20M/30M, burst 60M/100M 8s)
                                ↑ idle — profile-aktif tidak di-mark paket-aktif
```

**Flow traffic user hotspot:**
- `profile-aktif` → tidak di-mark → bypass PCQ → share `Utama` langsung
- `profile-fup` → mark `paket-fup` → `Limit-Dinamis-Per-User-20M` (PCQ 10M/20M + burst)
- `profile-habis`/`profile-expired` → mark `paket-habis` → throttle 256k

---

## 4. File yang Diubah

| File | Perubahan |
|------|-----------|
| `backend/app/extensions.py` | Stagger countdown, tambah purge + dlq beat schedule |
| `backend/app/tasks.py` | Tambah `purge_stale_quota_keys_task`, `dlq_health_monitor_task` |
| `.env.prod` | `QUOTA_SYNC_INTERVAL_SECONDS=60`, tambah 3 env baru (tidak di-commit) |
| MikroTik Router (live) | 6 perubahan langsung via API port 8728 |

---

## 5. Hal yang Tidak Dilakukan (Sengaja)

| # | Item | Alasan |
|---|------|--------|
| 9 | Burst PCQ paket-aktif aktif | profile-aktif intentional bypass, tidak di-mark paket-aktif |
| 10 | Hotspot user 6309 | Server wartel, beda aplikasi |
| - | IPv6 anti-tethering | IPv6 belum aktif di VLAN Klien |
| - | VIP address-list refresh | Manual maintenance periodik, tidak ada auto-refresh |
