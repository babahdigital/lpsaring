# E2E Lokal — Refresh Token + Flow Captive (tanpa ganggu Dev)

Tujuan E2E ini adalah simulasi flow/arsitektur (auth + refresh-token + device binding) **secara lokal**, tanpa tunnel/cloudflared, tanpa kirim WhatsApp sungguhan.

## Port yang dipakai (anti bentrok dev)
- Backend: `http://localhost:5011` (host) → `5010` (container)
- Frontend: `http://localhost:3011` (host) → `3010` (container)
- Nginx (gateway utama): `http://localhost:8089`

## Compose file
- Standalone E2E: `docker-compose.e2e.yml`

File ini sudah berisi stack lengkap dan sengaja **tidak** di-merge dengan `docker-compose.yml` supaya port dev tidak ikut terbuka.

## Menjalankan stack E2E
Dari root repo:
- `docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e up -d`

Untuk reset total (hapus volume E2E):
- `docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e down -v --remove-orphans`

## Menjalankan simulasi flow
Gunakan script PowerShell:
- `powershell.exe -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1 -UseE2ECompose:$true -ComposeProjectName hotspot-portal-e2e -UseOtpBypassOnly:$true -SkipMikrotik:$true -BaseUrl http://localhost:8089`

Catatan:
- `-UseOtpBypassOnly:$true` memastikan script tidak memanggil request OTP (yang biasanya memicu WhatsApp).
- `-SkipMikrotik:$true` men-skip check/cleanup/address-list yang butuh koneksi MikroTik sungguhan.

## Apa yang divalidasi terkait refresh-token
Di dalam script ada tahap:
- Verify OTP (sekali) untuk mendapatkan cookie
- Panggil `POST /api/auth/refresh` berbasis cookie
- Panggil endpoint protected tanpa `Authorization: Bearer ...`

Jika tahap ini sukses, artinya user bisa tetap login setelah browser ditutup selama refresh cookie masih valid.
