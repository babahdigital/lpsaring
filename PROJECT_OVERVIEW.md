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
2) OTP diverifikasi; backend menentukan IP/MAC dan membuat ip-binding + device record.
3) Status akses ditentukan dari kuota dan masa aktif; profil MikroTik disesuaikan.
4) Address-list di MikroTik di-sync (active/fup/habis/expired/inactive) untuk policy.
5) Walled-garden mengizinkan akses portal dan halaman status.
6) Transaksi paket (Midtrans) menambah kuota dan memicu sinkronisasi.
7) Komandan dapat request kuota/unlimited, admin melakukan approval.

## Untuk Siapa
- Admin/Operator hotspot: mengelola user, paket, transaksi, promo
- End user: login/registrasi, pembelian paket, pembayaran

## Mode Lingkungan
- Development: `docker-compose.yml` + `docker-compose.dev.yml`
- Production: `docker-compose.prod.yml`

Catatan dev terbaru:
- Frontend Nuxt berjalan di host (port 3010).
- Backend + Redis + DB + Nginx berjalan di Docker (lihat `docker-compose.dev.yml`).
- ApexCharts di-load secara async saat chart dipakai.
- Dependensi berat yang tidak dipakai (Tiptap, Chart.js) dihapus.
- Sinkronisasi kuota memakai `/ip/hotspot/host`, akumulasi monotonic, dan auto-enroll device dari ip-binding.
- Sinkronisasi kuota menghitung delta per MAC (Redis) dan pembulatan MB konsisten.
- Pytest backend punya fallback sqlite in-memory saat env DB belum tersedia.

## Dukungan Raspberry Pi (arm64)
Proyek ini bisa berjalan di Raspberry Pi **64-bit (arm64)** menggunakan image multi-arch Docker Hub.

Jalankan production compose biasa:
- `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d`

Catatan:
- **Pi 32-bit (armv7)** tidak direkomendasikan.
- Pastikan OS Raspberry Pi 64-bit.

## Akses Layanan (Dev)
- Frontend: http://localhost:3010
- Nginx: http://localhost
- Backend: http://localhost:5010

## Referensi Teknis
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [docs/MIDTRANS_SNAP.md](docs/MIDTRANS_SNAP.md)
