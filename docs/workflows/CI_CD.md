# Workflow CI/CD

Dokumen ini merangkum workflow GitHub Actions yang aktif dan jalur rilis yang diizinkan.

Lampiran wajib:
- [.github/copilot-instructions.md](../../.github/copilot-instructions.md)

## Workflow Aktif

### CI

- File: `.github/workflows/ci.yml`
- Trigger: `push` ke `main`, `pull_request`, dan `workflow_dispatch`
- Fungsi utama:
  - deteksi perubahan path
  - contract gate
  - lint dan test backend
  - lint, typecheck, test, dan build frontend
  - build verification image backend dan frontend

### Docker Publish Images

- File: `.github/workflows/docker-publish.yml`
- Trigger: tag `v*` dan `workflow_dispatch`
- Fungsi utama: build dan push image `backend` serta `frontend` ke Docker Hub.
- Workflow ini tidak melakukan deploy ke produksi.

Troubleshooting manual dispatch dari workspace lokal:

- Jika `gh workflow run` atau `gh api` gagal dengan `wsarecv`, `WinError 10054`, `connection reset`, atau GraphQL/dispatch error serupa, jangan langsung asumsikan workflow rusak.
- Verifikasi dulu `gh auth status -h github.com`; jika token masih sehat dan punya scope `workflow`, curigai jalur jaringan ke `api.github.com`.
- Pada workspace Windows ini, kegagalan seperti itu pernah terbukti berasal dari jalur IPv6/NAT64 `api.github.com` yang reset koneksi, sementara jalur IPv4 tetap sehat.
- Jika gejalanya sama, forcing `api.github.com` ke IPv4 untuk request dispatch/view adalah workaround yang tervalidasi. RCA lengkap: `docs/incidents/2026-03-22-github-actions-dispatch-ipv6-reset.md`.

### Actions Housekeeping

- File: `.github/workflows/actions-housekeeping.yml`
- Trigger: scheduler 6 jam sekali dan `workflow_dispatch`
- Fungsi utama: memangkas workflow runs lama dan cache Actions lama.

## Jalur Rilis Resmi

1. Kerjakan perubahan di branch kerja.
2. Jalankan validasi lokal yang relevan.
3. Buka PR dan tunggu CI hijau.
4. Merge ke `main`.
5. Publish image via tag `v*` atau `workflow_dispatch` bila image baru memang dibutuhkan.
6. Deploy produksi secara manual dengan `deploy_pi.sh` sesuai [docs/workflows/PRODUCTION_OPERATIONS.md](PRODUCTION_OPERATIONS.md).

## Aturan Penting

- Deploy produksi tidak dilakukan otomatis dari GitHub Actions.
- Perubahan endpoint prioritas harus lolos contract gate.
- Perubahan frontend runtime penting akan memicu build frontend; push ke `main` tetap menjalankan build final.
- Dokumentasi yang dipakai automation harus tetap ada dan akurat.

## Saat CI Merah

- Gagal di contract gate: cek OpenAPI, typed contract, dan [docs/API_DETAIL.md](../API_DETAIL.md).
- Gagal di UI standards gate: cek [docs/VUEXY_BASELINE_STRATEGY.md](../VUEXY_BASELINE_STRATEGY.md).
- Gagal di backend atau frontend lint/test: perbaiki kode terlebih dahulu, jangan bypass workflow.

## Saat Manual Trigger Gagal Tapi `gh auth` Sehat

1. pastikan `.github/workflows/*.yml` target memang masih memiliki `workflow_dispatch`,
2. cek `gh auth status -h github.com` untuk memastikan scope `workflow` masih ada,
3. audit konektivitas `api.github.com` per family address bila error mengarah ke `connection reset`,
4. jika IPv6/NAT64 rusak tetapi IPv4 sehat, ulangi dispatch dengan jalur forcing IPv4,
5. setelah dispatch berhasil, cek run terbaru dan pastikan `head_sha` cocok dengan commit target sebelum deploy produksi.