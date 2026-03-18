# Incident 2026-03-19: Deploy dari Image Stale — Commit Belum Di-push

**Severity:** Medium (fitur baru tidak muncul; tidak ada data loss / downtime)
**Status:** Resolved
**Duration:** ~3 deploy cycle (~45 menit) sebelum root cause ditemukan

---

## Ringkasan

Tiga kali deploy berturut-turut (`130edd30`, `c36e9310`, `e6358ee3` — dua di antaranya sudah
digabung dalam satu sesi) tidak menampilkan perubahan di browser meskipun containers sudah
di-recreate dan health check hijau. User melaporkan UI masih sama walaupun incognito + Cloudflare
cache sudah dibersihkan.

---

## Timeline

| Waktu (UTC) | Event |
|-------------|-------|
| ~02:40 | Commit `130edd30` dibuat secara lokal, `deploy_pi.sh --trigger-build` dipanggil |
| ~02:55 | GitHub Actions Build Run `23261377246` — success; deploy selesai, health OK |
| ~03:05 | User melaporkan tidak ada perubahan; incognito + CF cache clear — masih sama |
| ~03:10 | Commit `c36e9310` dibuat secara lokal, `deploy_pi.sh --trigger-build` dipanggil |
| ~03:25 | Build Run `23262461615` — success; kedua migration jalan; health OK |
| ~03:30 | Masih tidak ada perubahan di browser |
| ~03:35 | `git log origin/main..HEAD` menunjukkan **2 commit belum di-push ke remote** |
| ~03:36 | `git push origin main` — push `ee2f67a6..c36e9310` ke GitHub |
| ~03:36 | `deploy_pi.sh --trigger-build` dipanggil lagi |
| ~03:52 | Build Run `23263057076` — berhasil build dari kode yang benar |
| ~04:00 | Perubahan terlihat di browser; deployment verified |

---

## Root Cause

`deploy_pi.sh --trigger-build` memanggil:
```bash
gh workflow run docker-publish.yml --field clean_before_deploy=true
```

GitHub Actions workflow meng-checkout **`origin/main`** — bukan kode lokal. Karena dua commit
(`130edd30` dan `c36e9310`) belum pernah di-push ke remote, workflow membangun image dari
commit terakhir yang ada di GitHub (`ee2f67a6`), yaitu commit sebelumnya.

Deploy script **tidak otomatis melakukan `git push`** sebelum trigger build.

---

## Impact

- Tiga build + deploy menggunakan image lama dari `ee2f67a6`
- Migration `20260319_add_price_rp_to_user_quota_debts` dan `20260319_c_populate_null_due_dates`
  **tidak** dijalankan di production selama durasi insiden
- Fitur harga aktual, jatuh tempo otomatis, paket unlimited tidak aktif selama ~45 menit
- **Tidak ada data loss** — DB dalam kondisi konsisten dengan kode yang benar-benar ter-deploy

---

## Resolution

```bash
# Cek commit yang belum di-push:
git log --oneline origin/main..HEAD

# Push ke remote dulu:
git push origin main

# Baru trigger build:
bash deploy_pi.sh --trigger-build
```

---

## Lessons Learned

1. **`git push` WAJIB dilakukan sebelum `--trigger-build`** — ini sekarang didokumentasikan
   sebagai peringatan di MEMORY.md dan PRODUCTION_OPERATIONS.md.
2. Indikator insiden ini bukan error deploy — health check tetap hijau karena containers
   berjalan dengan image lama yang valid. Hanya `CURRENT_REV` di alembic output yang bisa
   menjadi clue (kita lihat `20260318_*` padahal seharusnya `20260319_*`).
3. Browser cache bukan penyebab — Cloudflare cache clear + incognito tidak membantu karena
   masalah ada di server (image lama), bukan di client.

---

## Guardrail yang Ditambahkan

`MEMORY.md` dan `docs/workflows/PRODUCTION_OPERATIONS.md` diperbarui dengan peringatan eksplisit:

```
PERINGATAN: Selalu `git push origin main` DULU sebelum `--trigger-build`.
GitHub Actions build image dari `origin/main` di GitHub, bukan dari commit lokal.
```

Pertimbangan future: tambah step `git push` otomatis di `deploy_pi.sh --trigger-build` sebelum
memanggil `gh workflow run`.
