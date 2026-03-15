# Workflow Operasi Produksi

Dokumen ini menjadi runbook utama untuk backup, deploy, restore, health check, dan rollback produksi.

Lampiran wajib:
- [.github/copilot-instructions.md](../../.github/copilot-instructions.md)

## Target Produksi Tetap

- SSH: `ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31`
- App dir: `/home/abdullah/lpsaring/app`
- Global proxy dir: `/home/abdullah/nginx`

Produksi memakai split-stack. App deploy tidak boleh menyentuh `global-nginx-proxy`, `global-cloudflared`, WireGuard, atau stack lain di host.

## Prefix Compose Standar

```bash
COMPOSE_PROD="docker compose --env-file .env.prod -f docker-compose.prod.yml"
```

Semua command operasional app stack harus memakai prefix ini.

## Jalur Aman Harian

### Backup cepat

```bash
./deploy_pi.sh --detach-local --backup-only
```

### Deploy rutin

```bash
./deploy_pi.sh --detach-local --recreate
```

### Deploy dengan sync nginx config

```bash
./deploy_pi.sh --detach-local --recreate --sync-nginx-conf
```

## Mode Destruktif Yang Masih Diizinkan

### Clean preserve-data

```bash
./deploy_pi.sh --detach-local --clean --confirm-clean-data-loss --recreate
```

### Strict minimal app dir

```bash
./deploy_pi.sh --detach-local --strict-minimal --recreate
```

### Clean reset data

```bash
./deploy_pi.sh --detach-local --clean --clean-reset-data --confirm-clean-data-loss --recreate
```

Guard wajib sebelum mode destruktif:

- backup lokal berhasil dibuat
- ukuran backup masuk akal
- isi DB diverifikasi cepat
- maintenance window jelas

## Backup dan Restore

- Backup predeploy selalu berbentuk SQL dan disalin ke lokal `../backups`.
- Restore manual untuk kondisi insiden boleh memakai SQL atau dump, tetapi verifikasi schema dan `alembic_version` wajib dilakukan setelah restore.
- Setelah restore, jalankan migrate atau health check yang dibutuhkan sebelum membuka trafik penuh.

## Health Check Standar

```bash
$COMPOSE_PROD ps

docker exec global-nginx-proxy wget -T 10 -qO- \
  --header='Host: lpsaring.babahdigital.net' \
  http://127.0.0.1/api/ping
```

Cek tambahan yang umum dipakai:

- halaman `/login`
- satu asset `/_nuxt/...`
- log backend dan worker 10-20 menit terakhir

## Error Scan Singkat

```bash
$COMPOSE_PROD logs --since 20m --no-color backend celery_worker celery_beat \
  | grep -Ec '"level": "ERROR"|"level": "CRITICAL"|Traceback|Exception' || true

docker logs --since 20m global-nginx-proxy \
  | grep -Ec ' 5[0-9][0-9] ' || true
```

## Docker Cleanup Yang Aman

Jika host perlu dibersihkan tanpa menjatuhkan container aktif, batasi ke resource yang tidak dipakai:

- `docker builder prune -af`
- `docker image prune -f`

Jangan memakai `docker system prune --volumes` atau `docker volume prune` tanpa maintenance window dan audit yang jelas.

## Rollback Cepat

1. Stabilkan app stack dengan `up -d --remove-orphans`.
2. Jika regresi bersifat data, stop writer service lalu restore backup target.
3. Jalankan health check publik.
4. Audit log backend dan frontend sebelum menyatakan rollback selesai.

## Operasi Tambahan

- Preview remediation quota terlebih dahulu sebelum `--apply`.
- Jangan edit `.env.prod` langsung di host kecuali emergency; setelah itu sinkronkan kembali ke repo lokal.
- Hindari host-wide prune atau perubahan manual di produksi yang tidak tercermin di repositori.