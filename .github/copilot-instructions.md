# Instruksi Copilot (lpsaring)

## Gambaran Besar
- Portal hotspot dengan backend Flask (API + Celery) dan frontend Nuxt 3/Vuetify.
- Nginx mem-proxy `/api` ke backend dan `/` ke frontend (lihat infrastructure/nginx/conf.d/app.conf).
- Integrasi utama: MikroTik (RouterOS API), Midtrans (Snap), WhatsApp Fonnte.

## Arsitektur & Alur Data Penting
- Auth & captive flow: login/OTP di backend/app/infrastructure/http/auth_routes.py → frontend/pages/captive/ dan frontend/pages/login/.
- Transaksi: backend/app/infrastructure/http/transactions_routes.py → Midtrans Snap → webhook update status → apply paket ke MikroTik.
- WA invoice: Celery task di backend/app/tasks.py mengirim PDF; URL dibangun dari `APP_PUBLIC_BASE_URL`.
- Walled-garden sync: backend/app/services/walled_garden_service.py → MikroTik; host/IP allowlist wajib di-setting.

## Struktur & Alur Kode
- Backend entry: backend/app/__init__.py (factory `create_app()`), route di backend/app/infrastructure/http/, logika bisnis di backend/app/services/.
- Celery task di backend/app/tasks.py; model SQLAlchemy di backend/app/infrastructure/db/models/.
- Frontend: route di frontend/pages/, layout di frontend/layouts/, state di frontend/store/, composables di frontend/composables/.

## Konfigurasi & ENV
- ENV dipisah: root .env (Compose), backend/.env, frontend/.env; template ada di .env.example dan subfolder.
- `APP_PUBLIC_BASE_URL` dipakai untuk URL publik (invoice, webhook), wajib HTTPS saat produksi.
- Settings runtime dibaca lewat `settings_service.get_setting()`; nilai DB kosong akan fallback ke ENV.
- Mode OTP-only memakai `IP_BINDING_TYPE_ALLOWED=bypassed` sebagai default.
- Kuota dihitung dari `/ip/hotspot/host` (counter per MAC) karena bypass tidak menghasilkan sesi `/ip/hotspot/active` untuk user.
- Sinkronisasi kuota bersifat **monotonic** (counter host turun dianggap reset, total tetap akumulatif).
- Statistik harian/mingguan/bulanan mengikuti `APP_TIMEZONE` (default `Asia/Makassar`).
- Auto-enroll perangkat dari `/ip/hotspot/ip-binding` (berdasarkan `comment` berisi `user=<id>`), dibatasi `MAX_DEVICES_PER_USER`.
- Debug auto-enroll per MAC hanya jika `AUTO_ENROLL_DEBUG_LOG=True`.
- Walled-garden host/IP diatur via `WALLED_GARDEN_ALLOWED_HOSTS`/`WALLED_GARDEN_ALLOWED_IPS` dan disinkronkan ke MikroTik.
- Midtrans & WA bergantung pada URL publik; gunakan Cloudflare Tunnel (lihat DEVELOPMENT.md bagian HTTPS).

## Dokumentasi Wajib
- Setiap dokumen teknis yang diperbarui **wajib menyertakan tautan lampiran** ke `.github/copilot-instructions.md` sebagai pondasi pengembangan (dokumen ini tidak perlu melampirkan dirinya sendiri).

## Workflow Dev (Disarankan)
- Jalankan stack: `docker compose up -d`.
- Lihat log: `docker compose logs -f backend|frontend|nginx`.
- Lint backend: `docker compose exec -T backend ruff check .` (config di backend/ruff.toml).
- Lint frontend: `docker compose exec frontend pnpm run lint`.
- Simulasi end-to-end (Windows): jalankan scripts/simulate_end_to_end.ps1.

## Aturan Wajib Saat Mengubah Kode
- Jika mengubah file backend (backend/**), WAJIB jalankan: `docker compose exec -T backend ruff check .`.
- Jika mengubah file frontend (frontend/**), WAJIB jalankan: `docker compose exec frontend pnpm run lint`.
- Jika mengubah keduanya, jalankan kedua lint di atas.
- Semua perintah dev dijalankan di container agar konsisten (lihat DEVELOPMENT.md).
- Setiap perubahan perilaku/flow WAJIB update dokumentasi yang relevan (minimal docs/REFERENCE_PENGEMBANGAN.md dan/atau DEVELOPMENT.md) agar tidak ada kebingungan.

## Konvensi Proyek
- Backend: hindari one-liner control flow; gunakan `is None`/`is not None`, bukan `== None`.
- Frontend: jangan hardcode URL; gunakan runtime config/ENV (`NUXT_PUBLIC_*`).
- Perubahan terkait captive/auto-login ada di backend/app/infrastructure/http/auth_routes.py dan frontend/pages/captive/.

## Contoh Lokasi Kunci
- MikroTik client: backend/app/infrastructure/gateways/mikrotik_client.py.
- Settings & enkripsi: backend/app/services/settings_service.py.
- Walled garden: backend/app/services/walled_garden_service.py.
- Finish payment: frontend/pages/payment/finish.vue.

## Referensi Teknis
- Docs umum: README.md, DEVELOPMENT.md, PROJECT_OVERVIEW.md.
- Integrasi: docs/MIDTRANS_SNAP.md, docs/DOKUMENTASI_WHATSAPP_FONNTE.md.
