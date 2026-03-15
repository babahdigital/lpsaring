# Pengembangan: Sinkronisasi Kuota Real-Time & Otomasi Hotspot

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Ringkasan Tujuan
Dokumen ini mendeskripsikan pengembangan logika **kuota real-time** dengan sumber kebenaran di DB, sinkronisasi berkala dari MikroTik, **FUP berbasis ambang sisa kuota (MB)**, notifikasi WhatsApp low-quota berbasis **MB**, notifikasi masa aktif (H-7/H-3/H-1), serta **auto-deactivate** dan **auto-delete** pengguna tidak aktif.

## Keputusan & Best Practice
- **Sumber kebenaran kuota: DB**. MikroTik digunakan sebagai _feeder_ counter; DB menyimpan total dipakai dan histori penggunaan.
- **Interval sinkronisasi**: default 5 menit (300 detik). Cukup cepat untuk real-time tanpa membebani MikroTik.
- **Interval dinamis**: task dijalankan lebih sering, tetapi akan skip jika belum mencapai `QUOTA_SYNC_INTERVAL_SECONDS` (throttle via Redis).
- **Persistensi counter per-MAC**: simpan `last_bytes` per MAC di DB sebagai fallback jika Redis restart, agar delta tetap stabil.
- **Persistensi delta**: aktifkan Redis AOF atau simpan `last_bytes` per MAC di DB agar tidak hilang saat restart/power loss.
- **FUP**: otomatis saat sisa kuota ≤ ambang `QUOTA_FUP_THRESHOLD_MB`.
- **Notifikasi kuota**: hanya sekali per level `QUOTA_NOTIFY_REMAINING_MB` (contoh: `[500]`) untuk menghindari spam.
- **Notifikasi masa aktif**: H-7, H-3, H-1.
- **Komandan non-unlimited** juga menerima notifikasi kuota menipis dan masa aktif.
- **Timezone**: perhitungan expiry dan pesan mengikuti `APP_TIMEZONE` (default `Asia/Makassar`).
- **Statistik harian/mingguan/bulanan** mengikuti `APP_TIMEZONE`.
- **Auto cleanup**: nonaktif 45 hari, hapus permanen 90 hari (nilai bisa disesuaikan di env).
- **Kontrol perangkat**: gunakan IP binding untuk membatasi jumlah perangkat per akun.
- **Policy status**: gunakan address-list untuk active/fup/habis/inactive/expired.
- **Akses portal**: gunakan walled garden hanya untuk halaman login/info.

## Alur Sinkronisasi Kuota
1. Task Celery mengambil daftar user aktif dari DB.
2. Mengambil counter penggunaan dari MikroTik (/ip/hotspot/host) secara batch.
3. Auto-enroll perangkat dari `/ip/hotspot/ip-binding` (comment `user=<id>`) sebelum menghitung pemakaian.
4. Update `total_quota_used_mb` dan `DailyUsageLog` berdasarkan delta.
4. Hitung sisa kuota (MB). (Persen boleh dihitung untuk display/telemetri, tapi bukan threshold.)
5. Tentukan profil MikroTik:
   - Unlimited → `MIKROTIK_UNLIMITED_PROFILE`
   - Expired → `MIKROTIK_EXPIRED_PROFILE`
   - Habis → `MIKROTIK_HABIS_PROFILE`
   - ≤ FUP threshold → `MIKROTIK_FUP_PROFILE`
   - Normal → `MIKROTIK_ACTIVE_PROFILE`
7. Kirim notifikasi WhatsApp sesuai level.

## Auto-Delete & Deactivate
- **Deactive**: jika `last_login_at` lebih lama dari `INACTIVE_DEACTIVATE_DAYS`.
- **Delete**: jika `last_login_at` lebih lama dari `INACTIVE_DELETE_DAYS`.
- Saat deactivate/delete, user juga dihapus dari MikroTik.

## Address-List Status (Active/FUP/Inactive/Expired/Habis)
Sistem menandai status user di MikroTik melalui **address-list** berbasis IP:
- **Active** → list `MIKROTIK_ADDRESS_LIST_ACTIVE`.
- **FUP** → list `MIKROTIK_ADDRESS_LIST_FUP`.
- **Inactive** → dipakai saat user diblokir admin (deactivate manual). Masuk ke list `MIKROTIK_ADDRESS_LIST_INACTIVE`.
- **Expired (waktu)** → masa aktif habis. Masuk ke list `MIKROTIK_ADDRESS_LIST_EXPIRED`.
- **Habis (kuota)** → kuota 0. Masuk ke list `MIKROTIK_ADDRESS_LIST_HABIS`.
- **Blocked (akses)** → dipakai saat user diblokir (mis. admin block atau quota-debt hard block). Masuk ke list `MIKROTIK_ADDRESS_LIST_BLOCKED`.

Catatan:
- Habis hanya untuk kuota, expired hanya untuk waktu.
- Address-list dipakai sebagai tag status di RouterOS (walled-garden/queue/bypass bisa disusun dari list ini).
- Target operasionalnya: **1 IP = 1 status list** (active/fup/habis/expired/inactive/blocked).
- Versi backend terbaru melakukan sync untuk **semua IP kandidat** user (multi-device), tidak hanya 1 IP dari sesi aktif.
- IP yang tidak valid (contoh `0.0.0.0`) diabaikan.
- Address-list dapat dijadikan sumber visual untuk seleksi manual (mis. hapus user lama), sementara logika hapus otomatis tetap mengikuti DB.
 - Jika sesi aktif tidak tersedia, sistem mencoba fallback ke ip-binding milik user atau IP hasil lookup MAC yang sudah authorized.

## Quota-Debt Hard Block (Cap Hutang Kuota)
Latar belakang:
- Dengan kebijakan “kuota habis masih boleh akses banking/pay/WA”, pemakaian bisa terus naik sehingga `used_mb > purchased_mb`.
- Ini memunculkan **hutang kuota** (debt) yang harus dibatasi.

Definisi:
- `debt_mb = max(0, used_mb - purchased_mb)`
- `remaining_mb = max(0, purchased_mb - used_mb)`

Konfigurasi:
- `QUOTA_DEBT_LIMIT_MB` (int, default 0 = nonaktif)

Perilaku saat `debt_mb >= QUOTA_DEBT_LIMIT_MB`:
1) Sistem meng-enforce block MikroTik (idempotent):
   - profile user dipaksa ke `MIKROTIK_BLOCKED_PROFILE`.
   - firewall address-list `MIKROTIK_ADDRESS_LIST_BLOCKED` untuk IP perangkat (jika diketahui).
   - ip-binding tetap non-blocked (`regular`).
2) Sistem menandai DB `is_blocked=True` + `blocked_reason=quota_debt_limit|...` (sekali).
3) Pada transisi block baru di jalur sync-time (`policy.block_transition:sync_usage`), sistem mencoba mengirim WhatsApp khusus ke user dengan template `user_quota_debt_blocked`.
4) Sync berikutnya tidak mengirim duplikat jika user memang sudah berada pada state blocked auto debt yang sama.
5) Notifikasi admin `NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED` tetap berasal dari jalur task/admin terpisah yang memang mendukung fan-out admin.

Pengecualian hard block:
- `is_unlimited_user=True`
- role `KOMANDAN`

Catatan admin:
- “Unblock” **tidak membuat debt jadi 0**. Debt hanya turun jika kuota ditambah (inject/beli) atau used di-reset.
- Endpoint admin menolak unblock jika debt masih >= limit (kecuali unlimited/komandan).
- Untuk 1 kali aksi “Tambah Kuota + Unblock”, sistem harus apply kuota dulu baru unblock.

Catatan operasional MikroTik:
- Address-list berbasis IP dapat meninggalkan entry `blocked` yang stale saat IP berubah.
- Versi backend terbaru melakukan cleanup unblock berbasis token comment `uid=<uuid>`/`user=<08..>` agar stale entry ikut terhapus.
- Duplikat ip-binding (mis. `server=all type=blocked`) adalah penyebab umum user tetap blocked walau sudah dibuka.
  Gateway MikroTik sekarang melakukan dedupe konflik ini.

## IP Binding (Batas Perangkat)
Untuk membatasi jumlah perangkat per akun, gunakan **/ip/hotspot/ip-binding**:
- **Mode campuran (rekomendasi saat ini)**: set `IP_BINDING_TYPE_ALLOWED=regular`, lalu atur status yang dibypass melalui `HOTSPOT_BYPASS_STATUSES` (default `['active','fup','unlimited']`).
- **Mode OTP-only (opsional/legacy)**: set `HOTSPOT_BYPASS_STATUSES` agar mencakup semua status yang ingin dibypass.
- Saat login, backend mencoba mendeteksi MAC berdasarkan IP klien dan akan otomatis membuat ip-binding untuk perangkat baru jika kuota perangkat belum penuh.
- Saat sync kuota, backend akan mencoba auto-enroll device dari ip-binding (comment `user=<id>`) untuk menghindari pemakaian hilang.
- Jika kuota perangkat penuh (mis. max 3), login ditolak dan ip-binding akan ditandai `blocked` untuk MAC baru.
- User dapat **kelola perangkat sendiri** via endpoint berikut:
   - `GET /api/users/me/devices`
   - `POST /api/users/me/devices/bind-current`
   - `DELETE /api/users/me/devices/<device_id>`
   - `PUT /api/users/me/devices/<device_id>/label`

### UI Manajemen Perangkat
- Halaman akun menampilkan kartu **Perangkat Terdaftar** untuk user/komandan.
- Fitur: list perangkat, ikat perangkat saat ini, hapus perangkat, dan edit label.

Catatan perilaku:
- Pembuatan ip-binding saat OTP login memakai `client_ip` (atau IP hasil resolve dari `client_ip`) dan MAC hasil resolve dari IP jika MAC tidak dikirim.
- Jika `client_ip` kosong/tidak valid dan MAC tersedia, backend mencoba resolve IP dari hotspot host/ARP/DHCP berdasarkan MAC.
- Fallback address-list via ip-binding/MAC tetap dipakai saat sinkronisasi status.

Rekomendasi gabungan:
- **IP binding** untuk limit perangkat.
- **Address-list** untuk status policy (active/fup/habis/inactive/expired).
- **Walled garden** hanya untuk akses portal/info (login/expired/habis).

## Kebijakan Permintaan Komandan (QUOTA/UNLIMITED)
- Komandan dapat mengajukan request QUOTA atau UNLIMITED.
- Batas permintaan dibatasi oleh:
   - `KOMANDAN_REQUEST_WINDOW_HOURS` dan `KOMANDAN_REQUEST_MAX_PER_WINDOW`.
   - `KOMANDAN_REQUEST_COOLDOWN_HOURS` untuk jeda antar request.
   - `KOMANDAN_MAX_QUOTA_MB` dan `KOMANDAN_MAX_QUOTA_DAYS` untuk QUOTA.
   - `KOMANDAN_MAX_UNLIMITED_DAYS` untuk UNLIMITED.
- Admin tetap memegang approval, termasuk reject/partial grant.

   ## Rule Expiry Non-Akumulatif + Riwayat Mutasi Kuota

   - Semua jalur yang menambah masa aktif kuota sekarang wajib memakai strategi `reset_from_now`:
      - pembelian paket sukses,
      - inject quota oleh admin,
      - approve / partial approve request quota,
      - grant unlimited dengan durasi.
   - Artinya sisa masa aktif lama **tidak** boleh diakumulasi. Jika user membeli paket 30 hari hari ini, expiry baru dihitung 30 hari dari pembelian hari ini, walaupun masih punya sisa hari aktif sebelumnya.
   - User unlimited yang dibeli lewat paket tetap memakai `duration_days` paket sebagai batas waktu akses, kecuali admin memang sengaja mengosongkan `quota_expiry_date` untuk memberi unlimited time.
   - Riwayat mutasi kuota sekarang tersedia untuk user dan admin, serta bisa diexport PDF. Timeline ini memakai `quota_mutation_ledger` dan memuat kategori utama: `purchase`, `usage`, `debt`, `policy`, `adjustment`, dan `sync`.
   - Backfill pembelian lama dilakukan via command operasional agar transaksi sukses lama tetap muncul di timeline baru tanpa mengubah kontrak runtime pembacaan API.
   - Remediasi operasional baru tersedia lewat CLI:
      - `flask quota-remediation backfill-purchase-history`
      - `flask quota-remediation normalize-unlimited-expiry`
      - `flask quota-remediation audit-hotspot-spikes`

## Konfigurasi ENV Baru
Disediakan di backend/.env.example:
- `MIKROTIK_ACTIVE_PROFILE`
- `MIKROTIK_FUP_PROFILE`
- `MIKROTIK_HABIS_PROFILE`
- `MIKROTIK_UNLIMITED_PROFILE`
- `MIKROTIK_EXPIRED_PROFILE`
- `MIKROTIK_DEFAULT_SERVER_USER`
- `MIKROTIK_DEFAULT_SERVER_KOMANDAN`
- `MIKROTIK_ADDRESS_LIST_ACTIVE`
- `MIKROTIK_ADDRESS_LIST_FUP`
- `MIKROTIK_ADDRESS_LIST_INACTIVE`
- `MIKROTIK_ADDRESS_LIST_EXPIRED`
- `MIKROTIK_ADDRESS_LIST_HABIS`
- `MIKROTIK_ADDRESS_LIST_BLOCKED`
- `IP_BINDING_ENABLED`
- `IP_BINDING_TYPE_ALLOWED`
- `IP_BINDING_TYPE_BLOCKED`
- `HOTSPOT_BYPASS_STATUSES`
- `MAX_DEVICES_PER_USER`
- `REQUIRE_EXPLICIT_DEVICE_AUTH`
- `WALLED_GARDEN_ENABLED`
- `WALLED_GARDEN_ALLOWED_HOSTS`
- `WALLED_GARDEN_ALLOWED_IPS`
- `WALLED_GARDEN_ALLOWED_IP_LIST_NAMES`
- `WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS`
- `WALLED_GARDEN_AUTO_INCLUDE_PORTAL_HOSTS`
- `WALLED_GARDEN_INCLUDE_MIDTRANS_HOSTS`
- `WALLED_GARDEN_INCLUDE_MESSAGING_HOSTS`
- `WALLED_GARDEN_EXTRA_EXTERNAL_URLS`
- `WALLED_GARDEN_MANAGED_COMMENT_PREFIX`
- `WALLED_GARDEN_SYNC_INTERVAL_MINUTES`
- `QUOTA_SYNC_INTERVAL_SECONDS`
- `QUOTA_FUP_THRESHOLD_MB`
- `QUOTA_NOTIFY_REMAINING_MB`
- `QUOTA_EXPIRY_NOTIFY_DAYS`
- `INACTIVE_DEACTIVATE_DAYS`
- `INACTIVE_DELETE_DAYS`
- `AUTO_ENROLL_DEVICES_FROM_IP_BINDING`
- `AUTO_ENROLL_DEBUG_LOG`
- `KOMANDAN_REQUEST_WINDOW_HOURS`
- `KOMANDAN_REQUEST_MAX_PER_WINDOW`
- `KOMANDAN_REQUEST_COOLDOWN_HOURS`
- `KOMANDAN_ALLOW_UNLIMITED_REQUEST`
- `KOMANDAN_MAX_QUOTA_MB`
- `KOMANDAN_MAX_QUOTA_DAYS`
- `KOMANDAN_MAX_UNLIMITED_DAYS`

## Daftar Perubahan File
- backend/config.py
- backend/.env.example
- backend/app/infrastructure/db/models.py
- backend/migrations/versions/20260208_add_quota_notification_levels.py
- backend/migrations/versions/20260209_add_user_devices.py
- backend/app/infrastructure/gateways/mikrotik_client.py
- backend/app/services/hotspot_sync_service.py
- backend/app/services/device_management_service.py
- backend/app/services/walled_garden_service.py
- backend/app/tasks.py
- backend/app/extensions.py
- backend/app/notifications/templates.json
- backend/app/infrastructure/http/auth_routes.py
- backend/app/infrastructure/http/user/profile_routes.py
- frontend/components/akun/DeviceManagerCard.vue
- frontend/pages/akun/index.vue
- docker-compose.yml

## Catatan Implementasi
- Notifikasi disimpan per level: `last_quota_notification_level` dan `last_expiry_notification_level`.
- Sinkronisasi periodik dijalankan oleh Celery Beat.
- Template WhatsApp berada di `backend/app/notifications/templates.json`.
- Template Komandan: `komandan_quota_low`, `komandan_quota_expiry_warning`.

## Langkah Validasi
1. Pastikan Celery Worker & Beat berjalan.
2. Uji perubahan profil saat sisa kuota melewati ambang FUP (MB).
3. Uji notifikasi WA saat sisa kuota melewati ambang low-quota (MB) dan H-7/H-3/H-1.
4. Uji auto-deactivate & delete dengan memanipulasi `last_login_at`.
5. Uji login dari perangkat baru hingga batas `MAX_DEVICES_PER_USER` tercapai.
6. Uji bind perangkat saat ini dan update label perangkat.
7. Uji self-service hapus perangkat dan login kembali dari perangkat baru.
8. Uji walled-garden sync saat `WALLED_GARDEN_ENABLED=True`.
9. Jalankan inventory host eksternal: `python backend/scripts/scan_external_hosts.py` lalu review output `tmp/external_hosts_inventory.json`.
10. Uji pembelian paket saat user masih punya masa aktif dan pastikan expiry baru dihitung dari waktu pembelian terbaru, bukan sisa expiry lama.
11. Uji history kuota user/admin + export PDF untuk memastikan event purchase/usage/debt tampil konsisten.
12. Jalankan dry-run command remediation sebelum apply ke produksi.

## Lampiran Stabil 2026-03: Binding Lifecycle & Cleanup Scope

### A) Transisi `bypassed -> regular/blocked`
- Tipe ip-binding tidak ditentukan oleh 1 env saja. Nilai efektif mengikuti `resolve_allowed_binding_type_for_user(user)`.
- Untuk status non-bypass (`habis`, `expired`, `inactive`) target binding menjadi `regular`.
- Untuk status `blocked`, target bisa `blocked` atau `regular` sesuai rule hard-block policy.

Trigger sinkronisasi binding multi-device:
- `sync_hotspot_usage_task` (periodik, default throttle 300 detik).
- Event transaksi sukses.
- Event inject quota/set unlimited.
- Event block/unblock admin.

### B) Perubahan IP saat status berubah
- Tidak wajib berubah.
- Model saat ini mengutamakan MAC-binding (sering `address=None`), sehingga perubahan status biasanya hanya mengubah `type/comment`.
- Jika DHCP berubah, perubahan IP terjadi karena lease/host update, bukan karena transisi status itu sendiri.

### C) Hapus device vs reset-login
- `DELETE /users/me/devices/<id>` (device-level):
   - Hapus ip-binding MAC + managed address-list IP + row `user_devices`.
   - Tidak menghapus DHCP lease/ARP/host secara eksplisit.
   - Tidak revoke refresh token/session per-device.
- `POST /auth/reset-login` (user-level):
   - Hapus refresh tokens + seluruh user_devices.
   - Jalankan cleanup router lebih lengkap (ip-binding, DHCP lease, ARP, host, managed list).

Rujukan detail operasional:
- `docs/OPERATIONS_HOTSPOT_DEVICE_LIFECYCLE.md`
