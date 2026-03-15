## lpsaring

Portal hotspot dengan backend Flask dan frontend Nuxt 3.

## Dokumentasi Inti
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [docs/REFERENCE_PENGEMBANGAN.md](docs/REFERENCE_PENGEMBANGAN.md)
- [docs/API_DETAIL.md](docs/API_DETAIL.md)
- [contracts/openapi/openapi.v1.yaml](contracts/openapi/openapi.v1.yaml)
- [docs/ACCESS_STATUS_MATRIX.md](docs/ACCESS_STATUS_MATRIX.md)
- [docs/VUEXY_BASELINE_STRATEGY.md](docs/VUEXY_BASELINE_STRATEGY.md)
- [docs/workflows/OPENAPI_CONTRACT.md](docs/workflows/OPENAPI_CONTRACT.md)
- [docs/workflows/CI_CD.md](docs/workflows/CI_CD.md)
- [docs/workflows/PRODUCTION_OPERATIONS.md](docs/workflows/PRODUCTION_OPERATIONS.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CHANGELOG.md](CHANGELOG.md)

Integrasi Midtrans, Fonnte, dan MikroTik kini diringkas di [docs/REFERENCE_PENGEMBANGAN.md](docs/REFERENCE_PENGEMBANGAN.md).

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
- Detail checklist eksekusi: [docs/REFERENCE_PENGEMBANGAN.md](docs/REFERENCE_PENGEMBANGAN.md).

## Checklist Release Singkat
- 1) Pastikan branch fitur sudah bersih dan CI hijau (lint, test, typecheck; build sesuai policy trigger).
- 2) Buat PR ke `main` lalu merge setelah review.
- 3) Push ke `main` akan memicu workflow CI (`.github/workflows/ci.yml`) sebagai quality gate utama.
- 4) Publish image backend/frontend dilakukan lewat workflow `.github/workflows/docker-publish.yml` (tag `v*` atau `workflow_dispatch`).
- 5) Deploy ke produksi dilakukan manual via `deploy_pi.sh` (mode aman disarankan: `--recreate`, bukan mode destruktif).
- 6) Untuk produksi DigitalOcean, jalankan `nginx` + `cloudflared` pada stack global terpisah (`/home/abdullah/nginx`) dan jalankan app stack di `/home/abdullah/lpsaring/app`.

Kebutuhan GitHub Secrets:
- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`

## Template Env
- `.env.example` (root Compose interpolation only)
- `.env.prod.example` (production runtime: backend + db + celery)
- `.env.public.prod.example` (production frontend public runtime)
- `backend/.env.public.example` (backend dev non-secret)
- `backend/.env.local.example` (backend dev local/secret)
- `backend/.env.example` (backend full template, opsional/legacy)
- `frontend/.env.public.example` (frontend dev profile untuk docker dev)
- `frontend/.env.local.example` (frontend local profile untuk e2e/host-local)

Ringkasan ownership file env dan aturan runtime ada di [docs/REFERENCE_PENGEMBANGAN.md](docs/REFERENCE_PENGEMBANGAN.md).

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

## Remote SSH + DB Compose (VS Code)

- Buka project lewat **Remote-SSH** terlebih dahulu (folder project harus di mesin remote).
- Jalankan task via `Terminal: Run Task` untuk mengurangi error karena beda shell/OS.
- Task yang tersedia di `.vscode/tasks.json`:
	- `DB Dev: Up`
	- `DB Dev: Status`
	- `DB Dev: Logs`
	- `DB Dev: PSQL`
	- `DB Dev: Migrate`
	- `DB Prod: Status`
	- `DB Prod: Logs`
	- `DB Prod: PSQL`
	- `Stack Dev: Restart Backend`
	- `Stack Dev: Healthcheck`
	- `Stack Prod: Restart Backend`
	- `Stack Prod: Healthcheck`
- Untuk mode produksi, pastikan file `.env.prod` sudah ada di host remote.
