# Struktur Proyek (lpsaring)

Dokumen ini menjadi peta singkat repo, runtime, dan lokasi kode yang paling sering disentuh.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Topologi Runtime

- Aplikasi utama terdiri dari backend Flask, worker Celery, Redis, PostgreSQL, dan frontend Nuxt 3.
- Produksi memakai split-stack: app stack berada di `/home/abdullah/lpsaring/app`, sedangkan `global-nginx-proxy` dan `global-cloudflared` berjalan terpisah di `/home/abdullah/nginx`.
- Repositori lokal adalah source of truth. Perubahan produksi harus selalu kembali ke repo dan dideploy ulang secara terkontrol.

## Struktur Root

- `backend/`: API Flask, model SQLAlchemy, Celery task, dan Alembic migration.
- `frontend/`: aplikasi Nuxt 3, composables, store Pinia, halaman admin dan captive.
- `contracts/`: kontrak OpenAPI dan artefak sinkronisasi kontrak lintas FE/BE.
- `infrastructure/`: konfigurasi Nginx dan aset infra pendukung.
- `scripts/`: gate CI, generator kontrak, dan utilitas operasional lokal.
- `docs/`: dokumentasi aktif yang sudah diringkas.

## Backend

- `backend/app/__init__.py`: application factory dan bootstrap extension.
- `backend/app/infrastructure/http/`: blueprint HTTP dan entry route utama.
- `backend/app/infrastructure/http/auth_contexts/`: flow login OTP, auto-login, logout, dan hotspot status.
- `backend/app/infrastructure/http/transactions/`: initiation, webhook, public lookup, invoice, cancel, dan event transaksi.
- `backend/app/infrastructure/http/admin_contexts/`: bounded context admin untuk billing, reports, notifications, backups, dan transaksi.
- `backend/app/infrastructure/db/models/`: model database.
- `backend/app/services/`: service layer, termasuk hotspot sync, notification, settings, payment, dan device management.
- `backend/app/tasks.py`: Celery task periodik dan async work.
- `backend/migrations/`: Alembic revision.

## Frontend

- `frontend/pages/`: route Nuxt untuk login, captive, akun, admin, dan payment.
- `frontend/components/`: komponen presentasional dan card/dialog reusable.
- `frontend/composables/`: helper API, polling, instruksi payment, snackbar, dan auth helpers.
- `frontend/store/`: state auth dan state lintas halaman.
- `frontend/@core/` dan `frontend/@layouts/`: baseline Vuexy yang diadopsi untuk sistem layout, table toolbar, pagination, dan theme.
- `frontend/tests/`: unit test Vitest untuk auth, access policy, dan payment flow.

## Alur Domain Penting

### Auth dan captive portal

- Login utama bergerak dari `frontend/pages/login/` ke `backend/app/infrastructure/http/auth_routes.py`.
- Auto-login, hotspot recheck, dan otorisasi perangkat bergantung pada kombinasi token sesi, identitas MAC, dan state hotspot dari MikroTik.
- Halaman fallback hotspot ada di `frontend/pages/login/hotspot-required.vue` dan `frontend/pages/captive/`.

### Quota dan status akses

- Source of truth quota tetap di database.
- Enforcement jaringan dilakukan melalui sinkronisasi backend ke MikroTik dengan kombinasi ip-binding, address-list, DHCP lease, dan profile hotspot.
- Resolver status akses lintas FE/BE didokumentasikan di [docs/ACCESS_STATUS_MATRIX.md](ACCESS_STATUS_MATRIX.md).

### Payment dan notifikasi

- Midtrans dipakai untuk pembuatan transaksi, token/public status lookup, dan webhook finalisasi.
- WhatsApp/Fonnte dipakai untuk OTP dan notifikasi server-side.
- Detail konfigurasi integrasi diringkas di [docs/REFERENCE_PENGEMBANGAN.md](REFERENCE_PENGEMBANGAN.md).

## Peta Perubahan

- Jika mengubah endpoint: cek `backend/app/infrastructure/http/**`, `contracts/openapi/openapi.v1.yaml`, `frontend/types/api/contracts.ts`, dan [docs/API_DETAIL.md](API_DETAIL.md).
- Jika mengubah policy status akses: cek `backend/app/utils/access_status.py`, `frontend/types/accessStatus.ts`, `frontend/utils/authAccess.ts`, dan [docs/ACCESS_STATUS_MATRIX.md](ACCESS_STATUS_MATRIX.md).
- Jika mengubah UI framework atau pola tabel: cek `frontend/@core/**`, `frontend/@layouts/**`, dan [docs/VUEXY_BASELINE_STRATEGY.md](VUEXY_BASELINE_STRATEGY.md).
- Jika mengubah deploy atau prosedur operasi: cek [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).

## Dokumen Aktif Terkait

- [README.md](../README.md)
- [PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md)
- [DEVELOPMENT.md](../DEVELOPMENT.md)
- [docs/REFERENCE_PENGEMBANGAN.md](REFERENCE_PENGEMBANGAN.md)
- [docs/API_DETAIL.md](API_DETAIL.md)
- [docs/workflows/CI_CD.md](workflows/CI_CD.md)