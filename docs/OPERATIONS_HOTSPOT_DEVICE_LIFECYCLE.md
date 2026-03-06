# Runbook Operasional - Hotspot Device Lifecycle (Stabil 2026-03)

Dokumen ini menjadi acuan struktur dan flow terbaru untuk login hotspot, binding perangkat, transisi status akses, serta cleanup sesi/perangkat.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Tujuan
- Menetapkan flow stabil terkini agar implementasi fitur berikutnya konsisten.
- Menjawab pertanyaan operasional terkait transisi `bypassed/regular/blocked`.
- Menjelaskan cakupan cleanup saat `delete device`, `logout/reset-login`, dan `delete user`.

## 2) Struktur Kode Kunci

Backend:
- `backend/app/infrastructure/http/auth_contexts/login_handlers.py`
  - Auto-login policy dan validasi identitas perangkat (MAC/IP).
- `backend/app/infrastructure/http/auth_contexts/hotspot_status_handlers.py`
  - Endpoint `/api/auth/hotspot-session-status` untuk keputusan redirect hotspot-required.
- `backend/app/infrastructure/http/user/profile_routes.py`
  - Endpoint `POST /me/devices/bind-current` dan `DELETE /me/devices/<id>`.
- `backend/app/services/device_management_service.py`
  - `apply_device_binding_for_login`, `register_or_update_device`, `revoke_device`, `reset_user_network_on_logout`.
- `backend/app/services/user_management/user_quota.py`
  - Sinkronisasi ip-binding semua device authorized saat inject/unlimited.
- `backend/app/services/transaction_service.py`
  - Sinkronisasi ip-binding semua device authorized pasca transaksi sukses.
- `backend/app/services/hotspot_sync_service.py`
  - Self-heal binding type periodik berdasarkan policy status user.

Frontend:
- `frontend/store/auth.ts`
  - `initializeAuth()`, `authorizeDevice()`.
- `frontend/middleware/auth.global.ts`
  - Redirect ke `/login/hotspot-required` bila hotspot session belum aktif.
- `frontend/pages/login/hotspot-required.vue`
  - One-click activation: probe -> bind-current best-effort -> polling hotspot status.

## 3) Flow Stabil Saat Ini

1. User membuka portal/login.
2. Frontend mencoba `initializeAuth()` + auto-login best-effort jika ada hint identitas.
3. Middleware memanggil `/auth/hotspot-session-status`.
4. Jika hotspot belum aktif, user diarahkan ke `/login/hotspot-required`.
5. Pada `hotspot-required`, frontend:
   - trigger probe ke captive URL,
   - memanggil `/users/me/devices/bind-current?best_effort=true`,
   - polling `/auth/hotspot-session-status` sampai aktif.
6. Backend `apply_device_binding_for_login()` melakukan:
   - register/update device,
   - upsert ip-binding sesuai policy user,
   - cleanup list blocked/unauthorized,
   - cleanup hotspot host untuk device authorized,
   - optional static DHCP lease (jika fitur aktif).

## 4) Matrix Binding Type (Efektif)

Penentuan tipe binding berasal dari `resolve_allowed_binding_type_for_user(user)`:
- `blocked` + hard block policy -> `blocked`
- `blocked` tanpa hard block policy -> `regular`
- status bypass (`active`, `fup`, `unlimited`) -> `bypassed`
- status non-bypass (`habis`, `expired`, `inactive`) -> `regular`

Catatan penting:
- Nilai `IP_BINDING_TYPE_ALLOWED=regular` adalah default global, tetapi hasil akhir tetap mengikuti policy per-user di atas.
- Pada RouterOS, `type` kosong pada ip-binding diperlakukan efektif sebagai `regular`.

## 5) Jika User Punya 3 Device Bypassed Lalu Kuota Habis / Block

### Apakah 3 ip-binding akan berubah?
- Ya, akan disinkronkan ke tipe target policy terbaru.
- Trigger utama:
  - Sync periodik `sync_hotspot_usage_task` (default throttle `QUOTA_SYNC_INTERVAL_SECONDS`, default 300 detik).
  - Event transaksi sukses (`transaction_service`).
  - Event inject quota / set unlimited (`user_quota`).
  - Event admin block/unblock (`user_profile`).

### Apakah IP address ikut berubah?
- Tidak harus.
- Di desain saat ini, ip-binding memakai mode MAC-first (sering `address=None`), jadi perubahan policy biasanya cukup mengubah `type/comment` tanpa perlu perubahan IP.
- Jika DHCP klien berubah, IP bisa berubah secara natural di host/lease, bukan karena transisi status itu sendiri.

## 6) Perilaku Cleanup per Aksi

### A) User hapus 1 device dari dashboard (`DELETE /users/me/devices/<id>`)
Dilakukan:
- Hapus ip-binding untuk MAC device.
- Hapus managed address-list untuk IP device.
- Hapus row `user_devices` untuk device tersebut.

Tidak dilakukan (pada endpoint ini):
- Tidak hapus DHCP lease.
- Tidak hapus ARP entry.
- Tidak hapus hotspot host secara eksplisit.
- Tidak revoke token/session per-device.

### B) User logout / reset-login
Dilakukan cleanup lebih luas:
- Hapus refresh tokens user (all).
- Hapus user_devices user (all).
- Cleanup router: ip-binding, DHCP lease, ARP, hotspot host, managed address-list (best effort).

### C) Admin reset-login user / delete user
Dilakukan cleanup paling lengkap:
- Hapus refresh tokens + user_devices.
- Cleanup artefak router berbasis MAC/IP/comment marker (`uid=` / `user=`).

## 7) Incident Analysis - 082164599907 (Audit 06-03-2026)

Hasil audit runtime:
- DB produksi: tidak ditemukan user untuk nomor ini pada tabel `users`.
- RouterOS: ditemukan 1 ip-binding:
  - `id=*187`
  - `mac=C2:4C:D2:18:3F:81`
  - `type=None` (efektif `regular`)
  - comment: `authorized|user=082164599907|uid=d332b5fb-45f9-4ae0-9a40-0c4e174b7026|...`
- RouterOS host aktif untuk user ini: tidak ditemukan.
- UID pada comment (`d332b5fb-...`) tidak ada lagi di DB.

Kesimpulan:
- Kondisi `regular` yang terlihat adalah **stale orphan ip-binding** (artefak lama), bukan state aktif user DB saat ini.

Rekomendasi penyelesaian:
1. Hapus binding orphan tersebut dari RouterOS.
2. Jalankan audit parity policy + cleanup stale binding secara periodik.
3. Pastikan pipeline delete/reset-login dipakai untuk user removal agar artefak router ikut bersih.

## 8) Checklist Stabilitas Pengembangan Lanjutan

1. Selalu normalisasi nomor telepon ke E.164 saat query operasional.
2. Untuk fitur baru, pisahkan jelas:
   - endpoint soft-cleanup (device-level)
   - endpoint hard-cleanup (user-level/session-level).
3. Jangan mengasumsikan `type=None` sebagai anomaly; treat as `regular` pada audit.
4. Untuk insiden, audit wajib lintas 3 lapisan:
   - DB user/device,
   - RouterOS ip-binding/host,
   - Nginx/backend/celery logs.
5. Jika butuh cleanup jaringan total, gunakan reset-login/user-auth-cleanup, bukan delete-device tunggal.
