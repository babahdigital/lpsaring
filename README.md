## lpsaring

Portal hotspot dengan backend Flask dan frontend Nuxt 3.

## Dokumentasi Utama
- [.github/copilot-instructions.md](.github/copilot-instructions.md)
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
- [docs/ERROR_REFERENCE.md](docs/ERROR_REFERENCE.md)
- [docs/PUBLISH_FLOW_AND_ERROR_STATUS.md](docs/PUBLISH_FLOW_AND_ERROR_STATUS.md)
- [docs/OPERATIONS_MIKROTIK_SYNC.md](docs/OPERATIONS_MIKROTIK_SYNC.md)
- [docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md](docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md)
- [docs/TROUBLESHOOTING_HYDRATION.md](docs/TROUBLESHOOTING_HYDRATION.md)
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

## Checklist Release Singkat
- 1) Pastikan branch fitur sudah bersih dan CI hijau (lint, test, typecheck, build).
- 2) Buat PR ke `main` lalu merge setelah review.
- 3) Push ke `main` akan memicu publish image backend/frontend via GitHub Actions (`docker-publish.yml`).
- 4) Untuk deploy ke Raspberry Pi, jalankan workflow manual `workflow_dispatch` dengan input `deploy=true`.
- 5) Cloudflare Tunnel dijalankan via Docker Compose; simpan `CLOUDFLARED_TUNNEL_TOKEN` di root `.env` pada mesin yang menjalankan compose.

Kebutuhan GitHub Secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## Template Env
- `.env.example` (Compose-only)
- `.env.public.example` (Frontend dev)
- `.env.public.prod.example` (Frontend prod)
- `backend/.env.public.example` (Backend dev public/non-secret)
- `backend/.env.local.example` (Backend dev local/secret)
- `backend/.env.example` (Backend full template, opsional/legacy)
- `frontend/.env.public.example` (Nuxt public template, opsional jika jalan di host)
- `frontend/.env.local.example` (Nuxt local template, opsional jika jalan di host)
- `.env.prod.example` (Production runtime: backend + db + celery)
