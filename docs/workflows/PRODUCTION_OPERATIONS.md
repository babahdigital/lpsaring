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

### Deploy dengan build image baru (trigger GitHub Actions)

> **⚠ WAJIB:** Lakukan `git push origin main` DULU sebelum `--trigger-build`.
> GitHub Actions build image dari `origin/main` di GitHub — commit yang belum di-push **tidak akan** masuk ke image.
> Health check tetap hijau meski build menggunakan image lama. Lihat: `docs/incidents/2026-03-19-deploy-unpushed-commits.md`.

```bash
# 1. Pastikan commit sudah di-push ke remote
git push origin main

# 2. Trigger build + tunggu selesai + auto recreate
cd lpsaring && bash deploy_pi.sh --trigger-build

# Atau: trigger build tanpa recreate otomatis
gh workflow run docker-publish.yml --field clean_before_deploy=true
```

Indikator bangunan menggunakan kode yang salah: Alembic output menunjukkan `CURRENT_REV` dari commit
sebelumnya (bukan commit terbaru), meski health check dan container status berwarna hijau.

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

## Validasi Trust Boundary Captive Portal

Gunakan langkah ini bila deploy menyentuh flow `/captive`, `/login`, atau `/login/hotspot-required`.

### Cek cepat publik

```bash
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  'tail -n 400 /home/abdullah/nginx/logs/access.log \
    | grep -E "link_login_only|/captive|/login|/hotspot-required|wartelpas|172\.16\.12\.1| 500 | 401 " || true'
```

### Cek cepat runtime app

```bash
$COMPOSE_PROD logs --since 20m --no-color backend frontend \
  | grep -Ei 'link_login_only|hotspot-required|wartelpas|172\.16\.12\.1|Traceback|Exception' || true
```

### Interpretasi hasil

- `link_login_only` dengan host trusted seperti `login.home.arpa` masih normal.
- `client_ip` hotspot yang sah harus tetap berada di CIDR allowlist produksi, saat ini `172.16.2.0/23`.
- Hit yang membawa `wartelpas`, `172.16.12.1`, atau subnet asing harus diperlakukan sebagai foreign context dan tidak boleh diizinkan masuk ke flow activation.
- Jika tidak ada hit hari ini, itu hanya berarti belum ada traffic captive/login pada window audit tersebut; verifikasi end-to-end perlu memakai satu sesi hotspot nyata.

### Aturan perubahan allowlist

- Jika ada router login atau subnet hotspot resmi baru, update `NUXT_PUBLIC_HOTSPOT_ALLOWED_CLIENT_CIDRS` dan `NUXT_PUBLIC_HOTSPOT_TRUSTED_LOGIN_HOSTS`.
- Jangan menonaktifkan guard untuk mengakomodasi portal asing atau device liar.
- Setelah allowlist berubah, ulangi focused frontend tests untuk hotspot trust sebelum deploy.

## Validasi Hotspot Sync Pascadeploy

### Urutan aman yang sudah tervalidasi

1. Pastikan CI dan image publish untuk commit target sudah sukses.
2. Jika butuh hard refresh worker/container sebelum recreate, turunkan app stack lebih dulu:

```bash
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  'cd /home/abdullah/lpsaring/app && docker compose --env-file .env.prod -f docker-compose.prod.yml down --remove-orphans'
```

3. Jalankan deploy recreate:

```bash
./deploy_pi.sh --detach-local --recreate
```

4. Simpan stdout/stderr command panjang ke file lokal `tmp/` bila perlu forensik; jangan jadikan wrapper terminal sebagai source of truth tunggal.
5. Lakukan health check publik dan container.
6. Jalankan parity audit dari backend dan tunggu minimal satu full run `sync_hotspot_usage_task` berikutnya.

### Ekspektasi runtime yang sehat

- First natural run setelah recreate harus benar-benar masuk ke log `Memulai sinkronisasi kuota dan profil hotspot.` lalu selesai dengan `Sinkronisasi selesai`.
- Beat berikutnya boleh mengeluarkan `Skip sinkronisasi (menunggu interval dinamis)` jika interval belum lewat.
- `Skip sinkronisasi (worker lain sedang berjalan)` hanya boleh dianggap normal bila `celery inspect active` memang menunjukkan task quota sync lain yang sedang aktif.
- Baseline produksi tervalidasi per 17 Maret 2026 untuk full run berada di kisaran `60-66s`.

### Diagnosis stale quota lock

Gunakan langkah ini bila gejala pascarecreate menunjukkan skip palsu:

```bash
$COMPOSE_PROD exec -T celery_worker celery -A celery_worker.celery_app inspect active
$COMPOSE_PROD exec -T redis redis-cli GET quota_sync:run_lock
$COMPOSE_PROD exec -T redis redis-cli TTL quota_sync:run_lock
$COMPOSE_PROD logs --since 15m --no-color celery_worker celery_beat \
  | grep -E 'sync_hotspot_usage_task|Sinkronisasi|Skip sinkronisasi'
```

Aturan operasional:

- Jika `inspect active` menunjukkan task sync aktif lain, biarkan lock apa adanya.
- Jika `inspect active` kosong tetapi key lock masih hidup, perlakukan sebagai kandidat stale lock.
- Penghapusan manual `quota_sync:run_lock` hanya boleh dilakukan saat tidak ada task sync aktif lain yang valid.
- Setelah recovery, ulangi parity audit dan tunggu satu full run quota sync lagi.

### Interpretasi parity pascadeploy

- Counter ini harus tetap `0` sebelum deploy dianggap stabil:
  - `status_without_binding`
  - `critical_without_binding`
  - `unauthorized_overlap`
  - `status_multi_overlap`
  - `binding_dhcp_ip_mismatch`
- `authorized_mac_without_dhcp` dipantau terpisah karena bisa naik akibat device authorized yang sedang offline; jangan jadikan blocker deploy tanpa audit per-device.
- Devlog detail dan RCA insiden terkait ada di `docs/devlogs/2026-03-17-hotspot-sync-hardening.md` dan `docs/incidents/2026-03-17-stale-quota-sync-lock.md`.
- RCA dan devlog untuk foreign captive context ada di `docs/incidents/2026-03-17-foreign-hotspot-context.md` dan `docs/devlogs/2026-03-17-hotspot-portal-trust-hardening.md`.

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