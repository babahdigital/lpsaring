# Runbook Operasional — MikroTik Sync & Status Akses

Dokumen ini merangkum cara kerja sinkronisasi akses MikroTik (ip-binding, address-list, profile), alur unblock/inject, serta langkah recovery untuk kasus “nyangkut”.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Konsep Inti (Source of Truth)
- **DB adalah sumber kebenaran** untuk kuota (`total_quota_purchased_mb`, `total_quota_used_mb`) dan masa aktif (`quota_expiry_date`) + flag akses (`is_unlimited_user`, `is_blocked`).
- MikroTik dipakai untuk:
  - counter pemakaian (utama: `/ip/hotspot/host`),
  - enforcement session/profile,
  - policy per-IP lewat **firewall address-list**.

## 2) Dua Mekanisme Router yang Sering Tertukar
### A) `/ip/hotspot/ip-binding` (berbasis MAC)
Dipakai untuk **enforcement berbasis perangkat**.
- Di proyek ini, ip-binding dibuat **MAC-only** (tidak mengunci IP) agar stabil saat DHCP/roaming.
- Tipe yang dipakai (contoh): `regular`, `blocked`, `bypassed`.

### B) `/ip/firewall/address-list` (berbasis IP)
Dipakai untuk **status akses**:
- `MIKROTIK_ADDRESS_LIST_ACTIVE` (default: `klient_aktif`)
- `MIKROTIK_ADDRESS_LIST_FUP`
- `MIKROTIK_ADDRESS_LIST_HABIS`
- `MIKROTIK_ADDRESS_LIST_EXPIRED`
- `MIKROTIK_ADDRESS_LIST_INACTIVE`
- `MIKROTIK_ADDRESS_LIST_BLOCKED` (default: `klient_blocked`)

Catatan penting:
- Address-list itu **berbasis IP**, jadi IP yang berubah dapat meninggalkan entry “stale” (nyangkut) jika tidak dibersihkan.
- Untuk list status (active/fup/habis/expired/inactive/blocked), targetnya adalah **1 IP = 1 status list**.

### Multi-device / multi-IP
Versi terbaru backend melakukan sync address-list untuk **semua IP kandidat** milik user (bukan hanya 1 IP hasil lookup session).

Sumber kandidat IP yang dipakai:
- DB `user.devices.ip_address` (jika tersedia)
- `/ip/hotspot/host` (MAC → address)
- `/ip/hotspot/ip-binding` (MAC → address, jika ada)

IP yang tidak valid (contoh `0.0.0.0`) diabaikan.

## 2.1) Fitur Opsional: DHCP Static Lease (Stabilkan IP)

Jika firewall sangat bergantung pada address-list (IP-based) dan klien sering roaming/renew DHCP, IP bisa sering berubah dan memicu **stale address-list**.

- Aktifkan: `MIKROTIK_DHCP_STATIC_LEASE_ENABLED=True`
- WAJIB set: `MIKROTIK_DHCP_LEASE_SERVER_NAME=Klien` (sesuaikan dengan nama DHCP server hotspot utama).
  - Setting ini dibaca via `settings_service.get_setting()` (prioritas DB `application_settings`, fallback ke ENV bila DB kosong).
  - Tanpa pin server ini, RouterOS bisa punya lease untuk MAC yang sama di **beberapa DHCP server** (mis. `Kamtib/AOP/Wartelpas/Privated`), dan entry lease “managed” bisa nyasar.
- Perilaku saat login (device authorized): backend akan upsert DHCP lease menjadi static (MAC -> IP) dengan comment `lpsaring|static-dhcp|user=08...|uid=...`.

### Kenapa bisa “nyasar” ke DHCP server lain (contoh: Kamtib)
Jika `MIKROTIK_DHCP_LEASE_SERVER_NAME` dulu kosong atau salah, MikroTik bisa mengembalikan lease list untuk sebuah MAC tanpa jaminan urutan server. Versi lama sempat berpotensi meng-update lease “pertama” (`leases[0]`) walau itu bukan server hotspot yang dimaksud, sehingga comment `lpsaring|static-dhcp` ikut tertulis di server lain.

### Perbaikan (anti-terulang)
Versi backend terbaru menerapkan guard:
- Untuk comment managed `lpsaring|static-dhcp`, server pin **wajib** (kalau kosong, operasi lease dibatalkan).
- Jika server pin diset (mis. `Klien`), backend **tidak akan** mengupdate lease pada server lain; bila belum ada lease di server tersebut, backend akan membuat lease baru untuk server yang dipin.
- Best-effort cleanup: jika ditemukan lease managed `lpsaring|static-dhcp` untuk MAC yang sama di server lain, backend akan mencoba menghapusnya.

### Sync Semua User (Sekali Jalan)

Untuk migrasi/sinkronisasi awal (device yang sudah ada di DB):

- `flask sync-dhcp-leases --only-authorized`
- `flask sync-dhcp-leases --limit 200`

Catatan: device yang sedang tidak terlihat di MikroTik (tidak ada IP saat sync) akan di-skip.

Catatan penting:
- Jika `MIKROTIK_DHCP_STATIC_LEASE_ENABLED=True` tapi `MIKROTIK_DHCP_LEASE_SERVER_NAME` kosong, perintah ini akan abort (sengaja) agar tidak menulis lease ke server yang salah.

## 2.2) Fitur Opsional: Auto-Replace Device Saat MAC Berubah

Masalah umum: HP memakai **Private MAC** atau user ganti perangkat sehingga MAC baru tercatat sebagai device baru. Jika `MAX_DEVICES_PER_USER=3` sudah penuh, user bisa mentok.

- Aktifkan: `DEVICE_AUTO_REPLACE_ENABLED=True`
- Perilaku: saat ada binding dalam konteks **terautentikasi** (OTP sukses atau endpoint token-required seperti `/api/users/me/devices/bind-current`), jika device sudah mencapai limit, backend akan **menghapus 1 device lama** dan menggantinya dengan device baru.
  - Prioritas yang dihapus: device **belum authorized** dulu, lalu yang **paling lama** (last_seen).
  - Cleanup router: remove ip-binding, bersihkan semua address-list terkelola untuk IP lama, dan (jika DHCP static enabled) remove DHCP lease untuk MAC lama.

## 3) Cara Sistem Menentukan Status
### A) Remaining vs Debt
- Remaining kuota:
  - `remaining_mb = max(0, purchased_mb - used_mb)`
- Hutang kuota (debt):
  - `debt_mb = max(0, used_mb - purchased_mb)`

**Unblock tidak otomatis membuat debt=0.** Debt=0 hanya terjadi jika:
- `used_mb` di-reset, atau
- `purchased_mb` ditambah sampai `purchased_mb >= used_mb`.

### B) Profile target (MikroTik)
Sinkronisasi periodik akan memilih profile:
- unlimited → `MIKROTIK_UNLIMITED_PROFILE`
- expired → `MIKROTIK_EXPIRED_PROFILE`
- habis (remaining=0) → `MIKROTIK_HABIS_PROFILE`
- fup (percent <= threshold) → `MIKROTIK_FUP_PROFILE`
- normal → `MIKROTIK_ACTIVE_PROFILE`

### C) Address-list target (MikroTik)
Sinkronisasi akan menempatkan IP user ke salah satu list: active / fup / habis / expired / inactive.

## 4) Quota-Debt Hard Block (Cap Hutang)
Jika `QUOTA_DEBT_LIMIT_MB > 0` dan `debt_mb >= limit` maka sistem:
- menandai DB `is_blocked=True` (sekali),
- meng-enforce MikroTik:
  - profile user ke `MIKROTIK_BLOCKED_PROFILE`,
  - firewall address-list `klient_blocked` untuk IP device (jika diketahui),
  - ip-binding tetap non-blocked (`regular`),
- mengirim WhatsApp ke user + admin recipients yang subscribe tipe notifikasi `QUOTA_DEBT_LIMIT_EXCEEDED`.

Pengecualian:
- `is_unlimited_user=True`
- role `KOMANDAN`

## 5) Admin: Edit User — Urutan yang Benar
Perilaku yang disepakati:
- Jika satu request mengandung `add_gb/add_days` dan `unblock`, maka sistem harus:
  1) apply **inject quota** / toggle unlimited,
  2) baru melakukan **unblock**.

Ini mencegah kasus:
- unblock dicek dulu → guard debt-limit gagal → request rollback → kuota yang diisi tidak tersimpan.

## 6) Kasus Umum “Nyangkut” dan Recovery
### A) Winbox: user masih blocked padahal DB sudah dibuka
Penyebab paling umum:
- ada **duplikat** ip-binding untuk MAC yang sama (mis. `server=all type=blocked` meng-override `server=srv-user type=bypassed`).

Recovery:
- Pastikan hanya ada 1 ip-binding untuk MAC (hapus duplikat/konflik).
- Versi backend terbaru sudah otomatis dedupe konflik `server=all` saat melakukan upsert.

### B) Address-list `klient_blocked` masih ada walau unblock sudah sukses
Penyebab paling umum:
- entry “stale” karena IP berubah.

Recovery:
- Hapus entry `klient_blocked` yang comment-nya mengandung `uid=<uuid>` atau `user=<08..>`.
- Versi backend terbaru akan melakukan cleanup ini otomatis saat unblock.

### C) Paksa sync untuk 1 IP tertentu
Gunakan CLI:
- `sync-mikrotik-access` (lihat docs/WORKLOG_2026-02-16.md untuk konteks).

### D) Audit: ada IP yang masuk >1 status list
Tujuan audit ini memastikan tidak ada IP yang berada di beberapa list status sekaligus.

Cara cepat (dari server Pi, via container backend):
- Jalankan `python` untuk menginspeksi `/ip/firewall/address-list` dan menghitung IP yang muncul di lebih dari 1 list status.

Jika ditemukan kasus invalid seperti `0.0.0.0`, hapus entry tersebut dari semua list status.

### E) Audit parity holistik (status/ip-binding/unauthorized/DHCP)
Gunakan command resmi berikut untuk menghasilkan JSON audit terbaru:

- `flask audit-hotspot-parity`
- `flask audit-hotspot-parity --output /tmp/lpsaring_addrlist_binding_parity_dryrun.json`
- `flask audit-hotspot-parity --fail-on-drift`

Dokumentasi detail command ini tersedia di:
- `docs/OPERATIONS_HOTSPOT_PARITY_AUDIT.md`

Indikator utama yang harus `0`:

- `policy_focus.critical_without_binding_total`
  - memastikan status `active/fup/habis/blocked` tidak punya row tanpa binding.
- `policy_focus.unauthorized_must_not_duplicate_status_count`
  - memastikan IP `unauthorized` tidak overlap dengan list status.
- `unlimited_alignment.scoped_unlimited_users_with_authorized_device.without_binding`
  - memastikan user unlimited yang sudah punya device authorized tetap punya binding valid.
- `dhcp_alignment.authorized_without_dhcp_lease`
  - memantau MAC authorized yang belum punya DHCP lease.
- `dhcp_alignment.binding_dhcp_ip_mismatch`
  - memantau mismatch IP antara DHCP lease dan ip-binding.

## 7) Healthcheck Produksi
Untuk arsitektur DO split-stack (`nginx` global terpisah), cek dari container nginx global:
- `docker exec global-nginx-proxy wget -T 10 -qO- --header='Host: lpsaring.babahdigital.net' http://127.0.0.1/api/ping`

Untuk deployment lama yang masih membawa service `nginx` di app compose, gunakan metode internal compose seperti sebelumnya.

## 8) Referensi File Kode
- Status/profile sinkronisasi: `backend/app/services/hotspot_sync_service.py`
- Admin unblock cleanup: `backend/app/services/user_management/user_profile.py`
- Inject quota + set unlimited: `backend/app/services/user_management/user_quota.py`
- MikroTik gateway (ip-binding/address-list): `backend/app/infrastructure/gateways/mikrotik_client.py`

## 9) Kebijakan Demo Payment-Only (Hardening Terbaru)

- User demo **tidak ikut** sinkronisasi MikroTik:
  - dikecualikan pada sync periodik hotspot usage/profile,
  - dikecualikan pada sync single-user.
- Tujuan: mode demo hanya memvalidasi flow auth/pembayaran tanpa memodifikasi state akses router.

Implikasi operasional:
- Jangan gunakan akun demo untuk validasi perubahan profile/address-list MikroTik.
- Untuk uji enforcement akses router, gunakan akun non-demo yang disiapkan khusus uji operasional.

## 10) Login Sukses: Cleanup Address-list `blocked` + `unauthorized`

Saat user berhasil login/otorisasi perangkat:
- backend melakukan best-effort cleanup list `blocked` dan `unauthorized` untuk IP terkait user,
- ini mencegah kasus user tetap tertahan di list `unauthorized` walau otorisasi sudah valid.
- cleanup hotspot host hanya dijalankan pada jalur recovery unauthorized yang valid (bukan pembersihan periodik broad).

Jika masih ada residual entry, lakukan audit cepat berdasarkan marker comment (`uid=...` / `user=08...`) lalu hapus entry stale.

## 10.1) Guard Policy 2026-03-08 (No Broad Host Cleanup on Unauthorized Sync)

Perubahan policy:
- Scheduler `sync-unauthorized-hosts` tidak lagi menghapus trusted hotspot host secara periodik.
- Cleanup hotspot host difokuskan ke recovery unauthorized saat login sukses user terkait.

Tujuan:
- mencegah reset host trusted sebagai efek samping sinkronisasi unauthorized.

Indikator log worker yang diharapkan:
- `hotspot_host_cleanup_removed=0` pada siklus sinkronisasi normal.

## 10.2) Jika Host Tetap Reset Massal

Jika gejala tetap muncul walau policy aplikasi sudah aktif, audit jalur eksternal RouterOS:

```routeros
/system/scheduler print detail where on-event~"hotspot host remove"
/system/script print detail where source~"hotspot host remove"
```

Temuan command global seperti `/ip hotspot host remove [find server="wartel"]` pada scheduler/script periodik harus dianggap root cause eksternal dan diperbaiki langsung di RouterOS admin.

## 10.3) Recovery Darurat: User Hotspot MikroTik Hilang

Gunakan prosedur ini jika entry `/ip/hotspot/user` hilang/berkurang, sementara data user di DB masih ada.

Prinsip:
- DB tetap source of truth.
- Recovery dilakukan bertahap dan **scope ketat** (default: hanya `srv-user`).
- Hindari perubahan policy/profile lintas server saat emergency recovery.

Langkah operasional minimum:
1. Verifikasi koneksi SSH dan path deploy produksi.
2. Hitung target user dari DB (`USER`, `APPROVED`, `is_active=true`, `mikrotik_server_name='srv-user'`).
3. Rekonstruksi user hotspot dari DB ke MikroTik (create/update), gunakan password existing jika valid, generate hanya bila kosong/tidak valid.
4. Verifikasi jumlah user router pasca recovery dan bandingkan dengan target DB.

Catatan implementasi:
- Saat recovery darurat, utamakan `server='srv-user'` pada operasi `activate_or_update_hotspot_user`.
- Jangan menjalankan cleanup global yang bisa menghapus state router lain sampai recovery tervalidasi.
- Jika ada perintah bulk quota/profile, jalankan hanya setelah jumlah user hotspot kembali normal.

## 11) Policy Parity Mismatch Response

Jika dashboard admin menampilkan mismatch policy parity (App vs MikroTik), ikuti SOP khusus:
- `docs/OPERATIONS_POLICY_PARITY_RESPONSE.md`

## 12) Layered Gate Policy (OTP + MikroTik)

Untuk keputusan autentikasi identitas vs akses jaringan hotspot, gunakan policy matrix terbaru:
- `docs/LAYERED_GATE_POLICY_MATRIX.md`

Analisa historis lengkap (termasuk error/log, hardening unauthorized, dan hasil verifikasi) tersedia di:
- `docs/DEVLOG_2026-03-02.md`

## 13) Audit Nomor `082164599907` (06-03-2026)

### Ringkasan temuan
- DB produksi tidak menemukan user aktif untuk nomor ini.
- RouterOS masih menyimpan 1 ip-binding orphan:
  - `id=*187`
  - `mac=C2:4C:D2:18:3F:81`
  - `type=None` (efektif `regular`)
  - comment mengandung `user=082164599907` dan `uid=d332b5fb-45f9-4ae0-9a40-0c4e174b7026`
- UID pada comment tersebut tidak ada lagi di DB produksi.
- Tidak ada hotspot host aktif untuk user ini.

### Interpretasi
- Status `regular` pada kasus ini bukan state user aktif, melainkan artefak stale/orphan di router.
- Ini bisa muncul jika user/device di DB sudah terhapus tetapi cleanup router tidak tuntas di masa lalu.

### Tindak lanjut operasional
1. Hapus binding orphan berdasarkan id/MAC/comment marker.
2. Jalankan audit parity untuk mendeteksi orphan comment marker `uid=` yang tidak punya pasangan di DB.
3. Gunakan endpoint/flow cleanup user-level (`reset-login` atau admin auth cleanup) saat deprovisioning agar artefak router ikut bersih.

### Catatan kebijakan penting
- Nilai `type` kosong pada RouterOS (`None`) diperlakukan setara `regular` pada audit policy.
