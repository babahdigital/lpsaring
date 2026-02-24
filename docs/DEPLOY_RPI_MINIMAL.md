# Deploy Minimal ke Raspberry Pi (Tanpa Clone Full Repo)

Dokumen ini untuk skenario production ringan: **tidak perlu clone seluruh repository**.

## 1) Struktur Folder di Raspberry Pi

Buat struktur seperti ini:

```text
/home/abdullah/sobigidul/
├─ docker-compose.prod.yml
├─ .env.prod
├─ .env.public.prod
├─ infrastructure/
│  └─ nginx/
│     ├─ conf.d/
│     │  └─ app.prod.conf
│     ├─ ssl/
│     │  ├─ fullchain.pem        # opsional (jika terminate SSL di Nginx)
│     │  └─ privkey.pem          # opsional
│     └─ logs/
└─ backend/
   └─ backups/
```

## 2) Persiapan Folder di Pi

```bash
sudo mkdir -p /home/abdullah/sobigidul/infrastructure/nginx/conf.d
sudo mkdir -p /home/abdullah/sobigidul/infrastructure/nginx/ssl
sudo mkdir -p /home/abdullah/sobigidul/infrastructure/nginx/logs
sudo mkdir -p /home/abdullah/sobigidul/backend/backups
sudo chown -R $USER:$USER /home/abdullah/sobigidul
```

## 3) Copy File dari Laptop ke Pi (SCP)

Catatan: repository menyertakan template env:

- `.env.prod.example` → salin menjadi `.env.prod` lalu isi nilai sebenarnya (jangan commit)
- `.env.public.prod.example` → salin menjadi `.env.public.prod`

Jalankan dari laptop (PowerShell/Git Bash), sesuaikan `PI_USER` dan `PI_HOST`:

```bash
PI_USER=abdullah
PI_HOST=192.168.1.20
PI_PORT=1983
SSH_KEY=~/.ssh/id_raspi_ed25519
LOCAL_ROOT=/d/Data/Projek/hotspot/lpsaring
REMOTE_ROOT=/home/abdullah/sobigidul

scp -P "$PI_PORT" -i "$SSH_KEY" "$LOCAL_ROOT/docker-compose.prod.yml" "$PI_USER@$PI_HOST:$REMOTE_ROOT/"
scp -P "$PI_PORT" -i "$SSH_KEY" "$LOCAL_ROOT/.env.prod" "$PI_USER@$PI_HOST:$REMOTE_ROOT/"
scp -P "$PI_PORT" -i "$SSH_KEY" "$LOCAL_ROOT/.env.public.prod" "$PI_USER@$PI_HOST:$REMOTE_ROOT/"
scp -P "$PI_PORT" -i "$SSH_KEY" "$LOCAL_ROOT/infrastructure/nginx/conf.d/app.prod.conf" "$PI_USER@$PI_HOST:$REMOTE_ROOT/infrastructure/nginx/conf.d/"
```

### 3.1 Versi Langsung (Tanpa Variable)

Ganti `<PI_USER>` dan `<PI_HOST>` lalu jalankan langsung:

```bash
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /d/Data/Projek/hotspot/lpsaring/docker-compose.prod.yml <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /d/Data/Projek/hotspot/lpsaring/.env.prod <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /d/Data/Projek/hotspot/lpsaring/.env.public.prod <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /d/Data/Projek/hotspot/lpsaring/infrastructure/nginx/conf.d/app.prod.conf <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/infrastructure/nginx/conf.d/
```

Jika pakai sertifikat lokal Nginx:

```bash
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /path/to/fullchain.pem <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/infrastructure/nginx/ssl/
scp -P 1983 -i ~/.ssh/id_raspi_ed25519 /path/to/privkey.pem <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/infrastructure/nginx/ssl/
```

## 4) Alternatif Sinkronisasi (rsync)

Lebih praktis untuk update berulang:

```bash
PI_USER=pi
PI_HOST=192.168.1.20
PI_PORT=1983
SSH_KEY=~/.ssh/id_raspi_ed25519
LOCAL_ROOT=/d/Data/Projek/hotspot/lpsaring
REMOTE_ROOT=/home/abdullah/sobigidul

rsync -avz --progress -e "ssh -p $PI_PORT -i $SSH_KEY" \
  "$LOCAL_ROOT/docker-compose.prod.yml" \
  "$LOCAL_ROOT/.env.prod" \
  "$LOCAL_ROOT/.env.public.prod" \
  "$LOCAL_ROOT/infrastructure/nginx/conf.d/app.prod.conf" \
  "$PI_USER@$PI_HOST:$REMOTE_ROOT/"
```

### 4.1 rsync Langsung (Tanpa Variable)

```bash
rsync -avz --progress -e "ssh -p 1983 -i ~/.ssh/id_raspi_ed25519" \
  /d/Data/Projek/hotspot/lpsaring/docker-compose.prod.yml \
  /d/Data/Projek/hotspot/lpsaring/.env.prod \
  /d/Data/Projek/hotspot/lpsaring/.env.public.prod \
  /d/Data/Projek/hotspot/lpsaring/infrastructure/nginx/conf.d/app.prod.conf \
  <PI_USER>@<PI_HOST>:/home/abdullah/sobigidul/
```

## 5) Jalankan Service di Pi

SSH ke Pi lalu jalankan:

```bash
ssh -p 1983 -i ~/.ssh/id_raspi_ed25519 pi@192.168.1.20
cd /home/abdullah/sobigidul
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Cek log:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend frontend nginx
```

Catatan: karena `docker-compose.prod.yml` memakai variable `${...}` untuk cloudflared, semua perintah compose (termasuk `ps`, `logs`, `exec`) sebaiknya selalu pakai `--env-file .env.prod`.

### 5.1 One-shot SSH (Tanpa Masuk Shell Interaktif)

```bash
ssh -p 1983 -i ~/.ssh/id_raspi_ed25519 <PI_USER>@<PI_HOST> "cd /home/abdullah/sobigidul && docker compose --env-file .env.prod -f docker-compose.prod.yml pull && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d && docker compose --env-file .env.prod -f docker-compose.prod.yml ps"
```

## 6) Update Versi Aplikasi (Tanpa Clone Repo)

Jika image baru sudah dipublish ke Docker Hub:

```bash
cd /home/abdullah/sobigidul
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

### 6.0) Pastikan image `:latest` benar-benar baru

Kadang perubahan sudah di-push ke Git, tapi workflow Docker publish belum selesai, sehingga `pull` masih mengambil digest lama.

Cek timestamp/digest image yang ada di Pi:

```bash
docker image inspect babahdigital/sobigidul_frontend:latest --format 'id={{.Id}} created={{.Created}}'
docker image inspect babahdigital/sobigidul_backend:latest --format 'id={{.Id}} created={{.Created}}'
```

Jika `created` belum berubah setelah push terbaru, tunggu workflow publish selesai lalu jalankan `pull` ulang.

Jika ada perubahan skema DB, jalankan juga:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend flask db upgrade
```

## 6.1) Housekeeping: Rapikan transaksi EXPIRED

Jika halaman transaksi admin penuh transaksi kadaluarsa (EXPIRED/FAILED/CANCELLED), bersihkan yang lama:

Dry-run:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend flask cleanup-transactions --older-than-days 1
```

Apply:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend flask cleanup-transactions --older-than-days 1 --apply
```

## 7) Catatan Penting

- Pastikan file `.env.prod` terisi lengkap untuk backend dan service produksi.
- Cloudflare Tunnel dijalankan via `cloudflared` di `docker-compose.prod.yml`. Untuk stabilitas jaringan (menghindari error QUIC `timeout: no recent network activity`), protokol tunnel dipaksa menggunakan **HTTP/2**.
- Jika memakai DHCP static lease (disarankan untuk mengurangi "putus-nyambung" akibat IP berubah), pastikan:
  - `MIKROTIK_DHCP_STATIC_LEASE_ENABLED=True`
  - `MIKROTIK_DHCP_LEASE_SERVER_NAME` menunjuk DHCP server hotspot utama (mis. `Klien`).
  - Ingat: runtime settings dibaca via `settings_service.get_setting()` (prioritas DB `application_settings`, fallback ke ENV). Pastikan nilai DB tidak kosong/salah.
- `.env.prod` dan `.env.public.prod` sebaiknya dianggap sebagai **sumber kebenaran di laptop** (lokal) lalu di-upload ke Pi saat deploy. Hindari edit manual di Pi agar konfigurasi tidak “drift”.
- Pastikan file `.env.public.prod` ada karena service frontend membaca file ini secara langsung.
- Jika ingin tombol “Hubungi Admin” mengarah ke WhatsApp, isi juga di `.env.public.prod`:
  - `NUXT_PUBLIC_ADMIN_WHATSAPP=+62...`
  - `NUXT_PUBLIC_WHATSAPP_BASE_URL=https://wa.me`
- Folder `backend/backups` harus ada agar bind mount tidak gagal.
- Jika tidak pakai SSL di Nginx (SSL terminate di Cloudflare/Tunnel), folder `ssl` boleh kosong.

## 8) Verifikasi Cepat

```bash
curl -I http://localhost
curl -s http://localhost/api/ping
```

Jika port 80 tidak dipublish ke host (deployment internal + cloudflared), lakukan healthcheck dari dalam container Nginx:

```bash
cd /home/abdullah/sobigidul
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T nginx wget -qO- http://127.0.0.1/api/ping
```

Dari laptop:

```bash
curl -I http://<IP_PI>
```

## 9) One-Command Deploy Script (Direkomendasikan)

Script siap pakai ada di root project: [deploy_pi.sh](../deploy_pi.sh).

Contoh pakai:

```bash
bash ./deploy_pi.sh --host 10.10.83.2 --user abdullah --port 1983 --remote-dir /home/abdullah/sobigidul --prune
```

Catatan opsi:
- `--prune`: safe prune (container/image/network/builder) dan **tidak** menghapus volume.
- Jangan gunakan `--clean` kecuali benar-benar ingin reset total (karena menjalankan `down -v`).

### 9.1) Verifikasi migrate benar-benar sukses

Walau service `migrate` otomatis jalan saat `docker compose up -d` (karena `backend` depends_on migrate), tetap disarankan verifikasi exit code:

```bash
ssh -p 1983 -i ~/.ssh/id_raspi_ed25519 abdullah@10.10.83.2 \
  'cd /home/abdullah/sobigidul && \
   echo MIGRATE_EXIT=$(docker inspect -f "{{.State.ExitCode}}" hotspot_prod_flask_migrate) && \
   echo MIGRATE_STATUS=$(docker inspect -f "{{.State.Status}}" hotspot_prod_flask_migrate) && \
   docker logs --tail 50 hotspot_prod_flask_migrate'
```

Expected:
- `MIGRATE_EXIT=0`
- `MIGRATE_STATUS=exited`

```bash
./deploy_pi.sh --host <IP_PI>
```

Untuk skenario kamu (folder produksi dibuat **strict minimal** di `/home/abdullah/sobigidul`):

```bash
./deploy_pi.sh --host 10.10.83.2 --user abdullah --port 1983 \
  --key ~/.ssh/id_raspi_ed25519 \
  --remote-dir /home/abdullah/sobigidul \
  --strict-minimal \
  --prune
```

### 9.1 (Opsional) Tunggu CI hijau dulu: `--wait-ci`

Jika workflow Docker publish belum selesai, deploy terlalu cepat bisa membuat Pi menarik image `:latest` yang **masih digest lama**.

Solusi: gunakan `--wait-ci` agar script menunggu GitHub checks/Actions hijau untuk commit saat ini.

Syarat:
- Set salah satu env berikut di terminal yang sama saat menjalankan deploy:
  - `GH_TOKEN` atau `GITHUB_TOKEN`

Contoh:

```bash
export GH_TOKEN="<TOKEN>"   # jangan commit / jangan tulis ke repo

./deploy_pi.sh --host 10.10.83.2 --user abdullah --port 1983 \
  --key ~/.ssh/id_raspi_ed25519 \
  --remote-dir /home/abdullah/sobigidul \
  --strict-minimal \
  --wait-ci \
  --prune
```

Catatan (Windows):
- `export GH_TOKEN=...` hanya berlaku untuk sesi terminal itu saja.
- Pastikan menjalankan `./deploy_pi.sh ... --wait-ci` pada terminal yang sama yang sudah men-set token.

Dengan opsi SSL:

```bash
./deploy_pi.sh --host <IP_PI> \
  --ssl-fullchain /path/to/fullchain.pem \
  --ssl-privkey /path/to/privkey.pem
```

Cek dulu tanpa eksekusi (dry-run):

```bash
./deploy_pi.sh --host <IP_PI> --dry-run
```

## 10) Wartelpas Runbook

Untuk operasional `wartelpas.sobigidul.com` (Cloudflare Tunnel, Nginx routing, recovery SQLite korup, whitelist), lihat:

- [docs/WARTELPAS_OPERATIONS.md](WARTELPAS_OPERATIONS.md)
