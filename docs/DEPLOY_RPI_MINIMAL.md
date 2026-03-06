# Deploy Minimal (App-Only) via deploy_pi.sh

Dokumen ini adalah panduan resmi penggunaan `deploy_pi.sh` yang sudah dikunci untuk deployment **app-only**.

> Catatan penting:
> - Arsitektur produksi memakai split-stack: `global-nginx-proxy` + `global-cloudflared` berjalan terpisah dari app.
> - Script deploy **tidak** boleh menyentuh service global (WireGuard, Cloudflare Tunnel, nginx global, wartelpas stack lain).
> - Jalankan mode detached (`--detach-local`) untuk menghindari kegagalan akibat terminal lokal ter-interrupt (`exit code 130`).

Referensi:
- [DO_PRODUCTION_DEPLOYMENT.md](./DO_PRODUCTION_DEPLOYMENT.md)
- [OPERATIONS_COMMAND_STANDARD.md](./OPERATIONS_COMMAND_STANDARD.md)

## 1) Scope dan Target Wajib

`deploy_pi.sh` sudah dikunci ke target berikut:

- SSH: `ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31`
- Remote app dir: `/home/abdullah/lpsaring/app`

Artinya:
- `--host`, `--user`, `--port`, `--remote-dir` boleh ditulis, tetapi nilainya harus sama dengan target wajib di atas.
- Jika berbeda, script akan **langsung gagal**.
- Script juga memverifikasi arsitektur host harus `x86_64/amd64` dan image app (`backend`/`frontend`) harus `amd64`.

## 2) Perilaku Backup (Wajib, Sebelum Deploy)

Sebelum deploy, script selalu membuat backup **database saja** (bukan tarball) lalu copy ke lokal:

- Lokasi lokal: `../backups` (relatif dari folder `lpsaring`)
- Format file: `<host>_<mode>_predeploy_<timestamp>.sql`

Contoh:
- `../backups/159.89.192.31_deploy_predeploy_YYYYMMDD_HHMMSS.sql`
- `../backups/159.89.192.31_clean_predeploy_YYYYMMDD_HHMMSS.sql`
- `../backups/159.89.192.31_strict_minimal_predeploy_YYYYMMDD_HHMMSS.sql`

Safety guard backup:
- Default minimum ukuran backup: `102400` bytes.
- Untuk mode destruktif (`--clean`/`--strict-minimal`), jika backup lebih kecil dari ambang ini, deploy akan dibatalkan demi keamanan.
- Override hanya jika sadar risikonya: `--allow-small-backup`.
- Ambang bisa diubah: `--min-backup-bytes <BYTES>`.

## 3) Opsi Deploy yang Dipakai

### Mode detached (direkomendasikan)
```bash
./deploy_pi.sh --detach-local --recreate
```

Perilaku:
- Script dijalankan sebagai background lokal (`nohup`) dan tidak bergantung pada sesi terminal aktif.
- Menampilkan PID dan lokasi log `../tmp/deploy_detached_<timestamp>.log`.
- Pantau dengan `tail -f ../tmp/deploy_detached_*.log`.

### Mode normal (default)
```bash
./deploy_pi.sh
```

### Backup saja (tanpa deploy)
```bash
./deploy_pi.sh --backup-only
```

Perilaku:
- Tetap membuat backup DB ke `../backups`.
- Proses berhenti setelah backup selesai.
- Tidak menjalankan prepare/deploy/healthcheck.

### Force recreate container tanpa hapus volume
```bash
./deploy_pi.sh --recreate
```

Catatan penting:
- Saat `--recreate`, script akan tetap melakukan `docker compose pull` untuk service app (`backend`, `frontend`, `celery_worker`, `celery_beat`, `migrate`, `backups_init`) sebelum `up --force-recreate`.
- Kombinasi `--recreate --skip-pull` ditolak oleh script untuk mencegah deploy dengan image lama.

Alias yang diterima:
- `--recreated`
- `--recretaed` (typo alias)

### Clean deploy (tetap app-only)
```bash
./deploy_pi.sh --clean --confirm-clean-data-loss
```

Catatan:
- Menjalankan `docker compose down -v --remove-orphans` untuk stack app di folder app.
- Scope tetap dibatasi ke app dir yang dikunci.
- **Default terbaru:** setelah clean berhasil, data akan dipulihkan lagi dari backup pre-clean (mode preserve-data).
- Jika proses deploy gagal setelah backup, script otomatis mencoba restore DB dari backup lokal run tersebut.

Jika memang ingin clean dengan data benar-benar kosong:
```bash
./deploy_pi.sh --clean --clean-reset-data --confirm-clean-data-loss
```

### Strict minimal deploy (app dir dirapikan)
```bash
./deploy_pi.sh --strict-minimal
```

Catatan:
- Memakai `rm -rf` **hanya** di dalam `/home/abdullah/lpsaring/app`.
- Menjaga `backend/backups` tetap ada.
- Jika proses deploy gagal setelah backup, script otomatis mencoba restore DB dari backup lokal terbaru run tersebut.
- Jika cleanup `backend/backups` gagal karena permission, script akan auto-heal (coba `chown/chmod`, termasuk via `sudo -n` bila tersedia), lalu retry hapus.
- Jika setelah auto-heal masih gagal, script memberi warning non-fatal dan tetap lanjut deploy.

### Jika nginx conf berubah, sinkronkan sekalian
```bash
./deploy_pi.sh --sync-nginx-conf
```

## 4) Opsi yang Diblokir

`--prune` dinonaktifkan (ditolak) demi keamanan.

Alasan:
- `docker prune` bersifat host-wide dan berisiko menyentuh resource service lain di host.
- Kebijakan deploy ini: **app-only, no host-wide destructive ops**.

## 5) Quick Checklist Sebelum Deploy

- Pastikan file lokal tersedia:
  - `docker-compose.prod.yml`
  - `.env.prod`
  - `.env.public.prod` (opsional tapi direkomendasikan)
- Pastikan `.env.prod` tidak berisi `CHANGE_ME_*` (kecuali memang pakai `--allow-placeholders`).
- Pastikan key SSH tersedia: `~/.ssh/id_raspi_ed25519`.

## 6) Health Check Sesudah Deploy

Script melakukan health check otomatis (kecuali `--skip-health`):

- via `global-nginx-proxy`
- endpoint `GET /api/ping`
- halaman `/login`
- satu asset `/_nuxt/...`

Contoh cek manual:

```bash
docker exec global-nginx-proxy wget -T 10 -qO- --header='Host: lpsaring.babahdigital.net' http://127.0.0.1/api/ping
```

## 7) Contoh Alur Aman Harian

### 7.1 Backup cepat sebelum tindakan apa pun
```bash
./deploy_pi.sh --detach-local --backup-only
```

### 7.2 Deploy rutin
```bash
./deploy_pi.sh --detach-local --recreate
```

### 7.3 Deploy + update nginx conf
```bash
./deploy_pi.sh --detach-local --recreate --sync-nginx-conf
```

### 7.4 Kasus reset stack app (tetap preserve data)
```bash
./deploy_pi.sh --detach-local --clean --confirm-clean-data-loss --recreate
```

### 7.5 Kasus rapikan total app dir
```bash
./deploy_pi.sh --detach-local --strict-minimal --recreate
```

### 7.6 Kasus clean dengan reset data (opsional, destruktif)
```bash
./deploy_pi.sh --detach-local --clean --clean-reset-data --confirm-clean-data-loss --recreate
```

## 8) Ringkasan Safety

- Backup DB lokal selalu dibuat sebelum deploy.
- Scope operasi dibatasi ke app dir terkunci.
- `--prune` diblokir untuk mencegah dampak lintas stack.
- `--recreate` tersedia untuk recreate container tanpa hapus volume.
- Guard `--recreate` memastikan image app terbaru tetap dipull (kombinasi dengan `--skip-pull` diblokir).
- `--detach-local` direkomendasikan agar run tidak gagal karena interupsi terminal lokal.
- Guard ukuran backup mencegah clean/strict jalan saat dump terindikasi terlalu kecil.
- Untuk mode `--clean` dan `--strict-minimal`, rollback DB otomatis akan dicoba jika deploy gagal (sumber dari backup lokal run yang sama).
- Untuk mode `--clean`, default sekarang preserve-data (auto-restore setelah clean sukses), kecuali `--clean-reset-data`.
