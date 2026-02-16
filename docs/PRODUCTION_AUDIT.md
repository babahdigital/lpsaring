# Audit Produksi & Best Practice (Ringkas)

Dokumen ini berisi perbaikan keamanan yang sudah diterapkan sekarang, serta kekurangan dan rekomendasi untuk standar produksi.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Log perubahan
- Work log terbaru: [WORKLOG_2026-02-16.md](WORKLOG_2026-02-16.md)

## Refresh-token (session persisten) — catatan deploy produksi

### Temuan (drift produksi)
- Produksi bisa saja masih menjalankan image backend lama (belum ada endpoint refresh-token).
- `.env.prod` di server bisa belum berisi variabel `REFRESH_*`.

### Checklist deploy
1) Pastikan `.env.prod` berisi konfigurasi refresh cookie (contoh):
   - `REFRESH_TOKEN_EXPIRES_DAYS=30`
   - `REFRESH_COOKIE_NAME=refresh_token`
   - `REFRESH_COOKIE_HTTPONLY=True`
   - `REFRESH_COOKIE_SECURE=True`
   - `REFRESH_COOKIE_SAMESITE=Lax`
   - `REFRESH_COOKIE_PATH=/`
   - `REFRESH_COOKIE_DOMAIN=`
   - `REFRESH_COOKIE_MAX_AGE_SECONDS=2592000`
   - `REFRESH_TOKEN_RATE_LIMIT=60 per minute`

2) Pull image terbaru dan restart service backend + celery:
   - `docker compose -p hotspot-portal-prod -f docker-compose.prod.yml pull backend celery_worker celery_beat`
   - `docker compose -p hotspot-portal-prod -f docker-compose.prod.yml up -d --force-recreate backend celery_worker celery_beat`

3) Migrasi DB (wajib) untuk tabel `refresh_tokens`:
   - Jalankan via python venv di container:
     - `docker compose -p hotspot-portal-prod -f docker-compose.prod.yml exec backend /opt/venv/bin/python -m alembic -c /app/migrations/alembic.ini upgrade head`

4) Verifikasi cepat:
   - Cek endpoint ada:
     - `docker compose -p hotspot-portal-prod -f docker-compose.prod.yml exec backend sh -lc "grep -n '/api/auth/refresh' /app/app/infrastructure/http/auth_routes.py | head"`
   - Login OTP harus mengeluarkan 2 cookie:
     - `auth_token` (pendek)
     - `refresh_token` (panjang)

## Perbaikan keamanan yang sudah diterapkan
1) Cookie auth aman di produksi
   - `secure` otomatis aktif saat `NODE_ENV=production`.
2) Nuxt devtools nonaktif di produksi
   - Mengurangi exposure debugging UI.
3) Security headers dasar di Nginx
   - `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.
4) Idempotency webhook Midtrans
   - Notifikasi duplikat diblokir via Redis TTL.

## Checklist produksi (yang wajib dipenuhi)
- HTTPS aktif (TLS termination di Nginx atau upstream).
- HSTS hanya diaktifkan saat domain HTTPS sudah stabil.
- `OTP_ALLOW_BYPASS=false` di produksi.
- `SECRET_KEY` dan `JWT_SECRET_KEY` kuat dan unik.
- `APP_PUBLIC_BASE_URL` diset ke domain publik.
- `RATELIMIT_ENABLED=true`.
- `AUTO_ENROLL_DEBUG_LOG=false` di produksi.
- Backup Postgres terjadwal + uji restore.
- Monitoring log dan alert error aktif.

## Kekurangan/risiko yang masih ada (butuh tindak lanjut)
1) Cookie `HttpOnly`
   - Token auth kini diset via `Set-Cookie` server-side dengan `HttpOnly`.
   - Pastikan frontend tidak menyimpan token di localStorage dan semua request mengirim cookie.
2) Rate limit spesifik untuk endpoint auth
   - Limit per-IP/per-nomor sudah ditambahkan untuk `request-otp`, `verify-otp`, `admin/login`.
   - Pastikan nilai limit sesuai beban dan kebutuhan produksi.
3) OTP anti-abuse
   - Cooldown dan batas percobaan OTP sudah diterapkan.
3) Security headers lanjutan
   - CSP sudah aktif, namun masih mengizinkan `unsafe-inline`; perlu nonce/sha agar lebih ketat.
4) Manajemen secrets
   - Belum ada integrasi secret manager (Vault/SSM/Secrets Manager).
5) Dependency pinning ketat
   - Backend masih pakai `>=` sehingga ada risiko update tak terkontrol.
6) WAF/anti-bot
   - Belum ada proteksi layer-7 (WAF, bot protection) untuk publik.
7) Audit log akses sensitif
   - Belum ada audit khusus untuk admin login/aksi kritikal.
8) Trusted proxy CIDR terlalu luas (risiko spoofing IP)
   - `TRUSTED_PROXY_CIDRS` default mencakup 10/8, 172/12, 192/16.
   - Produksi sebaiknya dipersempit ke IP proxy nyata (Nginx/Cloudflare/host proxy).
9) CSRF guard untuk request tanpa Origin/Referer
   - Saat ini request cookie tanpa Origin/Referer tetap diterima.
   - Mengetatkan aturan ini bisa memutus klien non-browser (MikroTik/curl/monitoring), jadi perlu keputusan ops.

## Rekomendasi tindak lanjut (prioritas)
P0 (wajib):
- Pastikan `Set-Cookie` auth memakai `HttpOnly` + `Secure` penuh.
- Pastikan limiter ketat untuk endpoint OTP & admin login sesuai kebutuhan produksi.
- Pastikan HTTPS end-to-end + aktifkan HSTS hanya saat domain HTTPS sudah stabil.

P1 (sangat disarankan):
- Tambah CSP yang kompatibel dengan Nuxt/Vuetify.
- Terapkan secret manager dan rotasi secret berkala.
- Pin dependency backend (pip-tools/poetry) dan audit rutin.
- Aktifkan log JSON untuk agregasi terpusat.
- Tambahkan sink log (Sentry/ELK/Cloud Logging) dan dashboard error rate.

P2 (nice-to-have):
- WAF/anti-bot (Cloudflare/WAF lain).
- Centralized logging + tracing (Sentry/OpenTelemetry).
- Policy backup & DR yang teruji.

## Catatan implementasi
- Jika ada requirement captive portal khusus, pastikan integrasi Mikrotik mengirim IP/MAC asli ke backend untuk auto-login.
- Setelah perubahan keamanan, lakukan smoke test login OTP, auto-login, admin login, dan halaman dashboard.
- Uji `CSRF_STRICT_NO_ORIGIN=True` di dev/staging terlebih dahulu.
- Atur `CSRF_NO_ORIGIN_ALLOWED_IPS` untuk klien non-browser (contoh: MikroTik 10.10.83.1, server 10.10.83.2). Hapus IP host dev di produksi.
- Gunakan allowlist berbasis CIDR untuk IP container (misalnya `172.16.0.0/12`) agar SSR Nuxt tidak terblokir.

## SOP Recovery Redis & Kuota
Tujuan: memulihkan sinkronisasi kuota jika Redis restart, data AOF bermasalah, atau `last_bytes` tidak konsisten.

Langkah diagnosis cepat:
1) Pastikan Redis hidup:
   - `docker compose exec redis redis-cli ping`
   - Expected: `PONG`
2) Cek status persistence:
   - `docker compose exec redis redis-cli info persistence | cat`
   - Pastikan `aof_enabled:1` dan tidak ada error `aof_last_bgrewrite_status:err`.

Langkah pemulihan aman:
1) Restart Redis bila perlu:
   - `docker compose restart redis`
2) Sinkronkan ulang kuota dari MikroTik:
   - `docker compose exec backend python -c "from app import create_app; from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles; app=create_app(); ctx=app.app_context(); ctx.push(); print(sync_hotspot_usage_and_profiles()); ctx.pop()"`
3) Validasi hasil:
   - Pastikan status user dan address-list sesuai (active/fup/habis/expired).

Catatan operasional:
- Jangan hapus semua key Redis di produksi. Jika perlu, batasi ke key `quota:last_bytes:mac:*`.
- Simpan backup Postgres sebelum recovery besar.
- Jika error berulang, cek koneksi MikroTik dan `TRUSTED_PROXY_CIDRS` agar IP binding tidak salah.
