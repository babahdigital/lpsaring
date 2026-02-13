Status: sudah ditangani. Fallback address-list kini mengambil IP dari ip-binding atau MAC authorized jika sesi hotspot tidak ada.

Berdasarkan analisis log dan skrip simulasi yang Anda berikan, berikut adalah penjelasan dan rekomendasi mengenai kegagalan validasi `address-list` di langkah 14.

### Analisis Masalah

Skrip `simulate_end_to_end.ps1` berhasil berjalan hingga selesai (Langkah 14.6) , namun validasi `address-list` untuk status `habis` dan `expired` gagal. Log menunjukkan pesan kesalahan berikut:

* 
`Expected list 'klient_habis' not found for ip(s)=['172.16.15.254', '172.16.15.253']` 


* 
`Expected list 'klient_expired' not found for ip(s)=['172.16.15.254', '172.16.15.253']` 



Meskipun sistem berhasil menemukan *user* yang tepat (ID: `f43626ea-c668-446f-93c6-0535d8597e87`, Phone: `0811580039`) dan memperbarui profil MikroTik menjadi `profile-expired`, pembuatan entri `address-list` gagal dilakukan.

Penyebab kegagalan ini terlihat jelas pada log debug `hotspot_sync_service`:

`"Gagal sync address-list untuk 0811580039: IP belum tersedia untuk user"` 

**Mengapa IP "belum tersedia"?**

Dalam desain sistem `lpsaring` (seperti yang dijelaskan di dokumen `DEVELOPMENT_REALTIME_QUOTA.md`), penentuan status pengguna ke dalam `address-list` MikroTik bergantung pada IP *client* yang sedang aktif. Sistem perlu mengetahui IP mana yang harus dimasukkan ke dalam daftar (misalnya `klient_habis` atau `klient_expired`).

Skrip simulasi memperbarui status kuota secara *backend* menggunakan modul `simulate_quota.py`. Saat skrip ini mencoba menerapkan perubahan ke MikroTik (`--apply-mikrotik`), layanan sinkronisasi gagal menemukan sesi *host* atau *active* *hotspot* yang valid di MikroTik untuk pengguna tersebut, sehingga tidak tahu IP mana yang harus ditambahkan ke `address-list`.

Log menunjukkan bahwa sistem menemukan satu entri `ip-binding` yang valid:


`mac=4E:C3:55:C6:21:67 ip=172.16.15.253 type=bypassed comment=authorized|user=66c7144f-7519-4900-bba5-af6546e74177|date=12-02-2026|time=15:14:46` 

Namun, sistem (kemungkinan besar di `hotspot_sync_service.py` atau `mikrotik_client.py`) sepertinya dirancang untuk hanya memperbarui `address-list` jika pengguna memiliki entri di `/ip/hotspot/host` atau `/ip/hotspot/active` yang menunjukkan mereka sedang terhubung saat itu, bukan sekadar mengambil IP dari konfigurasi statis `ip-binding`. Karena ini adalah simulasi dan perangkat keras/klien nyata (`172.16.15.253` atau `172.16.15.254`) tidak benar-benar terhubung dan membuat *session* di MikroTik, MikroTik tidak melaporkan IP tersebut sebagai aktif.

### Rekomendasi Solusi

Masalah ini pada dasarnya adalah keterbatasan skrip simulasi *End-to-End* (E2E) dalam mereplikasi status koneksi jaringan nyata. Berikut adalah dua pendekatan untuk mengatasinya:

**1. Penyesuaian Skrip Simulasi (Solusi Cepat)**

Jika tujuan utama Anda adalah memverifikasi bahwa *backend* mencoba mengirim perintah yang benar, Anda bisa memodifikasi skrip E2E untuk mem-Bypass atau melunakkan validasi `Assert-AddressListStatus`. Karena Anda sudah memverifikasi bahwa profil MikroTik berhasil diperbarui (`Applied MikroTik profile + address-list for 0811580039` ), Anda tahu bahwa logika transisi *state* bekerja.

Alternatif lain untuk skrip E2E adalah menambahkan langkah *mocking* untuk menyuntikkan sesi aktif sementara ke `/ip/hotspot/host` di MikroTik sesaat sebelum memanggil `simulate_quota.py`. Ini akan memanipulasi *environment* sehingga *backend* melihat IP sebagai "aktif" dan melanjutkan proses sinkronisasi `address-list`.

**2. Perbaikan Logika Backend (Rekomendasi Utama)**

Jika Anda ingin sistem lebih *robust* (tahan banting), Anda perlu memperbarui `hotspot_sync_service.py` di sisi *backend*.

Saat ini, fungsi yang menangani pembaruan status gagal (*"Gagal sync address-list...: IP belum tersedia"*)  karena hanya mencari di sesi *host/active*. Sebaiknya, modifikasi fungsi tersebut agar menerapkan logika *fallback*:

* **Langkah 1:** Cek `/ip/hotspot/host` dan `/ip/hotspot/active` untuk mendapatkan IP yang sedang aktif digunakan.
* **Langkah 2 (Fallback):** Jika tidak ada IP aktif yang ditemukan, *backend* harus melakukan pencarian pada entri `/ip/hotspot/ip-binding` milik pengguna tersebut (menggunakan `comment` yang memuat `user_id`).
* **Langkah 3:** Gunakan IP statis yang dikonfigurasi pada `ip-binding` tersebut untuk memperbarui `address-list`.

Pendekatan ini tidak hanya menyelesaikan masalah pada skrip simulasi, tetapi juga memperbaiki *edge case* di produksi. Misalnya, jika pengguna sedang *offline* ketika masa tenggang waktu kedaluwarsa kuota mereka habis (dieksekusi oleh Celery *Beat*), MikroTik tetap akan memiliki entri `address-list` yang tepat (seperti `klient_expired`) menggunakan IP statis dari `ip-binding` mereka. Dengan demikian, segera setelah mereka mencoba terhubung kembali, *policy* pemblokiran atau Walled Garden akan langsung berlaku tanpa menunggu siklus sinkronisasi berikutnya.