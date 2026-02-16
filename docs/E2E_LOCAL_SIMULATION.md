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
- Pastikan env khusus E2E ada:
	- `backend/.env.e2e`
	- `frontend/.env.e2e`

- Jalankan stack:
	- `APP_ENV=e2e docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e up -d --build`

Untuk reset total (hapus volume E2E):
- `APP_ENV=e2e docker compose -f docker-compose.e2e.yml -p hotspot-portal-e2e down -v --remove-orphans`

## Menjalankan simulasi flow
Gunakan script PowerShell:
- `APP_ENV=e2e powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1 -UseIsolatedCompose 1 -ComposeProjectName hotspot-portal-e2e -IsolatedNginxPort 8089 -BaseUrl http://localhost:8089 -FreshStart 1 -Build 0 -UseOtpBypassOnly 1 -EnableMikrotikOps 0 -ApplyMikrotikOnQuotaSimulation 0 -CleanupAddressList 0`

Catatan:
- `-UseOtpBypassOnly 1` memastikan script tidak memanggil request OTP (yang biasanya memicu WhatsApp).
- Jika mau uji integrasi MikroTik, set `-EnableMikrotikOps 1` dan pastikan `MIKROTIK_*` valid di `backend/.env.e2e`.

## Apa yang divalidasi terkait refresh-token
Di dalam script ada tahap:
- Verify OTP (sekali) untuk mendapatkan cookie
- Simulasi "browser ditutup": session baru hanya membawa cookie `refresh_token`
- Panggil endpoint protected berbasis cookie (tanpa `Authorization: Bearer ...`)

Jika tahap ini sukses, artinya user bisa tetap login setelah browser ditutup selama refresh cookie masih valid.
