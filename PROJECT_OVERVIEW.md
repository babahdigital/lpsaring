# Ringkasan Proyek (lpsaring)

Lampiran wajib:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

## Tujuan
Portal hotspot berbasis web untuk manajemen paket, transaksi, dan integrasi perangkat (MikroTik), dengan dukungan notifikasi dan pembayaran.

## Komponen Utama
- Backend: Flask + SQLAlchemy + Celery + Redis
- Frontend: Nuxt 3 + Vuetify
- Database: PostgreSQL
- Reverse proxy: Nginx

## Alur Aplikasi Ringkas
1) User akses portal/captive dan request OTP.
2) OTP diverifikasi; backend menentukan konteks klien (IP/MAC) dan mengikat perangkat (ip-binding + record device).
	- Default terbaru: OTP sukses = device yang dipakai ikut **terotorisasi** (self-authorization) agar tidak ke-block saat MAC berubah (privacy/random).
	- User juga bisa mengikat/mengelola perangkat dari UI (halaman akun) bila diperlukan.
3) Status akses ditentukan dari kuota dan masa aktif; profil MikroTik disesuaikan.
4) Address-list di MikroTik di-sync (active/fup/habis/expired/inactive) untuk policy.
5) Walled-garden mengizinkan akses portal dan halaman status.
6) Transaksi paket (Midtrans) menambah kuota dan memicu sinkronisasi.
7) Komandan dapat request kuota/unlimited, admin melakukan approval.

Catatan:
- Untuk kasus device belum ada di DB (mis. MAC berubah), auto-login dapat melakukan fallback lewat sesi hotspot MikroTik by IP (best-effort) agar UX tidak putus.

## Untuk Siapa
- Admin/Operator hotspot: mengelola user, paket, transaksi, promo
- End user: login/registrasi, pembelian paket, pembayaran

## Mode Lingkungan
- Development: `docker-compose.yml`
- Production: `docker-compose.prod.yml`

## Template Environment
- Root (Compose-only): `.env.example`
- Frontend dev (public): `.env.public.example` → salin ke `.env.public`
- Frontend prod (public): `.env.public.prod.example` → salin ke `.env.public.prod`
- Backend dev public (non-secret): `backend/.env.public.example` → salin ke `backend/.env.public`
- Backend dev local (secret): `backend/.env.local.example` → salin ke `backend/.env.local`
- Production runtime (backend + db + celery + tunnel): `.env.prod.example` → salin ke `.env.prod`

Catatan dev terbaru:
- Frontend + backend + db + redis + nginx berjalan via `docker-compose.yml`.
- ApexCharts di-load secara async saat chart dipakai.
- Dependensi berat yang tidak dipakai (Tiptap, Chart.js) dihapus.
- Sinkronisasi kuota memakai `/ip/hotspot/host`, akumulasi monotonic, dan auto-enroll device dari ip-binding.
- Sinkronisasi kuota menghitung delta per MAC (Redis) dan pembulatan MB konsisten.
- Pytest backend punya fallback sqlite in-memory saat env DB belum tersedia.

## Dukungan Raspberry Pi (arm64)
Proyek ini bisa berjalan di Raspberry Pi **64-bit (arm64)**.
Image backend/frontend dipublish sebagai **multi-arch** (amd64 + arm64), jadi tidak perlu file override khusus.

Catatan:
- **Pi 32-bit (armv7)** tidak direkomendasikan.
- Build image di Pi lebih lambat.
- Pastikan OS Raspberry Pi 64-bit.

## Akses Layanan (Dev)
- Frontend: http://localhost:3010
- Nginx: http://localhost
- Backend: http://localhost:5010

## Referensi Teknis
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [docs/MIDTRANS_SNAP.md](docs/MIDTRANS_SNAP.md)
