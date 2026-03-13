# On-call Quick Runbook

Referensi standar command: [OPERATIONS_COMMAND_STANDARD.md](./OPERATIONS_COMMAND_STANDARD.md).
Referensi status akses canonical: [ACCESS_STATUS_MATRIX.md](./ACCESS_STATUS_MATRIX.md).
Referensi insiden unauthorized berulang: [OPERATIONS_UNAUTHORIZED_REAPPEAR_RESPONSE.md](./OPERATIONS_UNAUTHORIZED_REAPPEAR_RESPONSE.md).

Gunakan canonical compose prefix:

```bash
COMPOSE_PROD="docker compose --env-file .env.prod -f docker-compose.prod.yml"
```

## 1) Cek Cepat (2 menit)
- API ping harus `200`:
  - `curl -sS https://lpsaring.babahdigital.net/api/ping`
- Halaman publik utama harus `200`:
  - `/merchant-center`
  - `/merchant-center/privacy`
  - `/merchant-center/terms`

## 2) Cek Service Runtime (Server)
- `$COMPOSE_PROD ps`
- Semua service inti harus `Up`:
  - `backend`, `frontend`, `db`, `redis`, `celery_worker`, `celery_beat`
  - `global-nginx-proxy`, `global-cloudflared`

## 3) Cek Error Window 20 Menit
- Backend/Celery error count:
  - `$COMPOSE_PROD logs --since 20m --no-color backend celery_worker celery_beat | grep -Ec '"level": "ERROR"|"level": "CRITICAL"|Traceback|Exception' || true`
- Nginx 5xx count:
  - `docker logs --since 20m global-nginx-proxy | grep -Ec ' 5[0-9][0-9] ' || true`

## 4) Kriteria Sehat
- Ping API normal
- Endpoint publik `200`
- Service inti `Up`
- Error count backend/celery = `0`
- Nginx 5xx = `0`

## 5) Jika Ada Anomali
- Ulang cek 5 menit kemudian (konfirmasi bukan spike sesaat)
- Jika tetap anomali:
  - capture log 20m terakhir,
  - catat endpoint terdampak,
  - eskalasi ke maintainer,
  - pertimbangkan rollback jika core flow terdampak > 15 menit.

## 6) Cek Khusus Auto-login & Hotspot-required

Gunakan saat ada laporan user sering OTP ulang atau user sudah login tapi internet belum aktif.

- Hitung endpoint auth hotspot (server):
  - `$COMPOSE_PROD logs --since 6h --no-color backend | grep -Ec '/api/auth/auto-login' || true`
  - `$COMPOSE_PROD logs --since 6h --no-color backend | grep -Ec '/api/auth/hotspot-session-status' || true`
  - `$COMPOSE_PROD logs --since 6h --no-color backend | grep -Ec '/api/auth/request-otp' || true`
  - `$COMPOSE_PROD logs --since 6h --no-color backend | grep -Ec '/api/auth/verify-otp' || true`

- Sampel log endpoint (server):
  - `$COMPOSE_PROD logs --since 45m --no-color backend | grep -E '/api/auth/(auto-login|hotspot-session-status|request-otp|verify-otp|me)' | tail -n 200`

- Validasi route frontend hotspot-required via Nginx (server):
  - `docker logs --since 6h global-nginx-proxy | grep -E 'GET /login/hotspot-required|GET /login|GET /captive' | tail -n 120`

Interpretasi cepat:
- `auto-login` sangat rendah/0 dengan `request-otp` tinggi berulang → investigasi bootstrap auth client.
- `hotspot-session-status` 0 pada periode insiden user login-route → investigasi middleware precheck route guest.
- Hit `/login/hotspot-required` ada tetapi user tetap tidak lanjut → cek endpoint `GET /api/auth/hotspot-session-status` dan status ip-binding user.

## 7) Cek Khusus bind-current SIGKILL (502 dari dashboard)

Gunakan saat ada laporan user klik "Koneksikan Internet" di dashboard gagal (502 / spinner tidak berhenti).

- Cek SIGKILL gunicorn:
  ```bash
  $COMPOSE_PROD logs --since 1h --no-color backend | grep -E 'SIGKILL|Worker|Booting'
  ```
  - Jika ada `Worker was sent SIGKILL` → worker timeout (bukan OOM).

- Cek nginx bind-current error:
  ```bash
  docker logs --since 1h global-nginx-proxy 2>&1 | grep 'bind-current'
  ```

- Cek apakah masalah sebelum atau setelah patch `76e66bca`:
  - **Setelah patch**: bind-current slow path (tanpa client_ip) kini gunakan 1 koneksi MikroTik bersama. Jika SIGKILL masih terjadi, kemungkinan koneksi MikroTik single connection >120s (MikroTik load tinggi atau WireGuard jitter).
  - **Diagnosis MikroTik latency**: `$COMPOSE_PROD logs --since 30m --no-color backend | grep -E 'mikrotik|MikroTik pool' | head -30`

- Jika MikroTik tidak responsif, gunicorn timeout masih bisa terjadi walau hanya 1 koneksi → pertimbangkan naikkan `--timeout=150` di docker-compose sementara.

## 8) Cek hotspot-required.vue Status "Aktifkan Internet"

Alur berhasil (captive portal → hotspot-required.vue):
1. User OTP berhasil
2. `authorizeDevice()` dipanggil dengan `client_ip` dan `client_mac` dari URL params
3. `bind-current` → **fast path** (client_ip valid) → 1 koneksi MikroTik → ip-binding `bypassed`
4. Poll `hotspot-session-status` 3× (900ms interval) → `binding_active=True` via `db-device-mac` fallback
5. `continueToPortal()` dipanggil → redirect ke portal MikroTik

Konfirmasi di log backend:
```bash
$COMPOSE_PROD logs --since 30m --no-color backend | grep -E 'lookup_mode|binding_active|bind.current' | tail -30
```

Gejala sehat:
```
lookup_mode=router-mac-from-user-ip binding_active=True
```
atau:
```
lookup_mode=db-device-mac binding_active=True
```

Gejala bermasalah:
- `lookup_mode=missing-hints binding_active=False` → ip-binding tidak dibuat atau user belum ada di MikroTik
- `upstream prematurely closed` pada `bind-current` → lihat section 7 (SIGKILL)
