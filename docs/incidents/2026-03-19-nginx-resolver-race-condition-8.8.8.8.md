# Incident 2026-03-19: Nginx Resolver Race Condition — 8.8.8.8 vs 127.0.0.11

Status: resolved — nginx resolver dikonfigurasi ulang, dipush via `--sync-nginx-conf`.

## Ringkasan insiden

Setelah deploy ulang via `docker compose down` + `up` pada 18 Mar 2026 (bukan `--recreate`),
terjadi 502 intermiten berkelanjutan pada endpoint `/api/auth/me` dan beberapa API lain.
Kondisi ini berlangsung dari 16:43 sampai 16:56 UTC, sekitar 13 menit, dengan pola reguler
tiap :35 detik (sesuai polling interval 60 detik dari browser admin yang sudah berjalan).

## Gejala yang terlihat

- HTTP 502 dari nginx pada `/api/auth/me` secara periodik setiap menit, tepat pada detik ke-35.
- Setiap 502 diikuti 200 dari request lain pada timestamp yang sama (browser/tab berbeda berhasil).
- Error log nginx: `lpsaring-backend could not be resolved (3: Host not found)`.
- Saat `nslookup lpsaring-backend 127.0.0.11` dari dalam container nginx — berhasil (IP benar).
- Masalah tetap ada setelah nginx `-s reload` pertama karena client masih menggunakan koneksi keepalive ke worker lama.

## Evidence utama

Error log nginx (`/home/abdullah/nginx/logs/lpsaring_error.log`):

```
2026/03/18 16:43:35 [error] 1015#1015: *38334 lpsaring-backend could not be resolved (3: Host not found)
2026/03/18 16:44:35 [error] 1015#1015: *38334 lpsaring-backend could not be resolved (3: Host not found)
...
2026/03/18 16:56:35 [error] 1101#1101: *38531 lpsaring-backend could not be resolved (3: Host not found)
```

Setelah sync nginx config (hapus `8.8.8.8`) dan reload:

```
2026/03/18 16:58:35 GET /api/auth/me → 200 (dari 140.213.10.133 — client yang sebelumnya selalu 502)
```

## Akar masalah (dua lapisan)

### Lapisan 1: `docker compose down` sebelum `--recreate`

`docker compose down` menghapus container dari `proxy-network`. Docker DNS (`127.0.0.11`)
mengembalikan NXDOMAIN untuk `lpsaring-backend` dan `lpsaring-frontend` selama container
sedang tidak ada. Kondisi ini berlangsung dari container down sampai container baru benar-benar
bergabung ke network (selisih 3–5 menit). Ini adalah penyebab utama 502 awal.

### Lapisan 2: Race condition 8.8.8.8 vs 127.0.0.11

Konfigurasi resolver nginx sebelumnya:

```nginx
resolver 127.0.0.11 8.8.8.8 ipv6=off valid=2s;
```

Nginx mengirim kueri ke **semua resolver secara paralel** dan menggunakan respons tercepat.
Karena `8.8.8.8` adalah public DNS, ia dapat menjawab lebih cepat dari Docker DNS `127.0.0.11`
untuk nama yang tidak ia kenal (`lpsaring-backend`). `8.8.8.8` mengembalikan NXDOMAIN karena
nama ini tidak ada di DNS publik. Nginx meng-cache NXDOMAIN selama `valid=2s`, sehingga
request berikutnya dalam 2 detik langsung gagal tanpa mencoba `127.0.0.11`.

Race condition ini menyebabkan kegagalan intermiten bahkan setelah container kembali aktif:
- 127.0.0.11 sudah mengembalikan IP yang benar
- Tetapi jika 8.8.8.8 menang dalam race (respons lebih cepat), nginx menyimpan NXDOMAIN
- Caching 2 detik → setiap beberapa detik ada jendela dimana NXDOMAIN aktif → 502

## Dampak

- 502 intermiten pada seluruh API endpoint yang melalui nginx ke backend untuk ±13 menit.
- Efek terlihat di tab browser admin yang sedang aktif (polling `/api/auth/me` 60 detik).
- User biasa yang baru membuka browser tidak terdampak jika mereka tiba di jendela 200 (retry nginx berhasil via proxy_next_upstream untuk tab baru).
- Tidak ada data hilang, tidak ada downtime database.

## Remediasi permanen

Hapus `8.8.8.8` dari konfigurasi resolver nginx. Hanya gunakan Docker DNS:

```nginx
# File: nginx/conf.d/lpsaring.conf
# Sebelum:
resolver 127.0.0.11 8.8.8.8 ipv6=off valid=2s;

# Sesudah:
resolver 127.0.0.11 ipv6=off valid=2s;
```

Docker DNS (`127.0.0.11`) adalah embedded DNS server yang berjalan di dalam network namespace
container nginx. Ia selalu tersedia selama Docker daemon aktif. Saat container dimatikan, ia
mengembalikan NXDOMAIN (bukan timeout) — yang di-cache selama `valid=2s`. Setelah container
kembali aktif dan bergabung ke network, DNS lookup berikutnya (dalam 2 detik) sudah mengembalikan
IP yang benar.

Tidak ada kebutuhan untuk public DNS fallback dalam konfigurasi ini.

**Kaidah yang ditambahkan ke MEMORY.md:**
> JANGAN tambah public DNS (8.8.8.8, 1.1.1.1, dll) sebagai resolver nginx untuk hostname internal Docker.

## Verifikasi pascaperbaikan

1. `nginx -t` dalam container: syntax OK.
2. `nginx -s reload`: loaded, worker baru berhasil resolve `lpsaring-backend`.
3. Monitoring error log selama 5 menit pasca reload: tidak ada error baru setelah 16:56 UTC.
4. `nslookup lpsaring-backend 127.0.0.11` dari dalam container nginx: berhasil mengembalikan `192.168.0.5`.
5. Akses log 16:58 wkt UTC: client `140.213.10.133` yang sebelumnya selalu 502 pada :35 sekarang mendapat `200`.

## Runbook — mencegah insiden serupa

```bash
# 1. SELALU gunakan --recreate, JANGAN manual docker compose down sebelumnya
cd /home/abdullah/lpsaring/app
bash /d/Data/Projek/hotspot/lpsaring/deploy_pi.sh --recreate   # dari lokal

# 2. Jika sudah terlanjur down, setelah up periksa network membership:
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  "docker network inspect proxy-network --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{\"\\n\"}}{{end}}'"

# 3. Verifikasi DNS dari dalam nginx:
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  "docker exec global-nginx-proxy nslookup lpsaring-backend && docker exec global-nginx-proxy nslookup lpsaring-frontend"

# 4. Jika DNS gagal, reload nginx saja (tidak perlu restart):
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  "docker exec global-nginx-proxy nginx -s reload"

# 5. Periksa error log untuk resolusi cepat:
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  "tail -20 /home/abdullah/nginx/logs/lpsaring_error.log"
```

## Artefak terkait

- `docs/incidents/2026-03-19-nginx-resolver-race-condition-8.8.8.8.md` ← file ini
- Config yang diubah: `../nginx/conf.d/lpsaring.conf`
- MEMORY.md: entry "nginx resolver race condition 8.8.8.8"
