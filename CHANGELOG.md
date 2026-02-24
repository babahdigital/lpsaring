# Changelog

Semua perubahan penting pada proyek ini akan dicatat di file ini.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) dan versi mengikuti SemVer.

Lampiran wajib:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

## [Unreleased]

### Added
- Backend: fallback sqlite in-memory untuk pytest saat env DB belum tersedia.
- Frontend: script `typecheck` dan perbaikan typing `useApiFetch` untuk default data.
- CI: workflow sederhana untuk lint backend, pytest, dan lint frontend.
- Backend: mode CSRF ketat untuk request tanpa Origin/Referer dengan allowlist IP/CIDR.
- Backend: unit test CSRF guard dan normalisasi MAC.

### Changed
- Backend: sinkronisasi kuota menggunakan delta per-MAC (Redis last-bytes) + pembulatan MB konsisten.
- Backend: kebijakan hotspot login/ip-binding kini mendukung mode campuran berbasis status user (`HOTSPOT_BYPASS_STATUSES`), bukan hanya global `IP_BINDING_TYPE_ALLOWED`.
- Backend: verifikasi OTP kini mengizinkan auto-otorisasi perangkat pada login OTP agar tidak langsung masuk kondisi blokir pending-auth.
- Frontend: tampilan kuota mendukung MB desimal pada chart.
- Keamanan: CSRF origin guard untuk cookie auth dan JSON error handler konsisten.
- Health endpoint selalu HTTP 200 dengan status `ok`/`degraded`.
- Nginx: CSP produksi dipersempit (hapus `unsafe-eval`).
- CI/CD: workflow publish memakai Dockerfile produksi eksplisit per service dan build arg `NODE_OPTIONS` untuk stabilitas build frontend.
- Frontend: pipeline build Docker menambahkan `nuxt prepare` sebelum build untuk kompatibilitas `--ignore-scripts`.
### Added
- Dokumentasi detail endpoint API (request/response).
- Panduan kontribusi (flow PR, lint, testing).
- Template changelog ini.
- Endpoint opsi Mikrotik untuk form admin.
- Integrasi Snap.js Midtrans dengan loader aman dan promise readiness.
- Tampilan harga per hari/GB di halaman beli.
- Tombol unduh invoice dan refresh status pembayaran.
- Pengiriman invoice PDF via WhatsApp (backend).
- Endpoint health check untuk DB/Redis/Mikrotik.
- Endpoint metrics admin untuk OTP/payment/login.
- Script verifikasi walled-garden.
- Backend: script opsional `backend/scripts/normalize_phone_numbers.py` untuk scan/report/apply normalisasi `users.phone_number` ke E.164.
- Deploy: opsi `--sync-phones` dan `--sync-phones-apply` di `deploy_pi.sh` untuk menjalankan normalisasi nomor telepon dari dalam container backend.

### Changed
- Validasi nomor telepon ke format E.164 saat login/daftar.
- Redirect /register dan /daftar ke tab registrasi.
- Base URL lokal aplikasi ke HTTP (lpsaring.local).
- Cloudflared tunnel menggunakan HTTP/2.
- UI admin paket disederhanakan (hilangkan kelola profil di halaman paket).
- Penanganan HMR Nuxt memakai WS saat host HMR kosong.
- Pesan error pembayaran lebih informatif di captive.
- Auth session dipindah ke cookie `HttpOnly` server-side.
- Rate limit spesifik untuk OTP dan admin login ditambahkan.
- CSP header diberlakukan di Nginx.
- OTP anti-abuse memakai cooldown dan batas percobaan.
- WhatsApp: notifikasi low-quota diperkecil agar tidak noise (default cukup 5%; FUP 20% tetap via notifikasi status).
- Task Celery memakai retry/backoff dan DLQ sederhana.
- Public settings di-cache untuk mengurangi beban DB.

### Fixed
- Frontend: pelunasan tunggakan (Lunasi) tidak lagi mengirim event click sebagai `manual_debt_id` (fix 422).
- Frontend: dialog metode pembayaran pelunasan disamakan dengan dialog di `/beli` (dashboard/riwayat), termasuk per-item hutang manual.
- Backend: estimasi harga hutang kuota memilih paket referensi berdasarkan kecocokan kuota (closest-fit), bukan termurah-by-price.
- CI/Backend: perbaikan Ruff `F821` akibat variabel sisa pasca refactor.

### Changed
- Frontend: saat Core API aktif, GoPay/ShopeePay dapat redirect langsung ke deeplink bila backend mengembalikan `redirect_url`.
- OTP request 400 akibat body kosong.
- Redirect captive yang berulang (link_orig).
- Ikon Tabler tidak muncul (nama ikon diperbaiki).
- Flow pembayaran Midtrans pada captive dan halaman beli.
- Snap.js tidak terbaca karena script belum siap.
- WSS HMR gagal saat 443 tidak aktif.
- Log dan error handling saat inisiasi pembayaran.
- Frontend (Admin Dashboard): tooltip ApexCharts tidak lagi redundant/duplikat pada chart donut "Paket Terlaris".

## [0.1.0] - 2026-02-08
### Added
- Inisialisasi dokumentasi proyek dan checklist pengembangan.
