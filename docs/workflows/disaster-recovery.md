# Disaster Recovery — Prosedur Restore Database

> Dokumen ini mendokumentasikan prosedur restore database dari backup untuk pemulihan darurat (DR).
> Berlaku untuk stack produksi LPSaring Hotspot Portal di DigitalOcean.

## Arsitektur Backup Saat Ini

- **Trigger**: Otomatis setiap deploy via `deploy_pi.sh` (pre-deploy backup)
- **Format**: `pg_dump` plaintext SQL
- **Storage**:
  - Remote: `$REMOTE_DIR/_safe_backups/<nama>_predeploy_<timestamp>/postgres_dump.sql`
  - Lokal: `../backups/<host>_<nama>_predeploy_<timestamp>.sql`
- **Retention**: 14 backup terbaru (configurable via `BACKUP_RETENTION_COUNT`)
- **Safety guard**: Deploy mode destruktif (`--clean`, `--strict-minimal`) dibatalkan jika backup < 100KB

## Prasyarat

- SSH access ke server produksi (`ssh -i ~/.ssh/id_raspi_ed25519 abdullah@159.89.192.31 -p 1983`)
- Docker Compose tersedia di server
- File backup `.sql` tersedia (lokal atau remote)

## Prosedur Restore (Full Recovery)

### 1. Hentikan Semua Service Kecuali Database

```bash
cd ~/lpsaring/app
docker compose --env-file .env.prod -f docker-compose.prod.yml stop backend celery_worker celery_beat frontend
```

### 2. Identifikasi Backup Terbaru

```bash
# Remote backups
ls -lt ~/lpsaring/app/_safe_backups/
# Lokal (di mesin dev)
ls -lt ../backups/*.sql
```

### 3. Upload Backup ke Server (jika restore dari lokal)

```bash
scp -i ~/.ssh/id_raspi_ed25519 -P 1983 \
  ../backups/<file_backup>.sql \
  abdullah@159.89.192.31:/tmp/restore_backup.sql
```

### 4. Restore Database

```bash
# Pastikan DB container running
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db
sleep 5

# Drop dan recreate database
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc '
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"
'

# Restore dari backup
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc '
  psql -U "$POSTGRES_USER" "$POSTGRES_DB"
' < /tmp/restore_backup.sql

# Atau jika backup ada di remote _safe_backups:
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc '
  psql -U "$POSTGRES_USER" "$POSTGRES_DB"
' < ~/lpsaring/app/_safe_backups/<latest>/postgres_dump.sql
```

### 5. Jalankan Migration (jika ada migration baru setelah backup)

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend flask db upgrade
```

### 6. Restart Semua Service

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

### 7. Verifikasi

```bash
# Health check
curl -s http://localhost:5010/ping | python3 -m json.tool

# Cek jumlah user (sanity check)
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc '
  psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c "SELECT COUNT(*) AS total_users FROM users;"
'

# Cek container health
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

## Jadwal DR Drill

| Frekuensi | Aktivitas |
|-----------|-----------|
| Bulanan   | Restore backup terbaru ke environment E2E lokal, verifikasi data integrity |
| Per deploy | Pre-deploy backup otomatis (sudah berjalan) |

## DR Drill Lokal (via E2E Stack)

Untuk menguji restore tanpa risiko ke produksi:

```bash
# 1. Spin up E2E stack
docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e up -d db
sleep 10

# 2. Restore backup ke E2E database
docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e exec -T db sh -lc '
  psql -U hotspot_e2e_user -d hotspot_e2e_db
' < ../backups/<latest_backup>.sql

# 3. Start full stack dan verifikasi
docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e up -d
curl -s http://localhost:5011/ping

# 4. Cleanup setelah drill
docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e down -v
```

## Keputusan & Catatan

- Backup off-site (S3/R2) belum diimplementasi — masih mengandalkan 2-layer (remote server + lokal dev machine)
- Backup hanya database; file statis dan konfigurasi dikelola via Git
- Redis tidak di-backup (data ephemeral: rate limit counters, circuit breaker state, Celery schedule)
