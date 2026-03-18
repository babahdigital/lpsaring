# Incident: DHCP Static Lease Self-Heal Loop (28 lease konstan)

**Tanggal ditemukan**: 2026-03-19
**Severity**: Medium (tidak mengganggu koneksi aktif, tapi menyebabkan log noise dan operasi MikroTik berulang)
**Status**: ✅ FIXED (commit belum di-push)

---

## Gejala

Dari log `sync_hotspot_usage_task` dan `cleanup_waiting_dhcp_arp_task`:

```
"dhcp_self_healed": 28    # Setiap siklus sync (~3 menit)
"lease_removed": 28       # Setiap siklus cleanup (5 menit)
```

Persis **28 DHCP static lease yang sama** terus-menerus dibuat, dihapus, lalu dibuat lagi
dalam siklus tanpa henti.

---

## Root Cause

### Step 1: Self-heal membuat static lease untuk device offline
Fungsi `_self_heal_policy_dhcp_for_user` di `hotspot_sync_service.py` berjalan setiap siklus
quota sync. Ia mengecek: **"apakah device terotorisasi ini punya DHCP static lease?"**

Untuk menjawab pertanyaan ini, ia menggunakan snapshot dari `_snapshot_dhcp_ips_by_mac`:

```python
# hotspot_sync_service.py:472-473
status = str(row.get("status") or "").strip().lower()
if status == "waiting":
    continue  # ← BUG: semua waiting lease di-skip!
```

DHCP lease MikroTik berstatus `waiting` ketika device **offline** (bukan connected).
Akibatnya: 28 device yang sedang offline punya lease `waiting` tapi lease tersebut
dieksklusi dari snapshot → self-heal TIDAK TAHU lease sudah ada → **merekrasi lease setiap siklus**.

### Step 2: Cleanup menghapus lease yang justru sudah dibuat self-heal
`cleanup_waiting_dhcp_arp_task` berjalan setiap 5 menit dan mencari lease dengan:
- Status = `waiting`
- Comment mengandung `lpsaring|static-dhcp`
- Last-seen > `AUTO_CLEANUP_WAITING_DHCP_ARP_MIN_LAST_SEEN_SECONDS` (default 6 jam)

28 device offline ini memenuhi semua kriteria → **lease dihapus**.

### Siklus Lengkap
```
T=0m:   sync → self-heal: rekrasi 28 static lease (device offline)
T=0m:   device offline → lease masuk state "waiting"
T=5m:   cleanup_waiting_dhcp_arp: 28 waiting lease → last_seen > 6j → HAPUS
T=5-8m: sync → self-heal: snapshot tidak melihat waiting → rekrasi 28 lagi
T=...   ∞ loop
```

### Dampak Sekunder (sync_unauthorized_hosts_command.py)
Fungsi `_collect_dhcp_lease_snapshot` juga skip semua `waiting` lease:
```python
# sync_unauthorized_hosts_command.py:124-126
if status == "waiting":
    continue  # lpsaring_macs tidak terisi untuk device offline!
```
Akibatnya: 28 device offline juga kehilangan perlindungan dari `klient_unauthorized`
(meski ada ip-binding, MAC tidak masuk `lpsaring_macs` yang merupakan lapisan perlindungan kedua).

---

## Fix

### File 1: `backend/app/services/hotspot_sync_service.py`
Fungsi `_snapshot_dhcp_ips_by_mac` — include waiting lpsaring lease dalam snapshot:

```python
# SEBELUM:
if status == "waiting":
    continue

# SESUDAH:
if status == "waiting":
    comment = str(row.get("comment") or "").lower()
    if "lpsaring|static-dhcp" not in comment:
        continue
    # Fall-through: include lpsaring waiting lease dalam by_mac
```

**Efek**: Self-heal melihat lease "waiting" yang sudah ada → skip rekrasi → loop berhenti.

### File 2: `backend/app/commands/sync_unauthorized_hosts_command.py`
Fungsi `_collect_dhcp_lease_snapshot` — include waiting lpsaring MAC dalam `lpsaring_macs`:

```python
# SEBELUM:
if status == "waiting":
    continue

# SESUDAH:
if status == "waiting":
    if mac and "lpsaring|static-dhcp" in comment:
        lpsaring_macs.add(mac)  # Tetap dilindungi dari unauthorized
    continue
```

**Efek**: Device offline tetap terlindungi dari `klient_unauthorized` list.

---

## Verifikasi Post-Fix

Setelah deploy, cek di log `sync_hotspot_usage_task`:
```
# Yang diharapkan setelah fix:
"dhcp_self_healed": 0   (atau mendekati 0)

# Log cleanup_waiting_dhcp_arp juga harus berkurang:
"lease_removed": 0   (atau sangat kecil)
```

Jika masih ada self-heal kecil (1-3), itu normal — device yang baru online dan belum punya IP.

---

## Catatan Desain

`cleanup_waiting_dhcp_arp_task` **tetap diperlukan** untuk membersihkan stale lease dari:
- Device yang sudah dideauthorize dari DB tapi leasenya masih ada di MikroTik
- MAC randomization — MAC lama yang tidak lagi dipakai

Setelah fix, task cleanup masih akan menghapus lease-lease tersebut karena:
- Non-lpsaring waiting lease → tetap dihapus (tidak masuk snapshot)
- Lpsaring waiting lease dari device yang dideautorize → setelah dihapus dari `UserDevice`,
  `_self_heal_policy_dhcp_for_user` tidak akan merekrasi (device tidak ada di `user.devices`)

---

## Environment Variables Relevan

```env
AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED=True
AUTO_CLEANUP_WAITING_DHCP_ARP_COMMENT_KEYWORD=lpsaring|static-dhcp
AUTO_CLEANUP_WAITING_DHCP_ARP_MIN_LAST_SEEN_SECONDS=21600  # 6 jam
AUTO_CLEANUP_WAITING_DHCP_ARP_INTERVAL_SECONDS=300         # 5 menit
```
