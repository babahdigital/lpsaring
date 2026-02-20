# Referensi Pengembangan

Dokumen ini merangkum **perubahan yang sudah diterapkan** dan **struktur aplikasi** sebagai referensi pengembangan lanjutan.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Ringkasan Perubahan (Sync + Penyelarasan UI)

### A. Sinkronisasi ke starter-kit (tetap pada versi starter-kit)
- Konsistensi enum dan import diselaraskan ke `@core` dan `@layouts`.
- Penyesuaian plugin Vuetify (ikon, tema, defaults) agar sesuai struktur starter-kit.
- Penyesuaian lint/typecheck dan perbaikan error tipe.
- Perapihan utilitas dan composable agar mengikuti pola starter-kit.

### B. Penyelarasan UI ke versi lama (referensi lpsaring-bak)
- **Header**: hanya `HeaderWeeklyRevenue` (admin) + `UserProfile`.
- **UserProfile**: avatar tanpa gambar, menggunakan inisial; dropdown disesuaikan gaya lama.
- **Footer**: teks disesuaikan dan layout dibuat responsif.

### C. Pengecualian (dibiarkan)
- `frontend/@layouts/styles/_placeholders.scss` dibiarkan mengikuti kondisi saat ini (untuk menjaga kompatibilitas dan menghindari warning Sass yang pernah muncul).

---

## 2) Daftar Perubahan (Kelompok Besar)

### Core & Utilities
- Penyelarasan komponen AppBar, Notifications, TablePagination, Shortcuts, dan lainnya.
- Perbaikan composable cookie dan penambahan shim i18n lokal.
- Perapihan chart configs (Apex & Chart.js) agar tidak tergantung `ThemeInstance`.

### Layout & Navigasi
- Penyesuaian Horizontal/Vertical Nav untuk icon props dan link resolver.
- Update layout default/blank untuk loading indicator dan suspense.
- Penyesuaian konfigurasi layout dan store `@layouts`.

### Plugins & Theming
- Penyelarasan plugin iconify, vuetify defaults, dan theming.
- Penyusunan ulang alias icons yang berbasis class (tabler).

### Dialogs & Komponen UI
- Banyak dialog menggunakan `$vuetify.display` agar responsif dan konsisten.

---

## 3) Struktur Aplikasi

Struktur ringkas direktori utama:

```
.
├─ backend/                # Layanan backend (Flask) + worker Celery
├─ frontend/               # Aplikasi Nuxt 3 + Vuetify
├─ docs/                   # Dokumentasi proyek
├─ infrastructure/         # Konfigurasi infra/opsional
├─ docker-compose.yml      # Docker compose utama (dev)
├─ docker-compose.prod.yml # Docker compose prod
└─ README.md
```

### Struktur Frontend

```
frontend/
├─ @core/                  # Komponen inti, store, utilitas, composable
│  ├─ components/
│  ├─ composable/
│  ├─ enums.ts
│  ├─ initCore.ts
│  ├─ libs/                # Config chart libraries
│  ├─ scss/
│  ├─ stores/
│  └─ utils/
├─ @layouts/               # Sistem layout dan navigasi
│  ├─ components/
│  ├─ enums.ts
│  ├─ plugins/
│  ├─ stores/
│  ├─ styles/
│  └─ types.ts
├─ components/             # Komponen halaman & dialog
├─ composables/            # Composable khusus app
├─ layouts/                # Layout Nuxt
├─ navigation/             # Definisi menu
├─ plugins/                # Plugin Nuxt/Vuetify/Iconify
├─ store/                  # Pinia stores
├─ types/                  # Type declarations
├─ utils/                  # Utilitas umum
├─ app.vue                 # Entry Vue
├─ nuxt.config.ts
└─ package.json
```

---

## 4) Catatan Pengembangan

1. **Tetap gunakan versi starter-kit** untuk paket inti (Nuxt/Vuetify/Pinia dan dependensi utama).
2. **Header dan Footer** mengikuti gaya versi lama (lpsaring-bak).
3. **I18n** saat ini memakai shim lokal di `frontend/composables/useI18n.ts`.
4. **Perubahan lint/typecheck** sudah diselaraskan (ESLint + Nuxt typecheck).

---

## 5) Perubahan Hotspot Auth & Captive Flow (Feb 2026)

Ringkasan perubahan yang berkaitan dengan autentikasi hotspot, captive portal, dan auto-login dashboard:

1. **One-time session token untuk dashboard**
  - Login OTP menghasilkan `session_token` dan `session_url`.
  - Frontend menyediakan halaman `/session/consume` untuk menukar token menjadi JWT.

2. **Auto-login dashboard dari `/login`**
  - `initializeAuth()` mencoba `/auth/auto-login` jika tidak ada token.
  - Jika query `ip`/`mac` tersedia (redirect dari MikroTik), maka `client_ip`/`client_mac` ikut dikirim.

3. **Captive flow tetap di halaman terhubung**
  - `dst` dipaksa ke `/captive/terhubung`.
  - Halaman terhubung punya auto-close singkat.

4. **Mode regular (utama saat ini)**
  - `IP_BINDING_TYPE_ALLOWED=regular`, sehingga `hotspot_login_required=true`.
  - Captive mengirim `hotspot_login_context=true` agar backend tetap mengirim kredensial hotspot saat OTP sukses.

5. **Bypass hotspot login (opsional)**
  - `IP_BINDING_TYPE_ALLOWED=bypassed`, sehingga `hotspot_login_required=false`.
  - Tidak mengirim username/password hotspot ke frontend.

6. **Normalisasi MAC & resolusi MAC yang lebih robust**
  - Decode URL-encoded MAC dan samakan separator.
  - Resolusi MAC lewat hotspot host/active/ARP/DHCP.

7. **Perbaikan deteksi IP (ProxyFix + X-Forwarded-For)**
  - `get_client_ip()` sekarang bisa memakai X-Forwarded-For jika proxy dipercaya.

### File yang terpengaruh (ringkas)
- Backend: `backend/app/infrastructure/http/auth_routes.py`, `backend/app/services/device_management_service.py`, `backend/app/utils/request_utils.py`
- Frontend: `frontend/store/auth.ts`, `frontend/pages/captive/*`, `frontend/pages/login/index.vue`, `frontend/pages/session/consume.vue`

---

## 6) Catatan Produksi: IP Asli Klien (Auto-Login)

**Masalah inti:** Auto-login bergantung pada IP/MAC klien. Jika backend hanya melihat IP gateway Docker (contoh: 172.18.0.1), maka auto-login akan 401.

### Opsi Produksi yang Disarankan
1. **Akses lewat redirect MikroTik (paling aman)**
  - Pastikan login page MikroTik menyertakan parameter `ip` dan `mac`.
  - Frontend akan mengirim `client_ip`/`client_mac` ke `/auth/auto-login`.

2. **Proxy membaca IP asli**
  - Jalankan reverse proxy di host (bukan bridge Docker) sehingga `remote_addr` = IP asli.
  - Gunakan `X-Forwarded-For` dan `ProxyFix` di Flask.

3. **Host-network Nginx (Linux saja)**
  - Jalankan reverse proxy (Nginx) di host agar `remote_addr` bisa menjadi IP asli.
  - **Tidak didukung di Docker Desktop Windows/macOS** jika ingin memakai host networking.

### Rekomendasi

---

## 7) Usulan: Notifikasi Multi-Channel (WhatsApp + Telegram)

Dokumen detail usulan Telegram:
- [docs/TELEGRAM_NOTIFICATIONS_PROPOSAL.md](TELEGRAM_NOTIFICATIONS_PROPOSAL.md)

Saat ini notifikasi sudah punya **sistem template** yang generik:
- Template tersimpan di `backend/app/notifications/templates.json`
- Rendering lewat `backend/app/services/notification_service.py:get_notification_message(template_key, context)`

Artinya, menambah channel Telegram bisa **reuse template yang sama** (tanpa bikin template baru per-channel), lalu hanya mengganti “transport”-nya.

### 7.1 Prinsip Desain
- Template tetap 1 sumber (format string + spintax).
- Channel pengiriman menjadi adapter:
  - WhatsApp → `whatsapp_client.send_whatsapp_message(...)`
  - Telegram → `telegram_client.send_telegram_message(...)` (baru)

### 7.2 Scope yang paling aman (minimal)
Mulai dari **notifikasi admin** (bukan user) karena:
- admin sudah punya sistem subscription `NotificationRecipient (admin_user_id + notification_type)`
- user Telegram membutuhkan pairing/registrasi chat id yang belum ada flow-nya

### 7.3 Perubahan yang dibutuhkan (high-level)
1) Tambah gateway baru:
- `backend/app/infrastructure/gateways/telegram_client.py`
- Implement `sendMessage` via Telegram Bot API.

2) Tambah ENV secret (server-side):
- `TELEGRAM_BOT_TOKEN=...`
- Opsional: `TELEGRAM_API_BASE_URL=https://api.telegram.org` (default)

3) Tentukan mapping “admin → chat_id”
Opsi A (paling rapi, butuh migrasi kecil):
- Tambah kolom `users.telegram_chat_id` (nullable)
- Admin mengisi chat id (sementara via DB/manual) atau nanti lewat UI.

Opsi B (tanpa migrasi DB, tetapi kurang fleksibel):
- Simpan chat id di env: `TELEGRAM_ADMIN_CHAT_IDS=123,456`.

4) Pengiriman
- Saat trigger notifikasi (komandan request, quota debt limit, dsb):
  - render message pakai `get_notification_message(...)`
  - kirim via WhatsApp jika enabled
  - kirim via Telegram jika token tersedia dan admin punya `chat_id`

5) Pengaturan & uji coba
- Kunci settings Telegram disimpan via Admin → Pengaturan → Integrasi (`ENABLE_TELEGRAM_NOTIFICATIONS`, `TELEGRAM_BOT_TOKEN`, dll).
- Endpoint uji kirim (admin): `POST /api/admin/telegram/test-send`.

### 7.4 Catatan Keamanan
- Token bot Telegram adalah secret: hanya di `.env.prod` (jangan masuk `.env.public*`).
- Hindari mencetak token ke log.

Jika ingin saya implement, saya butuh keputusan: mapping chat id pakai Opsi A (kolom DB) atau Opsi B (env), dan target awalnya admin-only atau termasuk user.
- **Di Windows:** Gunakan redirect MikroTik dengan `ip`/`mac`.
- **Di Linux server produksi:** Gunakan host-network atau reverse proxy di host agar IP asli terbaca.

---

## 7) Referensi File Kunci (Sering Disentuh)

- Layout utama: `frontend/layouts/default.vue`
- Layout navbar: 
  - `frontend/layouts/components/DefaultLayoutWithVerticalNav.vue`
  - `frontend/layouts/components/DefaultLayoutWithHorizontalNav.vue`
- User profile: `frontend/layouts/components/UserProfile.vue`
- Footer: `frontend/layouts/components/Footer.vue`
- Navigasi: `frontend/navigation/*`
- Vuetify config: `frontend/plugins/vuetify/*`
- Theme config: `frontend/themeConfig.ts`

---

## 8) Checklist Saat Lanjut Pengembangan

- Pastikan `pnpm run lint` bersih.
- Pastikan `nuxi typecheck` (atau `pnpm run build`) tidak error.
- Validasi UI header/footer di layout vertical & horizontal.
- Jika menambah icon, pastikan bundling `frontend/plugins/iconify/build-icons.ts` sudah sesuai.

---

## 9) Perubahan Terbaru (Feb 2026 - Tambahan)

1. **IP Binding aktif kembali (MikroTik)**
  - Upsert ip-binding kini memaksa `disabled=false` agar binding lama yang nonaktif ikut aktif.

2. **Comment MikroTik ditambah tanggal/jam**
  - Address-list dan ip-binding menyertakan `date` + `time`.
  - Order comment memuat paket + tanggal + jam.

3. **Timezone aplikasi via ENV**
  - Tambah `APP_TIMEZONE` (default `Asia/Makassar`) dan dipakai untuk semua tanggal/jam di comment.

4. **UI Captive/Login: Tombol ambil IP/MAC**
  - Jika query `client_ip`/`client_mac` kosong, tampil tombol ke `APP_LINK_MIKROTIK`.

---

## 10) Perubahan Terbaru (Feb 2026 - Konsistensi Kuota & Testing)

1. **Konsistensi kuota (MB desimal)**
  - Perhitungan usage di backend dibulatkan konsisten (2 desimal) dan response kuota memakai float.
  - Frontend menampilkan MB desimal saat ada pecahan (chart kuota).

2. **Delta usage per-MAC + Redis**
  - Sinkronisasi kuota menghitung delta per MAC dari `/ip/hotspot/host` untuk menghindari double count.
  - Redis menyimpan `last_bytes` per MAC + lock per user saat sync.

3. **Testing fallback untuk pytest**
  - Jika env DB tidak tersedia saat pytest, backend memakai `sqlite:///:memory:`.
  - Validasi produksi dilewati saat pytest berjalan.

4. **CSRF & error handler**
  - Origin guard untuk cookie auth (CSRF) + JSON error handler standar.
  - Health endpoint selalu HTTP 200 dengan status `ok`/`degraded`.

5. **Env tambahan**
  - `CSRF_PROTECT_ENABLED`, `CSRF_TRUSTED_ORIGINS`, `LOG_IP_HEADER_DEBUG`.
  - `APP_PUBLIC_BASE_URL` dipakai untuk URL publik.

5. **Keamanan dasar**
  - Cookie auth `secure` otomatis di produksi.
  - Nuxt devtools nonaktif di produksi.
  - Security headers dasar di Nginx.

6. **Sync ENV**
  - Backend & frontend env diselaraskan dengan `.env.example`.
  - Tambahan kunci backend (ringkas):
    - `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`, `OTP_EXPIRE_SECONDS`.
    - `MIKROTIK_SSL_VERIFY`, `MIKROTIK_PLAIN_TEXT_LOGIN`, `MIKROTIK_SEND_LIMIT_BYTES_TOTAL`, `MIKROTIK_SEND_SESSION_TIMEOUT`.
    - `AUTO_ENROLL_DEVICES_FROM_IP_BINDING`, `AUTO_ENROLL_DEBUG_LOG`.
    - `RATELIMIT_STRATEGY`, `RATELIMIT_ENABLED`, `PING_RATE_LIMIT`.
    - `LOG_FILENAME`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`, `LOG_FILE_LEVEL`.

7. **Audit lint**
  - Backend: `ruff check .` ✅
  - Frontend: `pnpm lint` ✅

8. **Kebijakan Komandan di UI**
  - Form komandan membaca `KOMANDAN_*` dari settings publik.
  - Opsi unlimited dinonaktifkan jika kebijakan menolak.
  - Pesan cooldown/window menampilkan countdown untuk retry.

9. **Template notifikasi Komandan**
  - Template WhatsApp berada di `backend/app/notifications/templates.json`.
  - Kunci baru: `komandan_quota_low` dan `komandan_quota_expiry_warning`.

10. **Sinkronisasi kuota bersifat monotonic**
  - Counter host turun dianggap reset; total kuota tetap akumulatif.
  - `DailyUsageLog` mengikuti delta agar grafik tetap konsisten.

11. **Interval sync dinamis**
  - Celery Beat bisa berjalan lebih sering, tetapi task akan skip jika belum mencapai `QUOTA_SYNC_INTERVAL_SECONDS` (throttle via Redis).

12. **Auto-enroll device dari ip-binding**
  - Sinkronisasi kuota mencoba menambah device berdasarkan `comment` ip-binding berformat `user=<id>`.
  - Dibatasi `MAX_DEVICES_PER_USER`, debug per MAC hanya jika `AUTO_ENROLL_DEBUG_LOG=True`.

---

## 10) Pembaruan Midtrans/WA/Allowlist (Feb 2026)

1. **Fallback ENV saat setting DB kosong**
  - `get_setting()` kini mengembalikan nilai ENV jika value DB kosong/null.
  - Mencegah konfigurasi penting (URL publik, Midtrans, WA, allowlist) menjadi `None`.

2. **URL invoice WA wajib HTTPS publik**
  - `APP_PUBLIC_BASE_URL` diarahkan ke domain Cloudflare HTTPS.
  - Task WA invoice sekarang mengakses URL PDF publik (bukan `lpsaring.local`).

3. **Walled garden allowlist untuk Midtrans + domain app**
  - `WALLED_GARDEN_ALLOWED_HOSTS` berisi domain app + `app.midtrans.com`/`api.midtrans.com` (prod & sandbox).
  - Sinkronisasi walled garden dijalankan ulang untuk menerapkan allowlist.

4. **Finish page (payment) dirapikan**
  - Ikon dinormalisasi ke prefix `tabler-`.
  - Download invoice dibuka via tab baru sebelum fetch blob.

---

## 11) Mode OTP-only & IP Binding (Feb 2026)

Sistem ini menggunakan **portal OTP** sebagai satu-satunya login. MikroTik **tidak** dipakai untuk login username/password, hanya untuk mengirim IP/MAC ke portal.

Implikasi konfigurasi:
1. **IP binding tetap `bypassed`**
  - Setelah OTP sukses, device diberi akses internet tanpa login hotspot.

2. **Fail-open dimatikan**
  - `IP_BINDING_FAIL_OPEN=False` agar gagal binding tidak membuka akses.

3. **Approval perangkat**
  - `REQUIRE_EXPLICIT_DEVICE_AUTH=True` jika ingin perangkat baru melewati mekanisme otorisasi (pending-auth).
  - `OTP_AUTO_AUTHORIZE_DEVICE=True` (default) membuat **OTP sukses = user mengotorisasi device yang sedang dipakai**, sehingga tidak ke-block saat MAC berubah (privacy/random).
  - Jika ingin benar-benar “admin approve device baru”, set `OTP_AUTO_AUTHORIZE_DEVICE=False`.

4. **Walled garden hanya untuk portal/info**
  - Portal, API, dan domain pembayaran/WA di-allow untuk proses OTP.

5. **Portal info untuk troubleshooting**
  - Halaman `/portal` menyediakan tombol cepat untuk login Mikrotik, captive, login OTP, dan dashboard.
  - Dipakai saat perangkat sudah online tetapi IP/MAC belum terbaca.
  - Link `/portal` ditambahkan ke navigasi utama agar mudah diakses.

---

Jika diperlukan, bagian ini bisa diperluas menjadi dokumentasi modul per fitur (dashboard, user management, dsb.).

---

## 12) Kebijakan Request Komandan (Quota/Unlimited)

Komandan dapat mengajukan request QUOTA atau UNLIMITED. Admin tetap memegang approval penuh.

Kebijakan pembatasan request dikendalikan oleh ENV:
- `KOMANDAN_REQUEST_WINDOW_HOURS`
- `KOMANDAN_REQUEST_MAX_PER_WINDOW`
- `KOMANDAN_REQUEST_COOLDOWN_HOURS`
- `KOMANDAN_ALLOW_UNLIMITED_REQUEST`
- `KOMANDAN_MAX_QUOTA_MB`
- `KOMANDAN_MAX_QUOTA_DAYS`
- `KOMANDAN_MAX_UNLIMITED_DAYS`

Logika approval menggunakan batas di atas untuk mencegah over‑grant.
