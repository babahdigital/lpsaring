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

## 3) Update Status CI/CD (2026-03-08 — Sesi 3)

### Incident CI: Test Mock sessionStorage vs localStorage

Setelah perubahan `sessionStorage → localStorage` di `hotspotIdentity.ts`, CI gagal pada dua run:

| Run | Status | Root Cause |
|-----|--------|------------|
| `22810572908` | failed | `hotspot-identity.test.ts` masih mock `sessionStorage`, code pakai `localStorage` |
| `22810720221` | failed | sama — test "falls back to referrer" dan "falls back to stored" return empty |

Perbaikan: update test stub di `frontend/tests/hotspot-identity.test.ts`:
- `createSessionStorageMock` → `createStorageMock`
- `vi.stubGlobal('sessionStorage')` → `vi.stubGlobal('localStorage')`
- referensi `sessionStorage.getItem/setItem` di TTL test → `localStorage.getItem/setItem`

| Run | Status | Durasi |
|-----|--------|--------|
| `22811056993` | success | 3m17s, 85 tests |
| `22811117603` (Docker Publish) | success | 1m, cache hits |
| `22811351669` (post log retention) | success | docker-build only |

### Deploy Produksi Sesi 3

- Deploy pertama: semua container recreated, healthy, Backend readiness OK, Frontend readiness OK
- Deploy kedua (`--skip-pull`, log retention only): semua 4 container recreated dengan logging config baru, health check OK

**Commit yang masuk sesi ini:**
- `bd306bab` — localStorage + SQL cartesian fix
- `37623f06` — Pydantic v2 + ESLint guard
- `8aca7b64` — deploy_pi.sh targeted container rm
- `5abe94f8` — test localStorage mock fix (CI fix)
- `f172d6b3` — Docker log retention

## 4) Update Status CI/CD (2026-03-08 — Sesi 1 & 2)

Eksekusi terbaru sebelum sesi 3:
- Commit patch utama: `5244d65d`
- CI pertama: run `22805547615` -> `failed`
- Root cause: test backend lama belum selaras policy baru (cleanup host tidak lagi unconditional).
- Commit perbaikan test: `2909337a`
- CI rerun: run `22805668426` -> `success`
- Docker publish manual rerun: run `22805671558` -> `success`

Kesimpulan:
- Pipeline sudah kembali hijau setelah alignment test policy unauthorized recovery.
- Publish image manual untuk commit terbaru telah selesai tanpa error.

## 5) Status Error Operasional Terbaru (2026-03-08 Sesi 3)

Snapshot verifikasi produksi pasca deploy sesi 3:
- App stack: semua 6 container `Up` dan `healthy` (backend, celery_worker, celery_beat, frontend, postgres, redis).
- Server: 63% RAM, 25% disk, uptime 4d17h
- Health endpoint publik:
   - `/api/ping` -> `200 pong`
   - `/login` -> `200`
   - `_nuxt` asset -> loadable
- Scan log backend/celery (post-deploy):
   - `error_level_count=0`
   - `traceback_count=0`
   - Celery: 123 hosts, 27 blocked, 45 authorized, 0 failed
- Log Nginx: hanya 2 errors pada window deploy (01:19), none setelahnya
- SSL cert: valid sampai 9 Mei 2026
- Score kesiapan sistem: **97/100**

Catatan residual anomaly:
- `global-cloudflared` masih menunjukkan event intermiten `context canceled` (36 hits per 6 jam snapshot sebelumnya).
- Dampak: belum ada indikasi error berantai di backend/celery maupun 5xx Nginx.

**Log retention aktif mulai sesi ini:** Semua 4 service runtime menyimpan log di `json-file` (50m×5=250MB per service). Investigasi outage berikutnya bisa dilakukan via `docker logs <container> --since <ts>`.

## 6) Simulasi Produksi Non-Destruktif

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

## 7) Referensi

- `docs/DO_PRODUCTION_DEPLOYMENT.md`
- `docs/OPERATIONS_COMMAND_STANDARD.md`
- `docs/DEVLOG_2026-03-05.md`
- `docs/DEVLOG_2026-03-08.md`
- `docs/DEVLOG_2026-03-08_MIKROTIK_HARDENING.md`
- `docs/WORKLOG_2026-03-08_INFRA_STABILITY.md`
- `docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md`
