# Publish Flow & Status Error Terkini

Dokumen ini merangkum alur publish/deploy yang aktif setelah penyederhanaan workflow dan status error operasional terbaru.

## 1) Alur Publish Aktif (2026-03-05)

Workflow image publish:
- File: `.github/workflows/docker-publish.yml`
- Nama workflow: `Docker Publish Images`
- Scope: build + push multi-arch image saja (tanpa job deploy)

Trigger workflow image publish:
- Push tag `v*`
- Manual `workflow_dispatch`

Job aktif:
- `build-and-push` (matrix `backend` + `frontend`, platform `linux/amd64` dan `linux/arm64`)

Kebijakan deploy produksi:
- Deploy tidak otomatis dari GitHub Actions.
- Deploy dilakukan manual via `deploy_pi.sh`.
- Mode operasional aman yang direkomendasikan: `--recreate` (hindari mode destruktif kecuali kebutuhan incident recovery).

## 2) Quality Gate CI

Workflow CI utama:
- File: `.github/workflows/ci.yml`
- Trigger: push ke `main`, pull request, dan manual `workflow_dispatch`
- Fungsi: lint, test, typecheck, contract gate, dan docker build verification.

Kebijakan:
- Gunakan satu jalur CI utama (`ci.yml`) untuk mengurangi noise dan duplikasi status check.

## 3) Update Status CI/CD (2026-03-08)

Eksekusi terbaru:
- Commit patch utama: `5244d65d`
- CI pertama: run `22805547615` -> `failed`
- Root cause: test backend lama belum selaras policy baru (cleanup host tidak lagi unconditional).
- Commit perbaikan test: `2909337a`
- CI rerun: run `22805668426` -> `success`
- Docker publish manual rerun: run `22805671558` -> `success`

Kesimpulan:
- Pipeline sudah kembali hijau setelah alignment test policy unauthorized recovery.
- Publish image manual untuk commit terbaru telah selesai tanpa error.

## 4) Status Error Operasional Terbaru

Snapshot verifikasi produksi terkini:
- App stack `backend/frontend/celery/db/redis` berada pada status `Up` dan `healthy`.
- Health endpoint publik:
   - `/api/ping` -> `200` (`pong`)
   - `/login` -> `200`
- Scan log backend/celery 6 jam:
   - `error_level_count=0`
   - `traceback_count=0`
   - `router_timeout_count=0`
   - `fk_violation_count=0`
- Log aplikasi Nginx:
   - `lpsaring_error.log` kosong pada snapshot ini.
   - Tidak ditemukan 5xx pada window scan operasional.

Catatan residual anomaly:
- `global-cloudflared` masih menunjukkan event intermiten `Incoming request ended abruptly: context canceled`.
- Pada snapshot 6 jam, hit pattern ini terhitung `36`.
- Dampak saat ini: belum ada indikasi error berantai di backend/celery maupun 5xx Nginx untuk periode yang sama.

## 5) Simulasi Produksi Non-Destruktif

Perintah simulasi:
- `flask sync-unauthorized-hosts --dry-run --limit 120` (dijalankan dalam container backend, tanpa apply)

Hasil ringkas:
- `processed_hosts=95`
- `desired_block_ips=30`
- `failed_add_or_refresh=0`
- `failed_remove=0`
- `failed_forced_authorized_remove=0`
- `failed_forced_binding_dhcp_remove=0`

Interpretasi:
- Jalur sinkronisasi unauthorized berjalan dan menghasilkan metrik konsisten tanpa operasi tulis karena mode dry-run.
- Tidak ada error mutasi router yang terdeteksi pada simulasi ini.

## 6) Referensi

- `docs/DO_PRODUCTION_DEPLOYMENT.md`
- `docs/OPERATIONS_COMMAND_STANDARD.md`
- `docs/DEVLOG_2026-03-05.md`
- `docs/DEVLOG_2026-03-08.md`
- `docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md`
