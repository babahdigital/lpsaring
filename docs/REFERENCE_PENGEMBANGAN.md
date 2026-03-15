# Referensi Pengembangan

Dokumen ini merangkum aturan pengembangan aktif, integrasi utama, dan checklist validasi sebelum perubahan dianggap siap.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Jalur Kerja Harian

### Local stack

- Jalankan dev stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
- Lihat log: `docker compose logs -f backend frontend nginx`
- Hentikan stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml down`

### Validasi minimum

- Backend lint: `docker compose exec -T backend ruff check .`
- Frontend lint: `docker compose exec frontend pnpm run lint`
- Frontend typecheck: `docker compose exec frontend pnpm run typecheck`
- Backend tests: `docker compose exec -T backend python -m pytest backend/tests`
- Focused frontend tests auth/payment:
  `docker compose exec frontend pnpm run test -- tests/auth-access.test.ts tests/auth-guards.test.ts tests/access-status-parity.contract.test.ts tests/payment-composables.test.ts tests/payment-status-polling.test.ts`

## Kepemilikan File Env

- Root `.env`: interpolation Compose dan secret lintas service yang tidak dipublikasi.
- Root `.env.public` atau `.env.public.prod`: runtime config publik untuk frontend container.
- Root `.env.prod`: source of truth produksi untuk backend, migrate, Celery, dan Compose produksi.
- `backend/.env.local` dan `backend/.env.public`: overlay dev lokal. Jangan jadikan sumber kebenaran produksi.
- `frontend/.env.*`: hanya dipakai bila Nuxt dijalankan di luar Docker.

Variabel yang paling sensitif terhadap perilaku runtime:

- `APP_PUBLIC_BASE_URL`: URL publik untuk invoice, webhook, dan redirect.
- `IP_BINDING_TYPE_ALLOWED`: default policy hotspot (`regular` atau `bypassed`).
- `REQUIRE_EXPLICIT_DEVICE_AUTH` dan `OTP_AUTO_AUTHORIZE_DEVICE`: aturan otorisasi device baru.
- `DEVICE_AUTO_REPLACE_ENABLED`: auto-replace saat limit device penuh.
- `QUOTA_DEBT_LIMIT_MB`: hard block saat debt mencapai ambang.
- `MIKROTIK_DHCP_STATIC_LEASE_ENABLED` dan `MIKROTIK_DHCP_LEASE_SERVER_NAME`: stabilisasi IP berbasis static lease.

## Policy Produk yang Harus Dijaga

### Auth dan device authorization

- OTP sukses secara default mengotorisasi device aktif ketika `OTP_AUTO_AUTHORIZE_DEVICE=True`.
- Bypass code tidak boleh mengotorisasi device otomatis.
- Jalur self-service bind device tetap melalui `POST /api/users/me/devices/bind-current`.

### Quota dan expiry

- Quota source of truth tetap berada di database.
- Sinkronisasi hotspot usage bersifat monotonic: penurunan counter host dianggap reset router, bukan pengurangan total usage.
- User unlimited tidak boleh membawa debt quota.
- Status akses lintas aplikasi wajib tetap sinkron dengan [docs/ACCESS_STATUS_MATRIX.md](ACCESS_STATUS_MATRIX.md).

### Payment dan transaksi

- Midtrans mendukung mode `snap` dan `core_api`; frontend hanya memuat Snap.js saat benar-benar dibutuhkan.
- Endpoint publik transaksi harus tetap selaras dengan OpenAPI dan typed contract frontend.
- Perubahan alur transaksi atau webhook wajib memperbarui [docs/API_DETAIL.md](API_DETAIL.md) dan [docs/workflows/OPENAPI_CONTRACT.md](workflows/OPENAPI_CONTRACT.md).

## Ringkasan Integrasi

### MikroTik

- Counter utama berasal dari `/ip/hotspot/host`.
- Enforcement device menggunakan `/ip/hotspot/ip-binding` berbasis MAC.
- Enforcement status akses IP menggunakan `/ip/firewall/address-list`.
- Static DHCP lease dipakai hanya jika server pin jelas dan benar.
- Audit atau perbaikan massal produksi mengikuti [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).

### Midtrans

- Backend memakai `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY`, dan `MIDTRANS_IS_PRODUCTION`.
- Frontend memakai `NUXT_PUBLIC_MIDTRANS_CLIENT_KEY`.
- Webhook dan redirect harus berjalan melalui URL publik HTTPS yang valid.

### WhatsApp/Fonnte

- Pengiriman server-side memakai token API di backend.
- Deep link frontend ke WhatsApp admin hanya bergantung pada `NUXT_PUBLIC_ADMIN_WHATSAPP` dan `NUXT_PUBLIC_WHATSAPP_BASE_URL`.
- Jangan pernah menaruh token provider di env publik atau frontend.

## Aturan Saat Mengubah Kode

- Perubahan backend wajib divalidasi dengan lint backend.
- Perubahan frontend wajib divalidasi dengan lint frontend, dan typecheck bila menyentuh TypeScript/Vue.
- Perubahan auth, captive, quota, device, atau payment flow wajib menjalankan focused tests yang relevan.
- Perubahan endpoint prioritas wajib sinkron dengan OpenAPI, typed contract, dan [docs/API_DETAIL.md](API_DETAIL.md).
- Perubahan deploy, backup, atau operasi produksi wajib memperbarui [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).

## Dokumen Pendamping

- [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- [docs/API_DETAIL.md](API_DETAIL.md)
- [docs/VUEXY_BASELINE_STRATEGY.md](VUEXY_BASELINE_STRATEGY.md)
- [docs/workflows/OPENAPI_CONTRACT.md](workflows/OPENAPI_CONTRACT.md)
- [docs/workflows/CI_CD.md](workflows/CI_CD.md)
- [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md)