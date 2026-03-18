# Incident: Banking Deadlock — User Inactive Tidak Bisa Akses Mobile Banking

**Tanggal ditemukan**: 2026-03-19 (Audit Total Holistik)
**Severity**: High (bisnis — user tidak bisa bayar tagihan online)
**Status**: ⚙️ FIX DIIMPLEMENTASI — perlu deploy + konfigurasi

---

## Deskripsi Masalah

User dengan status `expired` atau `inactive` (kuota habis, masa aktif lewat) **tidak bisa
mengakses situs mobile banking** (BCA, BRI, Mandiri, BNI, dll) untuk membayar tagihan
perpanjangan layanan.

Ini menciptakan **deadlock**:
> "Akun habis → perlu bayar → tidak bisa buka internet banking → tidak bisa bayar → akun tetap habis"

---

## Analisis Root Cause

### Arsitektur Firewall MikroTik (dari audit langsung, 2026-03-18)

User `klient_inactive` (expired/inactive) memiliki 2 firewall rule:
```
1. chain=forward action=accept src-list=klient_inactive dst-list=Bypass_Server
2. chain=forward action=drop   src-list=klient_inactive dst-list=LOCAL_NETWORKS
```

**Rule 1 memperbolehkan** akses ke `Bypass_Server` — ini sudah benar secara desain.

### Masalah: Bypass_Server Tidak Ada Banking IPs

Saat audit, `Bypass_Server` address-list di MikroTik hanya berisi **9 entries**:
- Portal LPSaring (`lpsaring.babahdigital.net`)
- Nilai-nilai portal internal
- Server wartelpas

**Banking sites (BCA, BRI, Mandiri, BNI, dll) TIDAK ADA** di `Bypass_Server`.

### Walled Garden Tidak Cukup untuk klient_inactive

`WALLED_GARDEN_EXTRA_EXTERNAL_URLS` memang sudah mencakup banking domains:
```env
WALLED_GARDEN_EXTRA_EXTERNAL_URLS=[..., "*bca.co.id", "*bri.co.id", ...]
```

Tapi walled garden hanya berlaku untuk user yang **belum login** (captive portal).
User `klient_inactive` sudah melewati captive portal tapi aksesnya di-restrict oleh
firewall rule #2 (drop ke LOCAL_NETWORKS selain Bypass_Server).

---

## Fix Implementasi

### Task 7.3: `sync_access_banking_task`

Task Celery baru yang berjalan harian jam 02:00 untuk populate `Bypass_Server`
dengan banking domain IPs secara otomatis.

**File yang diubah**:
- `backend/app/tasks.py` — tambah task `sync_access_banking_task`
- `backend/app/extensions.py` — tambah beat schedule `sync-access-banking`

**Mekanisme**:
1. Load domain list dari settings DB (`AKSES_BANKING_DOMAINS`)
2. Resolve IP via DNS untuk setiap domain
3. Diff dengan entri `Bypass_Server` yang ber-comment `source=banking-sync`
4. Upsert IP baru, hapus entri stale (hanya yang dikelola task ini)
5. Entri manual tidak tersentuh

**Default domain yang di-resolve** (configurable via settings DB):
- klikbca.com, bca.co.id
- bri.co.id
- bankmandiri.co.id
- bni.co.id
- cimbniaga.co.id, permatabank.co.id, ocbcnisp.com
- danamon.co.id, btn.co.id

---

## Workaround Darurat (Sebelum Deploy Fix)

Tambahkan banking IPs secara manual ke MikroTik sampai fix di-deploy:

```
/ip firewall address-list
add list=Bypass_Server address=103.15.217.0/24 comment="emergency-banking-bca"
add list=Bypass_Server address=202.93.44.0/22  comment="emergency-banking-bri"
add list=Bypass_Server address=202.155.4.0/22  comment="emergency-banking-mandiri"
add list=Bypass_Server address=202.155.204.0/23 comment="emergency-banking-bni"
```

**CATATAN**: IP banking bisa berubah sewaktu-waktu (CDN dinamis). Task otomatis lebih andal.

---

## Konfigurasi Settings DB (Post-Deploy)

Tambahkan di admin settings panel setelah deploy:

| Key | Value Default | Keterangan |
|-----|---------------|------------|
| `AKSES_BANKING_ENABLED` | `True` | On/off fitur ini |
| `AKSES_BANKING_DOMAINS` | `klikbca.com,bri.co.id,...` | CSV domain banking |
| `AKSES_BANKING_LIST_NAME` | `Bypass_Server` | Target address-list MikroTik |

Atau via env (untuk cron schedule):
```env
AKSES_BANKING_CRON_HOUR=2
AKSES_BANKING_CRON_MINUTE=0
```

---

## Verifikasi Post-Deploy

1. Jalankan manual trigger (dari flask shell atau UI task):
   ```python
   from app.tasks import sync_access_banking_task
   sync_access_banking_task.delay()
   ```

2. Cek log:
   ```
   Celery Task: Banking bypass sync selesai. {"added": N, "updated": M, "removed_stale": 0, "errors": 0}
   ```

3. Verifikasi di MikroTik:
   ```
   /ip firewall address-list print where list=Bypass_Server
   # Harus muncul entri dengan comment "AUTO-BANKING-BYPASS|source=banking-sync|..."
   ```

4. Test: Login ke portal dengan user expired → coba buka `klikbca.com` → harus bisa akses.

---

## Referensi

- Devlog analisis: `docs/devlogs/2026-03-18-holistic-audit-penyempurnaan.md` section 7.3 dan 14
- Firewall rule audit: ibid section 11 (6.5 klient_inactive firewall — AUDITED OK)
- Task implementation: `backend/app/tasks.py::sync_access_banking_task`
