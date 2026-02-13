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
- [docs/TROUBLESHOOTING_HYDRATION.md](docs/TROUBLESHOOTING_HYDRATION.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CHANGELOG.md](CHANGELOG.md)

## Dokumentasi Integrasi
- [docs/MIDTRANS_SNAP.md](docs/MIDTRANS_SNAP.md)
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
- 5) Jika butuh tunnel Cloudflare, jalankan compose production dengan profile `tunnel` setelah token valid tersedia.

Kebutuhan GitHub Secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`