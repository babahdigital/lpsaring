# Dokumen Pengembangan (lpsaring)

Dokumen ini merangkum struktur proyek, cara menjalankan lingkungan development, dan langkah awal belajar kode secara bertahap.

## 1) Ringkasan Arsitektur
Proyek ini adalah aplikasi portal hotspot berbasis:
- Backend: Flask + SQLAlchemy + Celery + Redis
- Frontend: Nuxt 3 (Vue 3) + Vuetify
- Database: PostgreSQL
- Reverse proxy: Nginx

Komponen utama berjalan via Docker Compose (mode development) dan dapat dijalankan juga secara lokal jika diperlukan.

## 2) Struktur Folder Utama
Ringkasan struktur:
- backend/
  - app/: inti aplikasi Flask (blueprints, services, infrastructure)
  - migrations/: migrasi database (Alembic/Flask-Migrate)
  - requirements.txt: dependensi Python
  - run.py: entrypoint app Flask (Gunicorn menargetkan run:app)
  - config.py: konfigurasi environment
- frontend/
  - pages/, layouts/, components/: struktur Nuxt
  - nuxt.config.ts: konfigurasi Nuxt
  - package.json: scripts & dependensi
- infrastructure/
  - nginx/conf.d/app.conf: reverse-proxy ke backend (/api) & frontend (/)
- docker-compose.yml: stack development (db, redis, backend, celery, frontend, nginx)
- docker-compose.prod.yml: stack production (menggunakan image build)

## 3) Layanan & Port Default (Development)
- PostgreSQL: internal, tidak diekspose
- Redis: internal, tidak diekspose
- Backend (Flask/Gunicorn): 5010 (host → container)
- Frontend (Nuxt dev server): 3010 (host → container)
- Nginx: 80 (host → container)

## 4) File Environment
Siapkan file environment berikut:
- Root profile env (dipakai juga oleh frontend container):
  - `.env.public` untuk profile publik/dev
  - `.env.public.prod` untuk profile production
  - `APP_ENV` menentukan profile aktif (`public` atau `public.prod`)
- Backend: backend/.env
- Frontend: frontend/.env

Template tersedia di:
- .env.example
- .env.public.prod.example
- backend/.env.example
- frontend/.env.example

Lampiran wajib untuk setiap pembaruan dokumen:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

### Minimal yang perlu diisi
Root .env
- POSTGRES_DB
- POSTGRES_USER
- POSTGRES_PASSWORD

backend/.env
- DB_USER, DB_PASSWORD, DB_HOST, DB_NAME, DATABASE_URL
- SECRET_KEY, JWT_SECRET_KEY
- MIDTRANS_* jika fitur pembayaran dipakai
- WHATSAPP_* jika notifikasi WA dipakai
- MIKROTIK_* jika integrasi mikrotik dipakai

frontend/.env
- NUXT_PUBLIC_API_BASE_URL
- NUXT_PUBLIC_MIDTRANS_CLIENT_KEY

## 5) Menjalankan via Docker Compose (Disarankan)
Mode dev yang dipakai sekarang: **backend + db + nginx di Docker**, frontend Nuxt **jalan di host**, akses publik melalui **Cloudflare Tunnel (HTTPS)**.

Langkah umum:
1) Salin file .env dari template
2) Jalankan stack Docker (tanpa frontend container)
3) Jalankan Nuxt dev server di host
4) Akses aplikasi via Nginx

Catatan environment (dev):
- Gunakan `APP_ENV=local` agar backend memakai `backend/.env.local`.
- E2E script otomatis memakai `APP_ENV=local` (atau override dengan `-AppEnv`).

Catatan environment (prod):
- Jalankan compose prod dengan file interpolasi khusus: `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d`.
- Set `APP_ENV=public.prod` agar frontend container membaca profile root `.env.public.prod`.
- Cloudflared di compose sekarang bersifat opsional (profile `tunnel`), aktifkan hanya jika token sudah valid.

Catatan:
- Backend dan Celery akan bergantung pada Postgres & Redis
- Nginx mengarah ke /api → backend:5010, dan / → frontend dev server di host
- Kuota disinkronkan dari MikroTik dengan delta per-MAC dan pembulatan MB konsisten.
- Pytest backend memakai fallback sqlite in-memory saat env DB belum tersedia.

### 5.1) Mode Dev Hybrid (Direkomendasikan)
Jalankan stack Docker (backend, db, redis, nginx):
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`

Pastikan frontend container **tidak** berjalan saat mode host:
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml stop frontend`

Jalankan Nuxt di host (wajib bind ke 0.0.0.0):
- `pnpm dev --host 0.0.0.0 --port 3010`
- atau `pnpm run dev:host`

Untuk HTTPS publik via Cloudflare Tunnel, jalankan dengan env publik:
- `pnpm run dev:public`

Status check cepat (hindari 504):
- Host: `curl -I http://localhost:3010/_nuxt/`
- Dari container Nginx: `docker exec hotspot_nginx_proxy sh -c "wget -S --spider -T 5 http://host.docker.internal:3010/_nuxt/"`

Jika 504 masih muncul:
- Pastikan dev server benar-benar hidup.
- Pastikan port 3010 tidak diblokir firewall Windows.

Jika ingin menjalankan frontend di Docker (opsional):
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile frontend up -d`

Catatan VS Code (host):
- Pastikan `pnpm` terpasang di host (mis. `corepack enable` atau `npm i -g pnpm`).
- Jalankan `pnpm install` di folder `frontend/` agar TypeScript/Vue di VS Code tidak error.

### 5.2) Operasional Harian
Log Docker:
- `docker compose logs -f backend`
- `docker compose logs -f nginx`

Restart Docker setelah perubahan konfigurasi/env:
- `docker compose up -d`

Uji cepat setelah perubahan keamanan:
- `docker compose exec -T backend pytest`
- `powershell.exe -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1 -AppEnv local`

Catatan CSRF mode ketat (dev/staging):
- Set `CSRF_STRICT_NO_ORIGIN=True`.
- Isi `CSRF_NO_ORIGIN_ALLOWED_IPS` dengan IP non-browser dan CIDR Docker (contoh `172.16.0.0/12`).

Lint frontend (di host):
- `pnpm run lint`

Lint backend (di container):
- `docker compose exec -T backend ruff check .`

Clear cache Nuxt/Vite (di host):
- `rm -rf .nuxt .output .nitro node_modules/.vite`

Jika muncul error seperti "Failed to load module script" pada `icons.css`:
- Pastikan frontend **host** yang melayani `/\_nuxt/*`, bukan container frontend.
- Pastikan skema HMR (`ws`/`wss`) sesuai dengan skema halaman.

Rebuild image (jika perlu):
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`
- Recreate build (paksa container baru):
  - `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile frontend up -d --build --force-recreate`

### 5.2.1) Catatan Performa Frontend
- ApexCharts di-load secara async dan hanya dipakai di halaman chart.
- Dependensi berat yang tidak dipakai (Tiptap, Chart.js) dihapus.
- Gunakan build analyze untuk memantau ukuran bundle:
  - `pnpm nuxi build --analyze`

Catatan HTTPS + HMR:
- Skema **harus konsisten**: jika akses lewat HTTPS, set `NUXT_PUBLIC_*` ke `https://` dan `NUXT_PUBLIC_HMR_PROTOCOL=wss`.
- Mixed Content akan muncul jika halaman HTTPS mencoba HMR ke `ws://`.
- Jika muncul HMR menuju `ws://localhost:5173`, biasanya dev server tidak memuat `.env.public`. Gunakan `pnpm run dev:public`.
- Untuk mode HTTPS via Cloudflare Tunnel, origin tetap HTTP di Nginx, tetapi header `X-Forwarded-Proto` dipakai agar backend mengetahui skema HTTPS.
- Pastikan backend `.env.public` memakai URL `https://` agar CORS dan link konsisten.

### 5.3) Build Image di GitHub Actions
Workflow publish image ada di `.github/workflows/docker-publish.yml`.

Perilaku workflow:
- Push ke `main`: build + push image backend/frontend ke Docker Hub.
- Push tag `v*`: build + push image dengan tag versi.
- Manual `workflow_dispatch`: bisa pilih deploy ke self-hosted runner (`deploy=true`).

Secrets yang wajib di GitHub repository:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Catatan operasional:
- Deploy ke Raspberry Pi **tidak otomatis** saat push; hanya berjalan saat manual dispatch dengan `deploy=true`.
- Untuk menjalankan cloudflared di produksi: `docker compose --env-file .env.prod -f docker-compose.prod.yml --profile tunnel up -d`.
- Jika tidak butuh HMR, pakai build produksi dan akses via Nginx/Cloudflare.

Catatan Cloudflare cache (dev):
- Jika `icons.css` atau aset `/\_nuxt/` salah MIME, purge cache Cloudflare untuk path `/\_nuxt/*`.
- Nginx dev sudah mengirim `Cache-Control: no-store` untuk `/\_nuxt/` agar cache tidak nyangkut.

## 5.3) Catatan Lint (Vue/TS)
Jika `pnpm run lint` gagal karena error ESLint atau parse JSON:
- Gunakan konfigurasi flat di [frontend/eslint.config.js](frontend/eslint.config.js).
- Parser Vue perlu `vue-eslint-parser` di devDependencies.
- Direktori `.pnpm-store` dan file JSON di-ignore agar tidak diparse ESLint.

Jalankan lint di host:
- `pnpm run lint`

Jika masih error, pastikan `pnpm install` sudah dijalankan sesuai mode.

Catatan:
- Pada mode dev hybrid, `pnpm install` dijalankan di host.
- Pada mode frontend di Docker, jalankan `docker compose exec frontend pnpm install`.

## 5.4) Aturan Coding (Wajib) – Cegah Error Berulang
Gunakan aturan berikut agar error lint/bug tidak muncul lagi:

### Backend (Python)
- **Jangan** gunakan one‑liner control flow.
  - ❌ `if x: return y` / `except: pass` / `a; b`
  - ✅ Multi‑line dengan indent jelas.
- **Jangan** bandingkan boolean/None secara eksplisit.
  - ❌ `x == True`, `x == False`, `x == None`
  - ✅ `if x:`, `if not x:`, `x is None`, `x is not None`
- **Import harus di atas** (module level). Jangan import di tengah file.
- Setiap perubahan file Python **wajib** di‑lint di container:
  - `docker compose exec -T backend ruff check .`
- Konfigurasi Ruff ada di [backend/ruff.toml](backend/ruff.toml). Jangan hapus/ubah tanpa alasan.

### Frontend (Vue/TS/Nuxt)
- **Tidak ada hardcoded URL** (WhatsApp, redirect, base URL). Gunakan env/public runtime config.
- Jalankan lint sesuai mode:
  - Host: `pnpm run lint`
  - Docker frontend: `docker compose exec frontend pnpm run lint`

### Umum
- Edit minimal: hanya file yang terkait perubahan.
- Jangan menambah perubahan format/rapian jika tidak menyentuh fungsinya.
- Semua env harus lewat **.env.local/.env** (frontend) & **backend/.env**.

## 5.5) Testing (Pytest)
- Pytest backend memakai fallback `sqlite:///:memory:` saat env DB belum tersedia (khusus testing).
- Jika ingin konek database nyata, set `DATABASE_URL` atau `TEST_DATABASE_URL`.

## 5.6) Catatan Keamanan Runtime
- `/api/health` selalu mengembalikan HTTP 200 dengan status `ok`/`degraded` agar portal tidak dianggap down ketika satu dependency tidak sehat.
- Autentikasi berbasis cookie memakai pemeriksaan origin untuk request non-GET/HEAD/OPTIONS.
  - Atur `CSRF_PROTECT_ENABLED` dan `CSRF_TRUSTED_ORIGINS` di backend/.env sesuai domain portal.

## 6) Menjalankan Secara Lokal (Opsional)
**Peringatan:** jalur ini hanya untuk troubleshooting. Jangan gunakan untuk workflow utama agar tidak terjadi perbedaan hasil dengan Docker.
### Backend
- Buat virtualenv dan install dependencies dari backend/requirements.txt
- Pastikan variabel .env backend diisi
- Jalankan aplikasi Flask dengan run.py atau via Flask CLI

### Frontend
- Gunakan pnpm (disarankan oleh proyek)
- Install dependency dan jalankan nuxt dev

## 6.1) Testing
Backend (pytest):
- `cd backend && python -m pytest`

Frontend (vitest):
- `cd frontend && pnpm test`
- Watch mode: `pnpm run test:watch`

## 7) Titik Masuk Kode Penting
Backend:
- app/__init__.py: factory `create_app()`, registrasi blueprint dan extension
- app/infrastructure/http/: definisi route API
- app/services/: logika bisnis
- app/infrastructure/db/models/: model database
- app/tasks.py: task Celery

Frontend:
- pages/: halaman
- components/: komponen UI
- layouts/: layout global
- plugins/: plugin Nuxt
- store/: state management (Pinia)

## 8) Rencana Belajar Bertahap (Mulai Perlahan)
Tahap 1: Jalankan stack dev via Docker
- Pastikan Nginx (port 80) dan backend /api/ping berjalan

Tahap 2: Kenali alur API
- Baca route di backend/app/infrastructure/http/
- Fokus endpoint dasar: auth, packages, transactions, public

Tahap 3: Kenali alur frontend
- Cari halaman yang memanggil API (/api)
- Lacak penggunaan store dan composables

Tahap 4: Pahami integrasi eksternal
- Midtrans, WhatsApp API, Mikrotik

## 9) Catatan Produksi
- Gunakan docker-compose.prod.yml
- Pastikan semua secret di .env.prod lengkap
- Set APP_PUBLIC_BASE_URL dan secrets dengan aman

## 9.2) Mode OTP-only (Tanpa Login MikroTik)

Sistem ini **tidak** melakukan login username/password ke MikroTik. File login MikroTik hanya berfungsi membawa `ip/mac` ke portal OTP.

Konsekuensi konfigurasi:
- `IP_BINDING_TYPE_ALLOWED=bypassed` agar akses internet dibuka setelah OTP sukses.
- `IP_BINDING_FAIL_OPEN=False` untuk mencegah akses jika binding gagal.
- `REQUIRE_EXPLICIT_DEVICE_AUTH=True` jika ingin approval perangkat baru.
- Walled garden hanya untuk portal/info dan domain payment/WA yang dibutuhkan.
- Gunakan halaman `/portal` untuk bantuan ketika perangkat sudah online tetapi IP/MAC belum terbaca.

Catatan sinkronisasi kuota:
- Sumber data kuota: `/ip/hotspot/host` (per MAC).
- Akumulasi kuota bersifat monotonic; counter host turun dianggap reset dan total tetap bertambah.
- Auto-enroll perangkat dari `ip-binding` berbasis `comment` (format `user=<id>`), dibatasi `MAX_DEVICES_PER_USER`.
- Debug auto-enroll per MAC hanya saat `AUTO_ENROLL_DEBUG_LOG=True`.
- Statistik harian/mingguan/bulanan mengikuti `APP_TIMEZONE`.

## 9.1) Akses HTTPS via Cloudflare Tunnel (Untuk Midtrans & WhatsApp Webhook)
Gunakan Cloudflare Tunnel agar aplikasi bisa diakses dari luar dengan HTTPS tanpa membuka port publik.

### A) Buat Tunnel
1. Install **cloudflared** (Zero Trust) di host.
2. Buat tunnel baru di Dashboard Cloudflare Zero Trust.
3. Download **credentials file** (JSON) dari Cloudflare.

### B) Konfigurasi cloudflared
File konfigurasi tunnel ada di:
- [infrastructure/cloudflared/config.yml](infrastructure/cloudflared/config.yml)

Ubah hostname sesuai domain kamu (contoh):
```yaml
ingress:
  - hostname: lpsaring.babahdigital.net
    service: http://nginx:80
  - service: http_status:404
```

Jika menggunakan token, **tidak perlu** `credentials-file` di config.

Contoh file konfigurasi (Windows) jika ingin standalone (opsional):
```yaml
# %USERPROFILE%\.cloudflared\config.yml
ingress:
  - hostname: hotspot.example.com
    service: http://localhost:80
  - service: http_status:404
```

Catatan:
- Arahkan tunnel ke **Nginx (port 80)** karena Nginx sudah proxy `/api` ke backend.
- Ganti `hotspot.example.com` dengan domain kamu.

### C) Jalankan Tunnel
```bash
cloudflared tunnel run <NAMA_TUNNEL>
```

Untuk Docker Compose, set env di `.env.prod`:
- `CLOUDFLARED_TUNNEL_TOKEN=<CLOUDFLARE_TUNNEL_TOKEN>`

Untuk **development**, gunakan `.env` (root project):
- `CLOUDFLARED_TUNNEL_TOKEN=<CLOUDFLARE_TUNNEL_TOKEN>`
- `APP_PUBLIC_BASE_URL=https://lpsaring.babahdigital.net`
- `FRONTEND_URL=https://lpsaring.babahdigital.net`

### D) Verifikasi HTTPS
1. Pastikan DNS `lpsaring.babahdigital.net` sudah **CNAME** ke tunnel.
2. Jalankan stack + cloudflared.
3. Cek:
  - `https://lpsaring.babahdigital.net/`
  - `https://lpsaring.babahdigital.net/api/ping`

  ## 10) Ringkasan Pekerjaan & Masalah (Sesi Ini)
  Bagian ini merangkum perubahan yang sudah dilakukan, masalah yang muncul, dan bagaimana cara menyelesaikannya.

  ### 10.1) Perubahan yang Dilakukan
  - Tambah setup frontend testing: Vitest config, smoke test util formatters, dan script `test` + `test:watch`.
  - Perbaikan derivasi HMR di Nuxt agar mengikuti `NUXT_PUBLIC_APP_BASE_URL` (HTTP -> `ws`, HTTPS -> `wss`).
  - Rapikan UI halaman `/login` dan `/captive` agar konsisten dengan layout auth Vuetify.
  - Dokumentasi dev hybrid diperbarui (frontend di host, backend + nginx di Docker) dan checklist testing.
  - Penyesuaian `.env` untuk mode lokal (HTTP, `localhost`/`lpsaring.local`).
  - Nginx dev diarahkan ke host dev server (`app.dev.conf`) dan dependensi frontend container dihapus dari `depends_on`.

  ### 10.2) Masalah yang Dihadapi
  - 504 saat memuat asset Nuxt/Vite (`/_nuxt/*`).
  - HMR gagal karena browser mencoba `wss://` saat akses HTTP.
  - Frontend host mencoba akses `http://backend:5010` (DNS `backend` tidak resolvable di host).
  - MIME type CSS/JS salah (HTML), akibat upstream `/_nuxt` gagal.
  - Port 3010 sempat dipakai proses lain.

  ### 10.3) Penyelesaian
  - Pastikan dev server Nuxt berjalan di host: `pnpm run dev:host` (bind `0.0.0.0:3010`).
  - Konfigurasi HMR mengikuti `NUXT_PUBLIC_APP_BASE_URL` dan `.env.local` (HTTP -> `ws`).
  - Ubah `NUXT_INTERNAL_API_BASE_URL` ke `http://localhost:5010/api` untuk host dev.
  - Nginx dev proxy ke `host.docker.internal:3010` melalui `app.dev.conf`.
  - Restart Nginx dengan override dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d nginx`.
  - Bersihkan cache Nuxt/Vite (`.nuxt`, `.output`, `.vite`) saat perlu.
  - Hentikan proses pemakai port 3010 dan restart dev server.

  ### 10.4) Catatan Verifikasi
  - Cek `_nuxt` dari host: `curl -I http://localhost:3010/_nuxt/`.
  - Cek dari Nginx container: `docker exec hotspot_nginx_proxy sh -c "wget -S --spider -T 5 http://host.docker.internal:3010/_nuxt/"`.
  - Pastikan browser membuka `http://lpsaring.local` (bukan HTTPS) untuk menghindari `wss`.

### D) Update .env/.env.prod
Set variabel agar URL publik konsisten dengan HTTPS:
- `APP_PUBLIC_BASE_URL=https://hotspot.example.com`
- `FRONTEND_URL=https://hotspot.example.com`
- `NUXT_APP_BASE_URL=https://hotspot.example.com`
- `NUXT_PUBLIC_API_BASE_URL=/api`

### E) Set Webhook/Callback Eksternal
- **Midtrans**: set Notification/Redirect URL ke `https://hotspot.example.com/...`
- **WhatsApp (Fonnte)**: set webhook ke `https://hotspot.example.com/...`

## 10) Catatan Perubahan Terbaru (2026-02-09)
- Penambahan halaman captive portal di frontend untuk alur login hotspot (OTP → login Mikrotik).
- Endpoint `/api/auth/verify-otp` mengembalikan kredensial hotspot (username/password) untuk proses login hotspot.
- Redirect MikroTik `login.html` diarahkan ke `/captive` dengan membawa parameter hotspot (link-login-only, chap-id, dll).
- Penyesuaian template notifikasi agar menekankan login via OTP portal, kredensial hotspot jadi cadangan.
- Perbaikan middleware agar `/captive` bisa diakses guest.
- Penambahan fallback jika parameter CHAP tidak tersedia (pakai password biasa).
- Perbaikan routing API agar dinamis untuk dev/produksi melalui proxy Nuxt/Nitro.
- Penyesuaian konfigurasi base URL API di Nuxt agar konsisten dan tidak memicu 404.
- Lint fix pada frontend composables (penanganan timeout pada `useSnackbar`).
- Restart Docker Compose dan verifikasi log layanan utama (backend, frontend, db, redis, celery, nginx).
- Sinkronisasi default model vs server default di DB (migrasi 20260208_align_server_defaults).
- Perbaikan template notifikasi dan pengiriman konteks agar tidak fallback kosong.

## 10.1) Catatan Perubahan Terbaru (2026-02-10)
- Perbaikan path Iconify CSS agar tidak diperlakukan sebagai plugin Nuxt.
- Output Iconify CSS dipindah ke `frontend/assets/iconify/icons.css`.
- Pembaruan konfigurasi ESLint (flat config) agar lint berjalan di container.

## 11) Status & Masalah Saat Ini (2026-02-09)
**Gejala utama**: OTP tidak terkirim dari halaman login/captive, tapi registrasi berhasil kirim OTP.

**Hasil uji**:
- Panggilan langsung ke backend `/api/auth/request-otp` sukses (HTTP 200).
- Akses frontend melalui hotspot berhasil memuat halaman.
- Di log Nginx, **tidak ada POST** ke `/api/auth/request-otp` saat klik “Kirim OTP”.

**Kesimpulan sementara**: masalah ada pada konektivitas dari frontend → backend **melalui hotspot**, bukan backendnya.

**Penyebab paling mungkin**:
- Walled‑Garden belum mengizinkan akses ke portal/API (dst-address/dst-host).
- HTTPS/HSTS memaksa `https://` sehingga request gagal.
- DNS/route portal tidak konsisten (sebaiknya pakai IP langsung saat testing).

**Checklist perbaikan**:
1) Walled‑Garden allow **dst-address=IP portal** (contoh 10.0.0.6) dan/atau **dst-host=dev.sobigidul.com**.
2) Pastikan akses portal pakai **http://IP/captive** (hindari HTTPS).
3) Pastikan file `login.html` di MikroTik sudah versi terbaru.

### Catatan Log (terbaru)
- Backend: reload worker karena perubahan file (normal pada mode dev).
- Nginx: warning IPv6 conf read-only saat entrypoint (umum pada image nginx).
- Frontend: peringatan Vue Router untuk path Chrome DevTools (aman diabaikan).

## 12) Cara Menjalankan Full Test & Simulasi
Full test otomatis tersedia di PowerShell script:
- [scripts/simulate_end_to_end.ps1](scripts/simulate_end_to_end.ps1)

### 12.1 Prasyarat
- Docker Desktop aktif.
- File environment sudah diisi (.env root, backend/.env, frontend/.env).
- WhatsApp gateway dan MikroTik API sudah dikonfigurasi (opsional untuk simulasi penuh).

### 12.2 Menjalankan Full Test (Windows / PowerShell)
Jalankan dari root proyek:
- `./scripts/simulate_end_to_end.ps1`

Jika perlu menyesuaikan URL atau nomor:
- `./scripts/simulate_end_to_end.ps1 -BaseUrl http://10.0.0.6 -UserPhone 0811580039`

Parameter yang sering disesuaikan:
- `BaseUrl`: basis URL untuk API dan frontend (script akan memisahkan API vs frontend jika perlu).
- `SimulatedClientIp`, `SimulatedClientMac`: identitas user utama.
- `SimulatedKomandanIp`: IP khusus Komandan (mencegah kontaminasi binding).
- `RunKomandanFlow`: set `false` untuk melewati flow Komandan.
- `FreshStart`: reset DB + volume sebelum simulasi.
- `CleanupAddressList`: bersihkan address-list untuk IP simulasi.

### 12.3 Apa yang Dilakukan Script
1) Menyalakan container (db, redis, backend, celery, frontend, nginx).
2) Menunggu backend siap (`/api/ping`) dan menentukan `ApiBaseUrl` + `FrontendBaseUrl`.
3) Menjalankan migrasi & seed data.
4) Membuat admin (idempotent) dan login admin.
5) Set settings penting (IP binding, walled‑garden, profil expired).
6) Registrasi user, approve user.
7) Request OTP (dengan retry jika cooldown aktif) dan ambil OTP dari Redis (bypass untuk testing).
8) Verify OTP via Nginx dengan header `X-Forwarded-For`.
9) Debug binding resolution dan uji endpoint device binding.
10) Uji halaman status frontend (login/captive) dan redirect berbasis cookie auth.
11) Uji status signed (blocked/inactive) dari error token.
12) Simulasi flow Komandan (request + approval) dengan IP terpisah (opsional).
13) Simulasi transaksi paket (SUCCESS).
14) Simulasi kuota (FUP/Habis/Expired), apply MikroTik, validasi address-list, lalu sync walled‑garden.

### 12.4 Cara Validasi Hasil
- Cek log backend untuk IP binding & login:
  - `docker compose logs --tail=200 backend | Select-String 'IP determined|X-Forwarded-For'`
- Cek Mikrotik via script:
  - `docker compose exec backend env PYTHONPATH=/app python /app/scripts/ensure_mikrotik_profile.py --name profile-expired --comment "auto-created"`
  - `docker compose exec backend env PYTHONPATH=/app python /app/scripts/run_walled_garden_sync.py`
- Validasi address-list per status via skrip E2E (fup/habis/expired). Jika IP hotspot kosong, fallback memakai ip-binding atau MAC yang sudah authorized.
- Untuk inspeksi state MikroTik:
  - `docker compose exec backend env PYTHONPATH=/app python /app/scripts/check_mikrotik_state.py --phone 0811580039 --client-ip 172.16.15.254 --client-mac 4E:C3:55:C6:21:67`

### 12.5 Catatan Khusus Captive Test
- Jika testing dari HP hotspot, pastikan portal dan API **di-allow** oleh walled‑garden.
- Gunakan URL `http://IP-PORTAL/captive` (hindari HTTPS/HSTS saat testing).

---
Jika ingin, langkah berikutnya: pilih satu modul kecil (misalnya auth), lalu kita pelajari alurnya dari frontend → backend secara detail.
