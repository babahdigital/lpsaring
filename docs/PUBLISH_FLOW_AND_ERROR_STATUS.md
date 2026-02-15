# Publish Flow & Status Error Terkini

Dokumen ini merangkum **alur publish/deploy yang aktif**, **perbaikan yang sudah dilakukan**, dan **status error terbaru**.

## 1) Alur Publish Saat Ini

Workflow utama: `.github/workflows/docker-publish.yml` (`Docker Publish & Optional Deploy`).

### Trigger
- Push ke `main`.
- Push tag `v*`.
- Manual `workflow_dispatch`.

### Job 1 — `build-and-push` (ubuntu-latest)
Matrix service:
- backend: `babahdigital/sobigidul_backend`
- frontend: `babahdigital/sobigidul_frontend`

Platform build:
- `linux/amd64`
- `linux/arm64`

Urutan ringkas:
1. Checkout.
2. Setup QEMU + Buildx.
3. Login Docker Hub.
4. Metadata tag image (`latest`, `sha`, `tag`).
5. Build + push image multi-arch.

### Job 2 — `deploy` (self-hosted Pi)
Syarat jalan:
- hanya saat `workflow_dispatch` dengan `deploy=true`.

Urutan ringkas:
1. `down --remove-orphans`
2. `pull`
3. `up -d --remove-orphans`

Lokasi deploy aktif:
- `/home/abdullah/sobigidul`

## 2) Error yang Masih Berulang

### A) CI frontend publish (masih berulang)

```text
buildx failed with: ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons --if-present && pnpm run build" did not complete successfully: exit code: 1
```

Catatan:
- Error ini terjadi pada job matrix frontend.
- Backend di run yang sama bisa sukses.
- Pesan akhir masih generik (`exit code: 1`) sehingga perlu log step yang lebih rinci untuk akar masalah final.

### B) Runtime browser (pernah muncul)

```text
Uncaught ReferenceError: Cannot access 'ee' before initialization
```

Catatan:
- Terkait chunk runtime minified `_nuxt/*` (indikasi risiko urutan inisialisasi/caching campuran).
- Mitigasi sudah diterapkan di kode (lihat bagian perubahan).

## 3) Yang Sudah Kita Lakukan (Ringkas)

Berikut rangkaian perbaikan utama yang sudah masuk:

1. Hardening build frontend arm64 dan pipeline icon.
2. Perbaikan deploy workflow agar memakai direktori runtime Pi yang benar (`/home/abdullah/sobigidul`) dan `--env-file .env.prod`.
3. Penambahan cleanup pre-deploy yang bisa dikonfigurasi (`clean_before_deploy`, `aggressive_cleanup`).
4. Perapihan artifact sementara (`tmp*`, log) + update `.gitignore`.
5. Mitigasi bundling frontend:
   - pengurangan risky chunk split,
   - lalu penghapusan custom `manualChunks` agar kembali ke default Vite/Nuxt.
6. Retrigger pipeline setelah patch frontend chunk.

## 4) Kesimpulan Status

- Alur publish/deploy sudah terdokumentasi dan selaras dengan workflow aktif.
- Runtime chunk mitigation sudah diterapkan di source frontend.
- Error CI frontend publish **masih sama** pada sebagian run (`buildx ... exit code: 1`) dan butuh observasi log detail per-run sampai akar final terkunci.

## 5) Langkah Operasional Selanjutnya

1. Saat run gagal, simpan:
   - `run id`,
   - `job name`,
   - commit SHA,
   - baris error pertama sebelum ringkasan `exit code: 1`.
2. Reproduksi lokal pada commit yang sama:
   - `pnpm run build:icons --if-present && pnpm run build`
   - `docker build -f frontend/Dockerfile-prod frontend`
3. Jika lokal sukses tapi CI gagal, lakukan satu run investigasi dengan log build lebih verbose pada step frontend.

## 6) Referensi

- `docs/CI_INCIDENT_2026-02-14_FRONTEND_PUBLISH.md`
- `docs/ERROR_REFERENCE.md`
- `docs/DEPLOY_RPI_MINIMAL.md`
- `DEVELOPMENT.md`
