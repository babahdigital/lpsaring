## lpsaring

Portal hotspot dengan backend Flask dan frontend Nuxt 3.

## Dokumentasi Utama
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [docs/REFERENCE_PENGEMBANGAN.md](docs/REFERENCE_PENGEMBANGAN.md)
- [docs/DEVELOPMENT_REALTIME_QUOTA.md](docs/DEVELOPMENT_REALTIME_QUOTA.md)
- [docs/PRODUCTION_AUDIT.md](docs/PRODUCTION_AUDIT.md)
- [docs/DEVELOPMENT_CHECKLIST.md](docs/DEVELOPMENT_CHECKLIST.md)
- [docs/BACKUP_RESTORE_OPERATIONS.md](docs/BACKUP_RESTORE_OPERATIONS.md)
- [docs/API_OVERVIEW.md](docs/API_OVERVIEW.md)
- [docs/API_DETAIL.md](docs/API_DETAIL.md)
- [contracts/openapi/openapi.v1.yaml](contracts/openapi/openapi.v1.yaml)
- [docs/OPENAPI_CONTRACT_WORKFLOW.md](docs/OPENAPI_CONTRACT_WORKFLOW.md)
- [docs/ACCESS_STATUS_MATRIX.md](docs/ACCESS_STATUS_MATRIX.md)
- [docs/operations/CANONICAL_SPEC.md](docs/operations/CANONICAL_SPEC.md)
- [docs/operations/RUNBOOK_ACTIVE_INDEX.md](docs/operations/RUNBOOK_ACTIVE_INDEX.md)
- [docs/operations/ARCHIVE_HISTORICAL_INDEX.md](docs/operations/ARCHIVE_HISTORICAL_INDEX.md)
- [docs/VUEXY_BASELINE_STRATEGY.md](docs/VUEXY_BASELINE_STRATEGY.md)
- [docs/ERROR_REFERENCE.md](docs/ERROR_REFERENCE.md)
- [docs/TRANSACTIONS_STATE_INVARIANTS.md](docs/TRANSACTIONS_STATE_INVARIANTS.md)
- [docs/OPERATIONAL_API_MATRIX.md](docs/OPERATIONAL_API_MATRIX.md)
- [docs/ENV_FILE_MATRIX.md](docs/ENV_FILE_MATRIX.md)
- [docs/OPERATIONS_COMMAND_STANDARD.md](docs/OPERATIONS_COMMAND_STANDARD.md)
- [docs/PUBLISH_FLOW_AND_ERROR_STATUS.md](docs/PUBLISH_FLOW_AND_ERROR_STATUS.md)
- [docs/OPERATIONS_MIKROTIK_SYNC.md](docs/OPERATIONS_MIKROTIK_SYNC.md)
- [docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md](docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md)
- [docs/TROUBLESHOOTING_HYDRATION.md](docs/TROUBLESHOOTING_HYDRATION.md)
- [docs/UPDATE_PUBLIC_WORKFLOW.md](docs/UPDATE_PUBLIC_WORKFLOW.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CHANGELOG.md](CHANGELOG.md)

## Dokumentasi Integrasi
- [docs/PAYMENTS.md](docs/PAYMENTS.md)
- [docs/MIDTRANS_SNAP.md](docs/MIDTRANS_SNAP.md)
- [docs/TRANSACTIONS_MIDTRANS_LIFECYCLE.md](docs/TRANSACTIONS_MIDTRANS_LIFECYCLE.md)
- [docs/DOKUMENTASI_WHATSAPP_FONNTE.md](docs/DOKUMENTASI_WHATSAPP_FONNTE.md)

## Catatan Singkat
- Registrasi mendukung tamping vs non‑tamping.
- Tamping wajib `tamping_type`, non‑tamping wajib `blok` & `kamar`.

## Catatan Performa Frontend
- ApexCharts di-load secara async (hanya saat chart dipakai).
- Dependensi Tiptap dan Chart.js dihapus karena tidak digunakan.
- Build analyze: `pnpm nuxi build --analyze`.

## Policy Build Frontend (Lokal vs CI)
- Lokal (pre-commit harian): tidak wajib `pnpm run build` di setiap perubahan.
- Jalur cepat wajib: lint + typecheck + focused tests + E2E isolated.
- CI Pull Request: build frontend hanya saat ada perubahan runtime-critical frontend.
- CI push ke `main`: build frontend selalu jalan sebagai final safety gate.
- Detail checklist eksekusi: [docs/DEVELOPMENT_CHECKLIST.md](docs/DEVELOPMENT_CHECKLIST.md).

## Checklist Release Singkat
- 1) Pastikan branch fitur sudah bersih dan CI hijau (lint, test, typecheck; build sesuai policy trigger).
- 2) Buat PR ke `main` lalu merge setelah review.
- 3) Push ke `main` akan memicu publish image backend/frontend via GitHub Actions (`docker-publish.yml`).
- 4) Untuk deploy ke Raspberry Pi, jalankan workflow manual `workflow_dispatch` dengan input `deploy=true`.
- 5) Cloudflare Tunnel dijalankan via Docker Compose; simpan `CLOUDFLARED_TUNNEL_TOKEN` di root `.env` pada mesin yang menjalankan compose.

Kebutuhan GitHub Secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## Template Env
- `.env.example` (root Compose interpolation only)
- `.env.prod.example` (production runtime: backend + db + celery)
- `.env.public.prod.example` (production frontend public runtime)
- `backend/.env.public.example` (backend dev non-secret)
- `backend/.env.local.example` (backend dev local/secret)
- `backend/.env.example` (backend full template, opsional/legacy)
- `frontend/.env.public.example` (frontend dev profile untuk docker dev)
- `frontend/.env.local.example` (frontend local profile untuk e2e/host-local)

Lihat pemetaan lengkap file env per mode di [docs/ENV_FILE_MATRIX.md](docs/ENV_FILE_MATRIX.md).

## Quick Commands (Dev vs E2E)

### Dev (docker compose utama)
- Siapkan env:
	- copy `.env.example` -> `.env`
	- copy `backend/.env.public.example` -> `backend/.env.public`
	- copy `backend/.env.local.example` -> `backend/.env.local`
	- copy `frontend/.env.public.example` -> `frontend/.env.public`
- Jalankan:
	- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
- Akses:
	- Frontend/Nginx: `http://localhost`

### E2E (isolated localhost)
- Siapkan env:
	- pastikan `backend/.env.e2e` ada
	- copy `frontend/.env.local.example` -> `frontend/.env.local`
- Jalankan:
	- `docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e up -d`
- Akses:
	- Frontend/Nginx: `http://localhost:8089`

### Stop & cleanup
- Dev stop: `docker compose -f docker-compose.yml -f docker-compose.dev.yml down`
- E2E stop: `docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e down`
