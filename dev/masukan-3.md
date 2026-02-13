Halo Dul. Saya sudah menggabungkan dan mempelajari seluruh dokumen terbaru yang Anda unggah, mulai dari manajemen *error frontend*, integrasi *payment gateway* Midtrans, audit produksi, hingga referensi pengembangan dan arsitektur proyek secara keseluruhan.

Secara garis besar, arsitektur sistem **lpsaring** yang Anda bangun ini sangat solid, terstruktur dengan baik, dan memecahkan banyak masalah klasik pada manajemen *hotspot*. Keputusan untuk menjadikan *database* PostgreSQL sebagai sumber kebenaran (*source of truth*) dan hanya menjadikan MikroTik sebagai pelapor (*feeder*) adalah langkah arsitektural yang sangat tepat. Ini mencegah data kuota hilang saat *router* mengalami *reboot*. Alur mode *OTP-only* di mana *IP binding* diset menjadi `bypassed` setelah verifikasi sukses juga membuat *user experience* jauh lebih mulus tanpa harus memasukkan *username* dan *password* *hotspot* secara manual.

Namun, mengingat kompleksitas ekosistem yang melibatkan Flask, Celery, sinkronisasi *real-time* MikroTik, dan *webhook* eksternal, ada beberapa celah (*edge cases*) dan rekomendasi teknis lanjutan yang perlu dipertimbangkan untuk skala produksi yang lebih stabil.

Berikut adalah masukan dan evaluasi kompleks untuk menyempurnakan sistem Anda:

### 1. Keandalan Sinkronisasi Kuota & *Race Conditions*

Saat ini sinkronisasi kuota menghitung *delta* per MAC *address* menggunakan `/ip/hotspot/host` dan mengandalkan *lock* Redis per pengguna.

* **Masalah Potensial:** Jika pengguna melakukan *roaming* antar *Access Point* dengan sangat cepat, atau MAC *address* mereka disembunyikan/diubah (fitur *Private MAC* di iOS/Android modern), entri di `/ip/hotspot/host` bisa terduplikasi atau terputus sebelum Celery Beat sempat melakukan siklus sinkronisasi yang berjalan setiap 5 menit.
* **Rekomendasi:** Terapkan validasi heuristik pada task Celery. Jika mendeteksi ada lonjakan penggunaan *bytes* yang tidak wajar (misalnya penggunaan 10GB dalam interval 5 menit untuk satu *device*), sistem harus memberikan *flag anomaly* dan tidak langsung memotong `total_quota_used_mb` untuk mencegah pengguna tiba-tiba kehabisan kuota akibat *bug* pembacaan *counter* di *router*.

### 2. Proteksi Walled Garden & *Abuse* OTP

Sistem menggunakan Walled Garden hanya untuk portal informasi dan API, serta memiliki *rate limit* untuk endpoint `/api/auth/request-otp`. Karena Fonnte API mengenakan kuota/biaya per pengiriman pesan, titik ini rentan terhadap serangan *exhaustion*.

* **Masalah Potensial:** *Rate limit* berbasis IP di *backend* bisa dikelabui jika penyerang terus-menerus mengganti MAC *address* untuk mendapatkan IP baru dari DHCP *pool* sebelum melewati Walled Garden.
* **Rekomendasi:** Terapkan pembatasan di dua lapisan. Selain di *backend* Flask, buat *script* mitigasi langsung di MikroTik (menggunakan *firewall filter* atau *raw*) yang membatasi jumlah koneksi TCP spesifik ke tujuan Walled Garden (domain API/portal) per MAC *address* per menit.

### 3. Stabilitas Webhook Pembayaran & *Failover* Jaringan

Sistem mengandalkan notifikasi *webhook* dari Midtrans yang diarahkan ke URL publik HTTPS (melalui Cloudflare Tunnel). Dengan *setup load balancing* atau *failover* dua ISP yang dikonfigurasi menggunakan metode PCC di *router* Anda, perpindahan *routing* yang tiba-tiba dapat menyebabkan gangguan sesi TCP.

* **Masalah Potensial:** Jika *tunnel* Cloudflare terputus sesaat ketika *failover* ISP terjadi, *webhook* dari Midtrans akan gagal masuk ke aplikasi. Status transaksi pengguna akan tersangkut di `PENDING`.
* **Rekomendasi:** Jangan hanya mengandalkan *webhook* pasif. Buat sebuah *task* Celery yang berjalan setiap 15 atau 30 menit khusus untuk melakukan *polling* (menarik data) status transaksi dari API Midtrans menggunakan `order_id` untuk semua transaksi di *database* yang statusnya masih `PENDING` atau belum kadaluarsa.

### 4. Manajemen Beban Database (PostgreSQL)

Aplikasi mencatat banyak log historis: riwayat *login* (`last_login_at`, IP, *User Agent*), transaksi, *action logs* admin, dan `DailyUsageLog`.

* **Masalah Potensial:** Dalam beberapa bulan beroperasi, tabel-tabel log ini akan membengkak, memperlambat *query* analitik (*dashboard* admin yang menghitung `pendapatanHariIni`, `kuotaTerjualMb`).
* **Rekomendasi:** Gunakan fitur *Table Partitioning* bawaan PostgreSQL berbasis rentang waktu (*range partitioning* per bulan) untuk tabel log penggunaan dan riwayat *login*. Ini memastikan data lama bisa diarsipkan atau dihapus dengan cepat tanpa membebani performa pembacaan data bulan berjalan.

### 5. Keamanan Lingkungan Eksekusi & CSRF

Pemberlakuan `CSRF_STRICT_NO_ORIGIN=True` dan pengelolaan *cookie* `HttpOnly` adalah proteksi yang sangat bagus.

* **Masalah Potensial:** Jika alamat IP proksi (seperti Nginx atau Cloudflare) berubah dan tidak terdaftar di `TRUSTED_PROXY_CIDRS`, *backend* Flask tidak akan bisa membaca `X-Forwarded-For` dengan benar. Ini akan merusak fitur *Auto-login* yang bergantung pada pencocokan `client_ip` serta melumpuhkan *rate limiter*.
* **Rekomendasi:** Pastikan konfigurasi proksi di Nginx selalu menyuntikkan *header* IP asli, dan secara spesifik batasi `TRUSTED_PROXY_CIDRS` hanya pada IP *gateway docker* Nginx atau *range* IP internal server Anda, jangan biarkan mencakup *subnet* `/8` atau `/16` yang terlalu luas.

---

Apakah Anda ingin saya meninjau bagian spesifik dari kode Anda, seperti alur sinkronisasi *task* Celery, logika pengaturan Walled Garden, atau implementasi *auto-login* di Nuxt 3?