# Struktur Auth Routes

## Ringkasan

Direktori ini berisi semua route terkait autentikasi yang telah dipisahkan berdasarkan tanggung jawabnya:

1. **public_auth_routes.py** - Rute publik untuk registrasi dan verifikasi OTP
2. **session_routes.py** - Manajemen sesi: login admin, logout, refresh token, me
3. **device_routes.py** - Otentikasi perangkat: deteksi, sinkronisasi, otorisasi
4. **utility_routes.py** - Endpoint utilitas untuk debugging dan monitoring

## Keuntungan Struktur Ini

* **Modularitas**: Setiap file memiliki tanggung jawab yang jelas dan terfokus
* **Keterbacaan**: File yang lebih kecil lebih mudah dipahami dan dimodifikasi
* **Pemeliharaan**: Perubahan dapat dilokalisasi ke komponen yang tepat
* **Skalabilitas**: Mudah menambahkan fitur baru dengan menambahkan file baru

## Cara Menggunakan

Semua blueprint didaftarkan dengan prefix `/api` sehingga endpoint dapat diakses dengan URL:

* `/api/auth/register` - Registrasi user (public_auth_bp)
* `/api/auth/request-otp` - Request OTP (public_auth_bp)
* `/api/auth/verify-otp` - Verifikasi OTP (public_auth_bp)
* `/api/auth/me` - Informasi user saat ini (session_bp)
* `/api/auth/sync-device` - Sinkronisasi perangkat (device_bp)
* `/api/auth/authorize-device` - Otorisasi perangkat (device_bp)

## Catatan

Struktur ini adalah refactoring dari `auth_routes.py` yang asli. Blueprint lama (`auth_bp`) tetap dipertahankan untuk kompatibilitas dengan kode yang ada, tetapi secara bertahap akan digantikan oleh blueprint baru.
