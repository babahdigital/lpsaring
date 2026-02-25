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

## 2.1) Klasifikasi Docker Compose
Development:
- `docker-compose.yml`

Production:
- `docker-compose.prod.yml` (dipakai juga oleh workflow publish/deploy)

## 3) Layanan & Port Default (Development)
- PostgreSQL: internal, tidak diekspose
- Redis: internal, tidak diekspose
- Backend (Flask/Gunicorn): 5010 (host → container)
- Frontend (Nuxt dev server): 3010 (host → container)
- Nginx: 80 (host → container)

## 3.1) Pembayaran (Snap vs Core API)

Mode pembayaran dikontrol dari Setting Admin:
- `PAYMENT_PROVIDER_MODE=snap` → pembayaran via Snap UI (Snap.js di-load lazy saat diperlukan).
- `PAYMENT_PROVIDER_MODE=core_api` → tanpa Snap UI (server-to-server), mendukung QRIS/GoPay/VA (+ ShopeePay jika channel aktif).

URL status pembayaran (yang dibagikan ke user) adalah:
- `/payment/status?order_id=...`
  - Untuk link shareable lintas device (mis. via WhatsApp), server bisa menambahkan token bertanda tangan: `/payment/status?order_id=...&t=<SIGNED_TOKEN>`

Env terkait link status shareable (public):
- `TRANSACTION_STATUS_TOKEN_MAX_AGE_SECONDS` → TTL token `t` (default 7 hari; dibatasi min 5 menit, max 30 hari).
- Rate limit endpoint public (Flask-Limiter):
  - `PUBLIC_TRANSACTION_STATUS_RATE_LIMIT` (default `60 per minute`)
  - `PUBLIC_TRANSACTION_QR_RATE_LIMIT` (default `30 per minute`)
  - `PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT` (default `20 per minute`)

Env terkait prefix invoice:
- `MIDTRANS_ORDER_ID_PREFIX` → prefix order_id untuk transaksi user (beli paket).
- `ADMIN_BILL_ORDER_ID_PREFIX` → prefix order_id untuk tagihan yang dibuat admin.

Dokumen rujukan:
- `docs/TRANSACTIONS_MIDTRANS_LIFECYCLE.md`
- `docs/MIDTRANS_SNAP.md`

## 4) File Environment
Siapkan file environment berikut:
- Root env (dipakai juga oleh frontend container):
  - `.env.public` untuk development
  - `.env.public.prod` untuk production

- Root `.env` (compose-only): hanya untuk interpolation Compose (DB_*, token tunnel)
- Backend (compose):
  - Mengambil public URL dari `.env.public`.
  - DB connection diambil dari `.env` (DB_* -> DATABASE_URL via docker-compose.yml)
  - `backend/.env.local` opsional untuk override/secrets.
- Frontend (compose):
  - `.env.public` (dev)
  - `.env.public.prod` (prod)

Catatan: file `frontend/.env.*` hanya relevan jika menjalankan Nuxt **di luar** Docker (opsional).

### 4.1) Peta Env (Dev vs Prod)

| Lingkungan | File | Dipakai oleh | Isi utama |
|---|---|---|---|
| Dev | `.env` | Docker Compose interpolation | `DB_NAME/DB_USER/DB_PASSWORD`, token tunnel (opsional) |
| Dev | `.env.public` | `frontend`, `backend`, `celery_*` (via `env_file`) | URL dev (`dev-lpsaring...`), `CORS_*`, `NUXT_PUBLIC_*` |
| Dev (opsional) | `backend/.env.local` | backend loader (override) | secrets/override lokal (jangan commit) |
| Prod | `.env.prod` | compose `--env-file`, backend/celery `env_file` + mount `/app/.env` | semua runtime produksi (DB, secrets, URL prod, Mikrotik, Midtrans, WA) |
| Prod | `.env.public.prod` | `frontend` (via `env_file`) | `NUXT_PUBLIC_*` + URL prod |

Template tersedia di:
- .env.example
- .env.public.example
- .env.public.prod.example
- backend/.env.public.example
- backend/.env.local.example
- backend/.env.example
- frontend/.env.public.example
- frontend/.env.local.example
- frontend/.env.example

Catatan penting (loader backend):
- Backend sekarang dapat memuat beberapa file env secara berurutan (overlay). Urutan umumnya:
  - base: `.env` (root) untuk kebutuhan minimal Compose dan/atau file mount `/app/.env`
  - dev: hanya dari `backend/.env.public` → `backend/.env.local` (local override public)
  - prod: hanya `.env` / `.env.prod` (tidak memuat root `.env.public` agar tidak tercampur dengan env frontend)
- Environment yang sudah diset oleh Docker/OS **tidak ditimpa** oleh file `.env` (Docker env wins).

Catatan dev:
- Hindari menyetel `FLASK_ENV=production` di `backend/.env.public` / `backend/.env.local` saat development, karena backend akan menganggap mode produksi.

Lampiran wajib untuk setiap pembaruan dokumen:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

### Minimal yang perlu diisi
Root .env
- DB_NAME
- DB_USER
- DB_PASSWORD
- CLOUDFLARED_TUNNEL_TOKEN (wajib; dipakai service `cloudflared` di Docker Compose)

Root .env.public (frontend dev profile)
- NUXT_PUBLIC_* (lihat `.env.public.example`)

Root .env.prod (production)
- POSTGRES_DB
- POSTGRES_USER
- POSTGRES_PASSWORD
- DATABASE_URL
- SECRET_KEY, JWT_SECRET_KEY, dan config backend lainnya (lihat `.env.prod.example`)

Root .env.public.prod (frontend prod profile)
- NUXT_PUBLIC_* (lihat `.env.public.prod.example`)

backend/.env.public (dev public, tanpa secret)
- APP_PUBLIC_BASE_URL / FRONTEND_URL / CORS_* / APP_LINK_*
- PROXYFIX_* dan TRUSTED_PROXY_CIDRS (jika di belakang proxy)

backend/.env.local (dev lokal, berisi secret)
- DATABASE_URL atau DB_* fallback
- SECRET_KEY, JWT_SECRET_KEY
- MIDTRANS_* / WHATSAPP_* / MIKROTIK_* (sesuai kebutuhan)

frontend/.env.public + frontend/.env.local (opsional, jika Nuxt jalan di host)
- NUXT_PUBLIC_* dan NUXT_INTERNAL_API_BASE_URL

## 5) Menjalankan via Docker Compose (Disarankan)
Mode dev default: semua service utama berjalan via Docker Compose (**backend + db + redis + frontend + nginx**).

Langkah umum:
1) Salin file .env dari template
2) Jalankan stack Docker
3) Akses aplikasi via Nginx

Catatan environment (dev):
- Jika butuh secrets/override untuk backend, buat `backend/.env.local` (jangan commit).

Catatan environment (prod):
- Jalankan compose prod: `docker compose -f docker-compose.prod.yml up -d`.
- Pastikan `.env.public.prod` ada agar container frontend mendapat runtime config public.
- Cloudflared dijalankan di Docker (dev & prod). Pastikan `CLOUDFLARED_TUNNEL_TOKEN` ada di root `.env` pada mesin yang menjalankan compose.

Catatan penting:
- Jangan jalankan prod compose dengan `--env-file .env.prod` karena `.env.prod` adalah runtime env_file untuk container, bukan file interpolation untuk compose.

Konvensi yang disarankan:
- PRODUKSI: gunakan root `.env.prod` (dipakai compose prod dan dimount ke backend sebagai `/app/.env`).
- DEVELOPMENT: gunakan root `.env` (DB_*) + root `.env.public` (public URL + NUXT_PUBLIC_*) untuk menjalankan stack.
  - `backend/.env.local` opsional untuk override/secrets saat dibutuhkan (jangan commit).

Catatan:
- Backend dan Celery akan bergantung pada Postgres & Redis
- Nginx mengarah ke /api → backend:5010, dan / → frontend:3010
- Kuota disinkronkan dari MikroTik dengan delta per-MAC dan pembulatan MB konsisten.
- Pytest backend memakai fallback sqlite in-memory saat env DB belum tersedia.

### 5.1) Menjalankan (Dev)
1) Siapkan file env (development)
- Salin template berikut:
  - `.env.example` -> `.env` (Compose-only)
  - `.env.public.example` -> `.env.public` (frontend container, dev public)
  - (Opsional) `backend/.env.local.example` -> `backend/.env.local` (secrets/local override)

2) Jalankan stack Docker:
- `docker compose up -d`

3) Akses aplikasi:
- `http://localhost` (via Nginx)

### 5.1.1) Mode Dev (Mount backend, tanpa rebuild)
Jika ingin perubahan kode backend langsung terbaca tanpa `docker compose ... --build`, gunakan override compose:
- Jalankan:
  - `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`

Catatan:
- Override ini me-mount `./backend:/app` dan menjalankan gunicorn dengan `--reload` (polling) agar cocok untuk Docker Desktop Windows.
- Celery worker/beat tidak auto-reload; restart container jika ada perubahan kode yang dipakai worker/beat.

### 5.2) Operasional Harian
Log Docker:
- `docker compose logs -f backend`
- `docker compose logs -f nginx`

Restart Docker setelah perubahan konfigurasi/env:
- `docker compose up -d`

Uji cepat setelah perubahan keamanan:
- `docker compose exec -T backend pytest`
- `docker compose exec -T backend ruff check .`

### 5.2.1) One-command refresh lockfile + validasi

Untuk maintenance dependency backend yang konsisten, gunakan script berikut dari folder `backend/`:

- Refresh lockfile + cek sinkronisasi + jalankan regresi targeted:
  - `python scripts/refresh_lock_and_validate.py`

- Refresh lockfile + cek sinkronisasi saja (tanpa test):
  - `python scripts/refresh_lock_and_validate.py --skip-tests`

Script ini menjalankan urutan:
1. `pip freeze` -> `requirements.lock.txt`
2. checker sinkronisasi `requirements.txt` vs `requirements.lock.txt`
3. regresi targeted transaksi + auth OTP (opsional)

Catatan CSRF mode ketat (dev/staging):
- Set `CSRF_STRICT_NO_ORIGIN=True`.
- Isi `CSRF_NO_ORIGIN_ALLOWED_IPS` dengan IP non-browser dan CIDR Docker (contoh `172.16.0.0/12`).

Lint frontend (source of truth, di container):
- `docker compose exec frontend pnpm run lint`

Catatan VS Code (opsional):
- Boleh `pnpm install` di host (folder `frontend/`) agar TypeScript/Vue terbaca tanpa error di editor.
- Ini tidak menggantikan lint/typecheck/test di container.

Lint backend (di container):
- `docker compose exec -T backend ruff check .`

Clear cache Nuxt/Vite:
- Jika Nuxt jalan di host (opsional): `rm -rf .nuxt .output .nitro node_modules/.vite`
- Jika Nuxt jalan di Docker (default): restart container `frontend` (atau rebuild jika perlu)

Jika muncul error seperti "Failed to load module script" pada `icons.css`:
- Pastikan service `frontend` yang melayani `/\_nuxt/*` benar-benar hidup dan Nginx mem-proxy ke `frontend:3010`.
- Pastikan skema HMR (`ws`/`wss`) sesuai dengan skema halaman.

Rebuild image (jika perlu):
- `docker compose up -d --build`
- Recreate build (paksa container baru): `docker compose up -d --build --force-recreate`

### 5.2.1) Catatan Performa Frontend
- ApexCharts di-load secara async dan hanya dipakai di halaman chart.
- Dependensi berat yang tidak dipakai (Tiptap, Chart.js) dihapus.
- Gunakan build analyze untuk memantau ukuran bundle:
  - `pnpm nuxi build --analyze`

Catatan HTTPS + HMR:
- Skema **harus konsisten**: jika akses lewat HTTPS, set `NUXT_PUBLIC_*` ke `https://` dan `NUXT_PUBLIC_HMR_PROTOCOL=wss`.
- Mixed Content akan muncul jika halaman HTTPS mencoba HMR ke `ws://`.
- Jika menjalankan Nuxt di host (opsional) dan HMR menuju `ws://localhost:5173`, biasanya dev server tidak memuat `.env.public`.
- Untuk mode HTTPS via Cloudflare Tunnel, origin tetap HTTP di Nginx, tetapi header `X-Forwarded-Proto` dipakai agar backend mengetahui skema HTTPS.
- Pastikan backend `.env.public` memakai URL `https://` agar CORS dan link konsisten.

### 5.3) Build Image di GitHub Actions
Workflow publish image ada di `.github/workflows/docker-publish.yml`.

### 5.3.0) Kebijakan Build Frontend (CI vs Lokal)

Kebijakan yang dipakai sekarang:
- Lokal (dev harian): **tidak wajib** `pnpm run build` setiap perubahan.
  - Fokus ke `lint + typecheck + focused tests + E2E isolated`.
- CI Pull Request:
  - Build frontend **kondisional** (hanya saat ada perubahan runtime-critical frontend).
- CI Push ke `main`:
  - Build frontend **selalu jalan** sebagai final safety gate sebelum rilis lanjutan.

Perubahan yang dianggap runtime-critical (contoh):
- `frontend/pages/**`, `frontend/components/**`, `frontend/layouts/**`
- `frontend/middleware/**`, `frontend/plugins/**`, `frontend/store/**`
- `frontend/composables/**`, `frontend/utils/**`, `frontend/types/**`
- `frontend/app.vue`, `frontend/nuxt.config.ts`, `frontend/package.json`, `frontend/pnpm-lock.yaml`

Catatan:
- Jika ragu apakah perubahan memengaruhi runtime, jalankan build.
- E2E lokal tetap penting untuk validasi flow bisnis, tetapi tidak menggantikan build gate di CI `main`.

Perilaku workflow:
- Push ke `main`: build + push image backend/frontend ke Docker Hub.
- Push tag `v*`: build + push image dengan tag versi.
- Manual `workflow_dispatch`: bisa pilih deploy ke self-hosted runner (`deploy=true`).

Secrets yang wajib di GitHub repository:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Catatan operasional:
- Deploy ke Raspberry Pi **tidak otomatis** saat push; hanya berjalan saat manual dispatch dengan `deploy=true`.
- Untuk menjalankan produksi + cloudflared: `docker compose -f docker-compose.prod.yml up -d`.
- Jika tidak butuh HMR, pakai build produksi dan akses via Nginx/Cloudflare.

### 5.3.1) Alur Publish & Deploy (yang aktif saat ini)

1. Developer push ke `main`.
2. Workflow `Docker Publish & Optional Deploy` menjalankan matrix build:
  - backend (`babahdigital/sobigidul_backend`) untuk `linux/amd64,linux/arm64`
  - frontend (`babahdigital/sobigidul_frontend`) untuk `linux/amd64,linux/arm64`
3. Jika semua build-and-push sukses, image terbaru tersedia di Docker Hub.
4. Deploy ke Raspberry Pi berjalan **hanya** saat `workflow_dispatch` dengan `deploy=true`.
5. Job deploy di runner Pi menjalankan:
  - `docker compose ... down --remove-orphans`
  - `docker compose ... pull`
  - `docker compose ... up -d --remove-orphans`

Referensi rinci:
- `docs/PUBLISH_FLOW_AND_ERROR_STATUS.md`
- `docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md`

### 5.3.2) Status Error Terkini (2026-02-15)

Error CI yang masih berulang pada job frontend:

```text
buildx failed with: ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons --if-present && pnpm run build" did not complete successfully: exit code: 1
```

Error runtime browser yang sempat muncul:

```text
Uncaught ReferenceError: Cannot access 'ee' before initialization
```

Yang sudah dilakukan:
- Hardening Dockerfile/frontend publish arm64.
- Perbaikan deploy path + env-file pada runner Raspberry Pi.
- Pembersihan pre-deploy yang bisa dikonfigurasi.
- Mitigasi bundling frontend dengan menghapus custom `manualChunks` agar kembali ke strategi default.

Kesimpulan sementara:
- Mitigasi runtime sudah diterapkan di kode.
- Kegagalan CI frontend build masih perlu observasi log rinci per run karena pesan akhir masih generik (`exit code: 1`).

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
- `pnpm install` di **host** hanya opsional untuk kebutuhan VS Code (TypeScript/Vue terbaca, IntelliSense, dan mengurangi false error di editor).
  - Ini **bukan** cara menjalankan aplikasi.
- Workflow utama tetap di Docker:
  - Runtime: frontend/backend selalu jalan di container.
  - Lint/typecheck/test yang jadi acuan tetap dijalankan di container.

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
- Semua env harus lewat profile yang benar:
  - Root `.env` (Compose-only)
  - Root `.env.public*` (frontend container)
  - `backend/.env.public` + `backend/.env.local` (backend)

## 5.5) Testing (Pytest)
- Pytest backend memakai fallback `sqlite:///:memory:` saat env DB belum tersedia (khusus testing).
- Jika ingin konek database nyata, set `DATABASE_URL` atau `TEST_DATABASE_URL`.

## 5.6) Catatan Keamanan Runtime
- `/api/health` selalu mengembalikan HTTP 200 dengan status `ok`/`degraded` agar portal tidak dianggap down ketika satu dependency tidak sehat.
- Autentikasi berbasis cookie memakai pemeriksaan origin untuk request non-GET/HEAD/OPTIONS.
  - Atur `CSRF_PROTECT_ENABLED` dan `CSRF_TRUSTED_ORIGINS` di `.env.prod` (produksi) atau `backend/.env.local` (dev) sesuai domain portal.

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
1. Buat tunnel baru di Dashboard Cloudflare Zero Trust.
2. Buat Public Hostname (contoh `dev-lpsaring.babahdigital.net`) mengarah ke origin `http://hotspot_nginx_proxy:80`.

### B) Token (wajib)
Simpan token tunnel di root `.env` (file ini khusus untuk Docker Compose interpolation dan sudah di-ignore git):
- `CLOUDFLARED_TUNNEL_TOKEN=<TOKEN_DARI_CLOUDFLARE_ZERO_TRUST>`

### C) Jalankan (cloudflared tetap di Docker)
- Dev: `docker compose up -d`
- Prod: `docker compose -f docker-compose.prod.yml up -d`

Untuk runtime URL aplikasi (development), set di:
- `.env.public` (frontend/Nuxt): `NUXT_PUBLIC_APP_BASE_URL=https://dev-lpsaring.babahdigital.net`
- `backend/.env.public` (backend): `APP_PUBLIC_BASE_URL=https://dev-lpsaring.babahdigital.net` dan `FRONTEND_URL=https://dev-lpsaring.babahdigital.net`

### D) Verifikasi HTTPS
1. Pastikan DNS `dev-lpsaring.babahdigital.net` sudah **CNAME** ke tunnel.
2. Jalankan stack + cloudflared.
3. Cek:
  - `https://dev-lpsaring.babahdigital.net/`
  - `https://dev-lpsaring.babahdigital.net/api/ping`

  ## 10) Ringkasan Pekerjaan & Masalah (Sesi Ini)
  Bagian ini merangkum perubahan yang sudah dilakukan, masalah yang muncul, dan bagaimana cara menyelesaikannya.

  ### 10.1) Perubahan yang Dilakukan
  - Tambah setup frontend testing: Vitest config, smoke test util formatters, dan script `test` + `test:watch`.
  - Perbaikan derivasi HMR di Nuxt agar mengikuti `NUXT_PUBLIC_APP_BASE_URL` (HTTP -> `ws`, HTTPS -> `wss`).
  - Rapikan UI halaman `/login` dan `/captive` agar konsisten dengan layout auth Vuetify.
  - Dokumentasi development diperbarui dan checklist testing.
  - Penyesuaian `.env` untuk mode lokal (HTTP, `localhost`/`lpsaring.local`).

  ### 10.2) Masalah yang Dihadapi
  - 504 saat memuat asset Nuxt/Vite (`/_nuxt/*`).
  - HMR gagal karena browser mencoba `wss://` saat akses HTTP.
  - Frontend host mencoba akses `http://backend:5010` (DNS `backend` tidak resolvable di host).
  - MIME type CSS/JS salah (HTML), akibat upstream `/_nuxt` gagal.
  - Port 3010 sempat dipakai proses lain.

  ### 10.3) Penyelesaian
  - Konfigurasi HMR mengikuti `NUXT_PUBLIC_APP_BASE_URL` dan `.env.local` (HTTP -> `ws`).
  - Bersihkan cache Nuxt/Vite (`.nuxt`, `.output`, `.vite`) saat perlu.
  - Hentikan proses pemakai port 3010 dan restart dev server.

  ### 10.4) Catatan Verifikasi
  - Cek `_nuxt` dari host: `curl -I http://localhost:3010/_nuxt/`.
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
1) Walled‑Garden allow **dst-address=IP portal** (contoh 10.0.0.6) dan/atau **dst-host=dev-lpsaring.babahdigital.net**.
2) Pastikan akses portal pakai **http://IP/captive** (hindari HTTPS).
3) Pastikan file `login.html` di MikroTik sudah versi terbaru.

### Catatan Log (terbaru)
- Backend: reload worker karena perubahan file (normal pada mode dev).
- Nginx: warning IPv6 conf read-only saat entrypoint (umum pada image nginx).
- Frontend: peringatan Vue Router untuk path Chrome DevTools (aman diabaikan).

## 12) Cara Menjalankan Full Test & Simulasi
Full test otomatis menggunakan kombinasi test backend + verifikasi endpoint utama.

### 12.1 Prasyarat
- Docker Desktop aktif.
- File environment sudah diisi:
  - Root `.env` (Compose-only: DB_*)
  - Root `.env.public` (dev public URL + `NUXT_PUBLIC_*`)
  - (Opsional) `backend/.env.local` jika butuh secrets/override lokal

Catatan:
- WhatsApp gateway dan MikroTik API bersifat opsional; jika belum dikonfigurasi, jalankan simulasi dengan `-CleanupAddressList:$false`.

### 12.2 Menjalankan Full Test (Windows / PowerShell)
Jalankan dari root proyek:
- `docker compose up -d`
- `docker compose exec -T backend pytest`

Menjalankan simulasi end-to-end (disarankan):

- Mode aman (isolated, tidak mengganggu stack dev yang melayani `dev-lpsaring...`):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\simulate_end_to_end.ps1 -UseIsolatedCompose $true -FreshStart $true -CleanupAddressList $false -RunKomandanFlow $false`
  - Script akan menjalankan stack E2E terpisah via `docker-compose.e2e.yml` dan otomatis memakai `BaseUrl=http://localhost:8088` jika `-BaseUrl` tidak diisi.

- Mode legacy (TIDAK disarankan; memakai stack dev yang sama):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\simulate_end_to_end.ps1 -UseIsolatedCompose $false -BaseUrl http://localhost -FreshStart $true -CleanupAddressList $false -RunKomandanFlow $false`

Catatan parameter boolean:
- Bisa pakai `$true/$false` (PowerShell) atau `1/0` (mis. saat dipanggil dari shell lain).

Jika perlu menyesuaikan URL atau nomor:
- `curl -I http://localhost:8088`

Catatan domain `dev-lpsaring.babahdigital.net`:
- Domain itu biasanya di-serve melalui Cloudflare Tunnel dari stack dev.
- Saat E2E berjalan di mode isolated, ia tidak (dan sebaiknya tidak) mengambil alih tunnel/domain tersebut.

Parameter yang sering disesuaikan:
- `BaseUrl`: basis URL untuk API dan frontend (script akan memisahkan API vs frontend jika perlu).
- `SimulatedClientIp`, `SimulatedClientMac`: identitas user utama.
- `SimulatedKomandanIp`: IP khusus Komandan (mencegah kontaminasi binding).
- `RunKomandanFlow`: set `false` untuk melewati flow Komandan.
- `FreshStart`: reset DB + volume sebelum simulasi.
- `CleanupAddressList`: bersihkan address-list untuk IP simulasi.

### 12.3 Alur Verifikasi Full Test
1) Menyalakan container (db, redis, backend, celery, frontend, nginx).
2) Menunggu backend siap (`/api/ping`) dan frontend siap (`/`).
3) Menjalankan migrasi database (`flask db upgrade`) bila diperlukan.
4) Menjalankan test backend (`pytest`) dan lint backend (`ruff check`).
5) Menjalankan lint frontend (source of truth di container): `docker compose exec frontend pnpm run lint`.
6) Verifikasi endpoint utama melalui Nginx (`/`, `/api/ping`, captive path).

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
