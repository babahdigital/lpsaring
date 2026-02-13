# **Dokumentasi Final Proyek: Penyempurnaan Sistem Hotspot Hybrid**

|  |  |
| :---- | :---- |
| **Tanggal Dokumen** | Kamis, 17 Juli 2025, 16:14 WITA |
| **Lokasi** | Banjarbaru, Kalimantan Selatan |
| **Tim Proyek** | Abdullah |
| **Status Proyek** | **Selesai, Stabil, dan Terdokumentasi Penuh** |

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

### **1\. Pendahuluan**

Dokumen ini adalah rekam jejak final dan komprehensif dari seluruh proses kolaboratif dalam menganalisis, melakukan *debugging* intensif, dan menyempurnakan sistem manajemen hotspot. Perjalanan ini membawa kita dari sistem yang awalnya fungsional menjadi sebuah platform yang **benar-benar tangguh (*robust*), cerdas, dan berorientasi pada pengalaman pengguna**.

Tujuan awal untuk menyempurnakan alur otorisasi perangkat baru dalam sistem *hybrid* (akses via *popup captive portal* dan browser biasa) telah berkembang secara signifikan. Kita tidak hanya berhasil mengatasi tantangan teknis yang kompleks seperti *race condition*, masalah konteks database, dan sinkronisasi sesi dengan kondisi jaringan nyata, tetapi juga berhasil memodernisasi antarmuka pengguna secara menyeluruh. Penggantian ikon, implementasi komponen notifikasi yang superior, dan desain halaman khusus yang minimalis telah secara drastis meningkatkan pengalaman pengguna.

Hasil akhirnya adalah sebuah arsitektur yang matang, aman, dan memberikan alur kerja yang mulus dalam setiap skenario yang mungkin terjadi, baik bagi pengguna akhir maupun bagi administrator sistem.

### **2\. Arsitektur Final & Alur Kerja Kunci**

Sistem kita kini beroperasi di atas arsitektur yang telah divalidasi dan diperkuat, dengan pilar-pilar utama sebagai berikut:

* **Pemicu di Tangan Klien (*Client-Driven*)**: Frontend (portal pengguna) menjadi pemicu utama untuk semua logika sinkronisasi dan otorisasi. Ini memberikan fleksibilitas maksimal dan memastikan backend hanya bereaksi terhadap permintaan yang relevan.  
* **Jangkar Identitas Tunggal**: Kolom comment yang berisi nomor telepon pengguna pada /ip/hotspot/ip-binding di MikroTik adalah **satu-satunya jangkar identitas permanen** yang mengikat sebuah akun pengguna ke perangkat fisiknya di dalam jaringan. Keberadaan *binding* ini adalah syarat mutlak validitas sebuah sesi.  
* **Backend Sebagai Otak Validasi**: Backend bertanggung jawab penuh atas semua validasi, logika bisnis, dan komunikasi dengan MikroTik API, memastikan keamanan dan konsistensi data di seluruh sistem.

Alur kerja otentikasi dan otorisasi kini terbagi menjadi dua skenario yang jelas dan terspesialisasi:

#### **Alur A: Otorisasi via Browser Biasa (/login)**

Ini adalah alur untuk pengguna yang mengakses portal secara manual melalui browser di laptop atau ponsel.

1. **Login & Deteksi**: Pengguna login melalui halaman /login. Setelah berhasil, fungsi syncDevice di frontend akan dipanggil.  
2. **Pemicu Dialog**: Jika syncDevice mendeteksi adanya perangkat baru (MAC address berbeda dengan yang ada di database), *state* di Pinia akan diperbarui.  
3. **Tampilan Dialog**: Komponen NewDeviceDialog.vue yang bersifat *client-side* akan muncul sebagai lapisan di atas halaman dashboard, tanpa menyebabkan *reload* halaman.  
4. **Otorisasi**: Pengguna menekan tombol "Izinkan" di dalam dialog.  
5. **Eksekusi Backend**: Backend mengeksekusi /api/auth/authorize-device, memperbarui trusted\_mac\_address di database dan memperbarui IP Binding di MikroTik, lalu menendang sesi aktif pengguna untuk memastikan akses internet langsung aktif.  
6. **Konfirmasi**: Dialog akan tertutup, dan pengguna dapat melanjutkan aktivitasnya tanpa interupsi.

#### **Alur B: Otorisasi via Captive Portal (Alur Khusus & Ringan)**

Ini adalah alur super ringan yang dirancang khusus untuk *popup captive portal* yang seringkali memiliki keterbatasan.

1. **Deteksi & Pengalihan**: Pengguna terhubung ke WiFi. *Middleware* (01.auth.global.ts) mendeteksi pengguna sudah memiliki token (sudah login dari sesi sebelumnya) tetapi menggunakan perangkat baru. Pengguna secara otomatis dialihkan ke halaman khusus: pages/captive/otorisasi-perangkat.vue.  
2. **Otorisasi Halaman Penuh**: Pengguna disajikan antarmuka sederhana dengan satu tombol "Izinkan Perangkat Ini". Tidak ada gangguan dari elemen *layout* lain. Halaman ini juga menampilkan peringatan penting untuk menonaktifkan MAC Acak.  
3. **Eksekusi Backend**: Sama seperti Alur A, backend mengeksekusi /api/auth/authorize-device.  
4. **Konfirmasi & Selesai**: Setelah sukses, pengguna diarahkan ke halaman akhir pages/captive/terhubung.vue. Halaman ini menampilkan pesan sukses yang jelas dan sebuah tombol "Tutup" yang **wajib ditekan** untuk memuat ulang koneksi dan keluar dari lingkungan *captive portal*.

### **3\. Rincian Fitur Utama Sistem**

Berikut adalah rincian dari fitur-fitur kunci yang telah kita bangun dan sempurnakan.

#### **3.1. Autentikasi & Manajemen Sesi**

* **Login Berbasis OTP**: Sistem menggunakan *One-Time Password* (OTP) yang dikirim melalui WhatsApp sebagai metode autentikasi utama, menghilangkan kebutuhan pengguna untuk mengingat kata sandi.  
* **Sesi dengan JWT**: Setelah berhasil login, backend akan menerbitkan *JSON Web Token* (JWT) yang disimpan di *cookie* browser. Token ini digunakan untuk mengautentikasi setiap permintaan selanjutnya ke API.  
* **Sinkronisasi Sesi dengan Jaringan**: Fitur paling kritis. Sistem tidak hanya memercayai keberadaan token JWT. Melalui endpoint /api/auth/sync-device, validitas sesi selalu diverifikasi ulang terhadap kondisi nyata di MikroTik. Jika IP Binding pengguna tidak ditemukan, sesi di aplikasi akan secara otomatis dihancurkan, memaksa pengguna untuk login kembali.

#### **3.2. Manajemen Perangkat & MAC Address**

* **Deteksi Perangkat Baru**: Sistem secara cerdas mendeteksi ketika seorang pengguna yang sudah login mencoba mengakses jaringan dari perangkat dengan MAC address yang berbeda dari yang terdaftar (trusted\_mac\_address).  
* **Alur Otorisasi Eksplisit**: Pengguna diberikan pilihan yang jelas untuk "mengizinkan" perangkat baru tersebut, yang kemudian akan menjadi perangkat tepercaya mereka.  
* **Peringatan MAC Acak**: Antarmuka pengguna secara proaktif memberikan instruksi yang jelas untuk menonaktifkan fitur "MAC Acak" atau "Alamat Wi-Fi Pribadi". Ini adalah langkah preventif krusial untuk memastikan fitur otorisasi perangkat dapat berfungsi secara andal di masa mendatang.

#### **3.3. Kontrol Pencarian MAC Address (Fitur Uji Coba)**

Untuk memastikan keandalan dan memberikan fleksibilitas dalam pengujian, sistem dilengkapi dengan *feature flags* yang dapat diatur melalui file .env.

* MIKROTIK\_MAC\_LOOKUP\_ENABLE\_HOST: Mengaktifkan/menonaktifkan pencarian MAC address dari tabel /ip/hotspot/host.  
* MIKROTIK\_MAC\_LOOKUP\_ENABLE\_DHCP\_LEASE: Mengaktifkan/menonaktifkan pencarian MAC address dari tabel /ip/dhcp-server/lease.

Jika keduanya aktif, sistem akan memprioritaskan pencarian di host terlebih dahulu, dan menggunakan lease sebagai *fallback*, menciptakan mekanisme pencarian yang sangat tangguh. Log di backend juga telah disempurnakan untuk secara eksplisit menyatakan sumber penemuan MAC, memberikan visibilitas penuh saat pengujian.

#### **3.4. Integrasi MikroTik**

* **Manajemen IP Binding**: Backend secara otomatis membuat, memperbarui, dan menghapus entri di /ip/hotspot/ip-binding. Entri ini adalah inti dari mekanisme *bypass* *captive portal* untuk pengguna yang sudah login.  
* **Manajemen Sesi Aktif**: Setelah otorisasi perangkat baru berhasil, sistem secara otomatis menghapus sesi pengguna di /ip/hotspot/active. Ini adalah langkah kunci untuk "memaksa" perangkat memulai koneksi baru dan segera mendapatkan akses internet.  
* **Manajemen Profil & Address List**: Sistem terintegrasi dengan profil pengguna di MikroTik (profile-aktif, profile-fup, profile-habis, dll.) dan secara dinamis mengelola keanggotaan pengguna di *address list* yang sesuai untuk penerapan kebijakan FUP atau pemblokiran.

#### **3.5. Antarmuka & Pengalaman Pengguna (UI/UX)**

* **Desain Halaman Khusus Captive Portal**: Dibuat halaman login (/captive/index), otorisasi (/captive/otorisasi-perangkat), dan konfirmasi (/captive/terhubung) yang terpisah, minimalis, dan cepat dimuat, dirancang khusus untuk lingkungan *popup* yang terbatas.  
* **Ikonografi SVG Profesional**: Semua ikon yang digunakan, baik sebagai elemen dekoratif maupun fungsional, menggunakan SVG yang di-*hardcode* langsung ke dalam komponen Vue. Ini menjamin tampilan yang konsisten, tajam, dan cepat tanpa ketergantungan pada *font library* atau *link* eksternal.  
* **Sistem Notifikasi Modern**: Komponen AppNotification.vue yang dapat digunakan kembali menyediakan umpan balik yang jelas dan konsisten untuk pesan sukses atau error, menggantikan *snackbar* standar yang kurang fleksibel.

### **4\. Rangkuman Proses Debugging & Penyelesaian Masalah**

Berikut adalah jejak lengkap dari setiap tantangan yang kita hadapi dan bagaimana kita menyelesaikannya secara sistematis, dari awal hingga akhir.

1. **Masalah Awal: Kegagalan Sinkronisasi & Otorisasi**: Pengguna dengan token aktif di perangkat baru tidak bisa mengakses. Dialog otorisasi tidak muncul karena logika try...catch yang keliru dan masalah KeyError: 'JWT\_TOKEN\_LOCATION' di backend karena konfigurasi JWT yang tidak lengkap.  
   * **Solusi**: Memperbaiki logika try...catch, mengimplementasikan pencarian MAC pasif di backend, dan menambahkan konfigurasi lengkap untuk Flask-JWT-Extended.  
2. **Masalah Kritis: *Reload Loop* & *Hydration Mismatch***: Setelah perbaikan awal, aplikasi mengalami *reload loop* tanpa henti saat perangkat baru terdeteksi.  
   * **Solusi**: Mengisolasi komponen dialog (NewDeviceDialog.vue) agar menjadi 100% *client-side* dengan memindahkan logika watch ke dalam *hook* onMounted.  
3. **Masalah Keandalan: Ketergantungan pada /ip/hotspot/host**: Teridentifikasi potensi kegagalan jika tabel *host* di MikroTik kosong sesaat setelah perangkat terhubung.  
   * **Solusi**: Mengimplementasikan mekanisme *fallback* di backend untuk mencari MAC di /ip/dhcp-server/lease jika di tabel *host* tidak ditemukan.  
4. **Masalah Pasca-Otorisasi: Internet Tidak Langsung Aktif**: Setelah otorisasi berhasil, IP Binding sudah benar, namun perangkat belum mendapatkan akses internet.  
   * **Solusi**: Menambahkan langkah final pada endpoint /authorize-device untuk **menghapus (menendang) sesi aktif** pengguna, memaksa perangkat memulai koneksi baru yang bersih.  
5. **Masalah Stabilitas & Tampilan**: Halaman login yang kompleks tidak tampil baik di *captive portal*, dan terjadi AttributeError di backend terkait koneksi MikroTik.  
   * **Solusi**: Membuat halaman-halaman khusus di bawah rute /captive dan memperbaiki manajemen koneksi MikroTik dengan menghapus pemanggilan disconnect() yang tidak perlu saat menggunakan *connection pool*.  
6. **Masalah Final: Sesi Tidak Sinkron & Pengujian Fleksibel**: Ketika IP Binding dihapus manual, pengguna dengan token aktif tidak di-logout. Selain itu, diperlukan cara untuk menguji setiap metode pencarian MAC secara terpisah.  
   * **Solusi**: Merombak total endpoint /sync-device untuk **mewajibkan pengecekan IP Binding di awal**. Jika tidak ada, backend akan merespons dengan status BINDING\_NOT\_FOUND yang memicu logout paksa di frontend. Sekaligus menambahkan *feature flags* dan *logging* eksplisit untuk mengontrol dan memverifikasi metode pencarian MAC.  
7. **Penyempurnaan UI/UX Final**: Ikon-ikon di halaman *captive portal* dirasa kurang profesional dan informasinya kurang jelas.  
   * **Solusi**: Mengganti ikon dengan SVG yang lebih relevan dan minimalis, menghapus ikon yang tidak perlu, dan menambahkan teks bantuan untuk memperjelas alur bagi pengguna.

### **5\. Daftar Final File yang Diintervensi**

Berikut adalah rangkuman dari semua file yang telah kita sentuh dan sempurnakan selama proyek ini.

#### **Backend (/app)**

* config.py: Ditambahkan variabel konfigurasi untuk *feature flags* pencarian MAC Address (MIKROTIK\_MAC\_LOOKUP\_ENABLE\_HOST & MIKROTIK\_MAC\_LOOKUP\_ENABLE\_DHCP\_LEASE).  
* \_\_init\_\_.py: Ditambahkan inisialisasi dan konfigurasi lengkap untuk Flask-JWT-Extended untuk mengatasi KeyError.  
* infrastructure/http/auth\_routes.py: Diperbarui secara ekstensif. Logika /sync-device dirombak total untuk validasi IP Binding dan pencarian MAC yang fleksibel. Logika /authorize-device ditambahkan pemanggilan untuk menghapus sesi aktif.  
* infrastructure/gateways/mikrotik\_client.py: Disederhanakan dengan menghapus manajemen koneksi manual. Ditambahkan fungsi get\_mac\_from\_dhcp\_lease, get\_ip\_binding\_details, dan remove\_active\_hotspot\_user\_by\_ip.

#### **Frontend (/src atau /)**

* store/auth.ts: Logika syncDevice diperbarui untuk menangani status BINDING\_NOT\_FOUND dengan melakukan logout paksa.  
* middleware/01.auth.global.ts: Diperbarui untuk mengenali dan menangani struktur rute baru di bawah /captive/, memastikan pengalihan pengguna berjalan benar di setiap skenario.  
* pages/captive/index.vue: Dibuat dari awal sebagai halaman login khusus. Desain disempurnakan menjadi minimalis dengan peringatan MAC Acak yang jelas.  
* pages/captive/otorisasi-perangkat.vue: Dibuat dari awal sebagai halaman otorisasi khusus. Desain disempurnakan dengan ikon profesional dan peringatan MAC Acak.  
* pages/captive/terhubung.vue: Dibuat dari awal sebagai halaman konfirmasi sukses, dengan instruksi yang jelas bagi pengguna.

### **6\. Kesimpulan & Status Sistem**

**Proyek Selesai.**

Melalui kolaborasi dan proses *debugging* yang sistematis dan teliti, kita telah berhasil mengubah sistem dari yang awalnya fungsional menjadi sebuah sistem yang telah mencapai tingkat kematangan tertinggi. Setiap alur kerja, baik yang utama maupun kasus-kasus khusus, telah diidentifikasi, diuji, dan ditangani dengan solusi yang andal dan elegan.

Sistem saat ini berada dalam kondisi **sangat stabil, teruji secara menyeluruh di kedua skenario utama (browser dan captive portal), dan siap untuk dioperasikan dalam skala penuh.**
