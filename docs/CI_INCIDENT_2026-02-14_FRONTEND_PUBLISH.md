# Postmortem CI Frontend Publish (2026-02-14)

Dokumen ini merangkum masalah CI/CD yang terjadi pada pipeline publish frontend, termasuk gejala error, akar masalah, tindakan perbaikan, dan langkah pencegahan.

## Status Terkini (Update 2026-02-15)

- Status umum: **belum sepenuhnya stabil**.
- Gejala CI masih berulang pada job frontend:

```text
buildx failed with: ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons --if-present && pnpm run build" did not complete successfully: exit code: 1
```

- Gejala runtime browser yang sempat muncul:

```text
b0FJU5zQ.js:13 Uncaught ReferenceError: Cannot access 'ee' before initialization
```

- Mitigasi bundling terbaru sudah dicoba:
  - `fix(frontend): reduce risky manual chunk splitting` (`f9e1a13a`)
  - `fix(frontend): remove custom manual chunk splitting` (`2d7dd65b`)
  - `ci: retrigger deploy after frontend chunk fix` (`8128de5c`)
- Hasil: runtime fix sudah diterapkan di kode, namun error CI frontend build masih perlu observasi run berikutnya dengan log yang lebih detail.

## Ringkasan Singkat

- Workflow terdampak: `Docker Publish & Optional Deploy` (`.github/workflows/docker-publish.yml`)
- Job terdampak: `build-and-push (frontend, ./frontend, babahdigital/sobigidul_frontend, linux/amd64,linux/arm64)`
- Dampak: publish image frontend gagal, job deploy otomatis tidak jalan.
- Backend publish tetap sukses pada run yang sama.

## Gejala Utama

Error yang berulang di langkah build frontend:

```text
ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons &&     pnpm run build" did not complete successfully: exit code: 1
Error: buildx failed with: ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons &&     pnpm run build" did not complete successfully: exit code: 1
```

Pada iterasi lain juga muncul warning konfigurasi workflow:

```text
Warning: Unexpected input(s) 'progress', valid inputs are [...]
```

## Timeline Singkat

1. Publish pipeline ditrigger beberapa kali via tag (`v2026.02.14-hotfix-tdz-*`).
2. Pola tetap sama: backend sukses, frontend gagal di build-and-push.
3. Reproduksi lokal dilakukan untuk Docker build frontend.
4. Ditemukan parser error di `frontend/Dockerfile-prod` karena inline comment pada instruction Docker.
5. Setelah parser fix, build lokal `docker build` dan `buildx --platform linux/arm64` sukses.
6. Workflow diperbaiki untuk validasi secret dan tuning build arg.
7. Ditemukan input `progress` tidak valid untuk action version yang digunakan; kemudian dihapus.

## Akar Masalah yang Terkonfirmasi

### 1) Dockerfile parser issue (terkonfirmasi)

Pada `frontend/Dockerfile-prod`, ada inline komentar pada instruction tertentu yang memicu parser strict di buildx environment tertentu.

Contoh pola bermasalah (sebelum diperbaiki):

- `ENV NODE_ENV=production # ...`
- `EXPOSE 3010 # ...`

Status: **sudah diperbaiki** dengan memindahkan komentar ke baris terpisah.

### 2) Workflow input tidak kompatibel (terkonfirmasi)

`docker/build-push-action@v5` tidak menerima input `progress` pada konfigurasi yang dipakai, sehingga menimbulkan warning `Unexpected input(s) 'progress'`.

Status: **sudah diperbaiki** dengan menghapus input `progress`.

### 3) Nuxt build gagal di CI (masih perlu observasi detail lanjut)

Meskipun build lokal sukses, di runner CI sempat tetap terjadi `pnpm run build` exit code 1 pada konteks Docker build.

Mitigasi yang sudah diterapkan:

- Tambah `NODE_OPTIONS=--max-old-space-size=3072` via build arg.
- Validasi keberadaan secret Docker Hub secara eksplisit di workflow.

Status: **mitigasi aktif**, perlu monitor run berikutnya untuk memastikan stabil sepenuhnya.

### 4) Risiko regresi chunk/runtime frontend (terkonfirmasi di browser, mitigasi sudah diterapkan)

Gejala sempat muncul di browser produksi:

```text
Uncaught ReferenceError: Cannot access 'ee' before initialization
```

Analisis:
- Error ini konsisten dengan risiko urutan inisialisasi modul/chunk (TDZ) pada bundle minified.
- Konfigurasi custom chunk splitting meningkatkan risiko mismatch inisialisasi ketika terjadi cache campuran antar aset `_nuxt/*`.

Mitigasi:
- Menghapus pemecahan chunk manual di `frontend/nuxt.config.ts` agar kembali ke strategi default Vite/Nuxt.

Status: **mitigasi sudah aktif di branch `main`**, tetap perlu verifikasi pada run publish + deploy berikutnya.

## Perubahan yang Dilakukan

### File: `frontend/Dockerfile-prod`

- Membersihkan inline comment pada instruction Docker agar parser konsisten.
- Menambah:

```dockerfile
ARG NODE_OPTIONS=--max-old-space-size=3072
ENV NODE_OPTIONS=${NODE_OPTIONS}
```

Tujuan: menurunkan risiko OOM/instabilitas saat `pnpm run build` di CI.

### File: `.github/workflows/docker-publish.yml`

- Menambah step validasi secret Docker Hub:
  - `DOCKERHUB_USERNAME/DOCKERHUB_TOKEN` atau fallback `DOCKER_USERNAME/DOCKER_PASSWORD`.
- Menambah `build-args` untuk `NODE_OPTIONS`.
- Menghapus input `progress` yang tidak didukung action.

## Validasi yang Sudah Dilakukan

1. `pnpm run build:icons` lokal: sukses.
2. `pnpm run build` lokal: sukses.
3. `docker build -f frontend/Dockerfile-prod frontend ...` lokal: sukses.
4. `docker buildx build --platform linux/arm64 ...` lokal: sukses.
5. `nginx -t` untuk perubahan terkait routing prod: sukses (di host target).

## Lessons Learned

1. Jangan gunakan inline comment pada instruction Docker di file produksi; gunakan baris komentar terpisah.
2. Selalu verifikasi kompatibilitas input action terhadap versi action yang dipakai.
3. Pisahkan diagnosis:
   - Error auth/secret (login registry)
   - Error build source (Dockerfile, Nuxt build)
   - Error runtime/deploy
4. Untuk kasus CI-only failure, wajib lakukan reproduksi lokal `buildx` lintas arsitektur agar pembuktian lebih kuat.

## Checklist Pencegahan Ke Depan

- [x] Tambah job `docker build` frontend (no push) di workflow CI utama untuk fail-fast.
- [ ] Gunakan output log build yang konsisten (`plain`) via mekanisme yang kompatibel dengan action version.
- [x] Pertahankan step validasi secret sebelum build-and-push.
- [ ] Dokumentasikan versi `docker/build-push-action` dan input yang didukung pada file workflow.
- [ ] Tambah SOP incident log: run id, job id, commit sha, dan error pertama yang relevan.

## Next Action Operasional

1. Jalankan publish ulang dari commit terbaru (`8128de5c`) dan simpan `run id`.
2. Jika frontend job gagal lagi, ambil log step `Build & push frontend` paling awal yang memuat stack trace asli sebelum ringkasan `exit code: 1`.
3. Cocokkan hasil CI dengan reproduksi lokal:
  - `pnpm run build:icons --if-present && pnpm run build`
  - `docker build -f frontend/Dockerfile-prod frontend`
4. Jika CI-only failure berulang, aktifkan log build lebih verbose pada step frontend untuk satu run investigasi.

## Referensi Internal

- Workflow publish: `.github/workflows/docker-publish.yml`
- Dockerfile frontend prod: `frontend/Dockerfile-prod`
- Dokumen deploy Pi: `docs/DEPLOY_RPI_MINIMAL.md`
