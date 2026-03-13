# Audit Firewall MikroTik 2026-03-14

## Scope

Audit ini membahas RouterOS `R.Utama` pada `10.10.83.1:1983` dengan fokus pada:

- `raw`, `mangle`, `nat`, `filter`
- `address-list`
- `DNS enforcement`
- `PCC / multi-WAN routing`
- `queue` dan keterkaitannya dengan packet mark
- `hotspot walled-garden` dan `ip-binding`

Audit dilakukan read-only melalui SSH. Tidak ada perubahan konfigurasi router yang diterapkan pada sesi ini.

## Model Yang Seharusnya Didukung

Berdasarkan desain backend dan operasi `lpsaring`, model jaringan yang diinginkan adalah:

- aplikasi backend menjadi sumber kebenaran status user
- MikroTik menegakkan policy akses melalui `ip-binding`, `address-list`, profile hotspot, dan firewall
- user `aktif` dan `fup` tetap bisa online normal sesuai profile dan queue
- user `habis` dan `expired` dibatasi, tetapi masih bisa mencapai portal, pembayaran, banking, dan channel recovery yang memang diizinkan
- user `unauthorized` dibatasi sangat ketat, tetapi tetap bisa menuju login portal dan channel OTP/recovery yang diperlukan
- host/server aplikasi, banking, dan domain walled-garden tidak boleh ikut kena drop/pembatasan yang merusak flow bisnis
- pembagian multi-WAN harus tetap tunduk pada pengecualian bisnis seperti banking, game, traffic server, dan akses aplikasi internal

## Ringkasan Hasil

Secara umum desain firewall sudah cukup matang dan jelas diarahkan untuk captive portal berbasis status user. Hal-hal yang sudah kuat:

- enforcement status dipindahkan ke `raw` sehingga drop terjadi sebelum beban conntrack membesar
- `mangle` sudah memetakan `klient_aktif`, `klient_fup`, `klient_habis`, `klient_expired`, dan `unauthorized` ke packet-mark yang konsisten dengan queue
- DNS client dipaksa ke resolver router, lalu DoH dan DoT diblok di `forward`
- policy multi-WAN memakai kombinasi VIP list dan PCC 4:1 yang masuk akal untuk Starlink utama dan Telkom khusus traffic tertentu
- `walled-garden` sudah terhubung ke list bisnis penting: server aplikasi, Midtrans, banking, dan WhatsApp

Tetapi ada beberapa gap nyata yang perlu dirapikan agar firewall benar-benar selaras dengan model bisnis aplikasi.

## Update Re-Audit Setelah Perapihan

Re-audit kedua dilakukan setelah rule firewall dirapikan ulang. Hasilnya, beberapa temuan awal memang sudah tertutup:

- akses `WebFig` dan API RouterOS sudah dipersempit ke interface list `MGT`, tidak lagi terbuka ke seluruh `LIST_LAN`
- `drop invalid` di `forward` sudah aktif
- resolver router sudah memakai lintas vendor (`8.8.8.8` dan `1.1.1.1`)
- pengecualian `Midtrans` sekarang sudah masuk ke `raw` untuk `unauthorized`, `klient_habis`, dan `klient_expired`
- rule NAT bypass lama yang sebelumnya disabled sudah jauh lebih bersih

Masih ada tiga poin yang menurut saya penting pada konfigurasi terbaru.

### 1. `raw` untuk `unauthorized` masih belum selaras penuh dengan `walled-garden`

Saat ini `walled-garden ip` masih mengizinkan:

- `Akses-Banking`
- `walled-garden-midtrans-prod`
- `whatsapp_otp_ips`
- `5222,5223,5228/tcp`

Tetapi `raw` untuk `unauthorized` baru mengecualikan:

- `Bypass_Server`
- `walled-garden-midtrans-prod`
- `whatsapp_otp_ips`
- `5222,5223,5228/tcp`

Artinya, trafik `Akses-Banking` untuk user yang masih `unauthorized` tetap berpotensi dipotong di `raw` sebelum Hotspot sempat mengizinkannya lewat `walled-garden`.

Keputusan yang rapi harus salah satu dari dua ini:

- jika `unauthorized` memang boleh akses aplikasi banking/dompet digital, tambahkan pengecualian `Akses-Banking` di `raw`
- jika `unauthorized` memang tidak boleh akses banking, hapus rule `walled-garden` banking untuk `srv-user` agar policy tidak bertabrakan

Menurut desain bisnis yang sekarang, saya lebih condong menyamakan `raw` dengan `walled-garden`, bukan sebaliknya.

### 2. Extra matcher `hotspot=!auth,!local-dst` di `raw` justru perlu dipertahankan

Untuk rule drop status di `raw`, kombinasi ini benar dan tidak sebaiknya dibuang:

- `hotspot=!auth`
- `hotspot=!local-dst`

Alasannya:

- `!auth` memastikan rule hanya menindak klien yang belum authenticated di hotspot path
- `!local-dst` mencegah router memotong trafik menuju tujuan lokal hotspot lebih awal, misalnya login flow, redirect captive portal, DNS lokal, atau service router yang memang harus tetap bisa dijangkau sebelum auth selesai

Kalau `!local-dst` dihapus dari `raw`, ada risiko login/captive flow ikut kepotong lebih dini.

### 3. Extra matcher serupa tidak wajib di `mangle`

Di `mangle`, rule yang spesifik untuk `unauthorized` saat ini cukup memakai `hotspot=!auth`. Itu masuk akal.

Saya tidak melihat kebutuhan kuat untuk menambahkan `!local-dst` di `mangle`, karena:

- banyak rule `mangle` berada di chain `forward`, sedangkan trafik ke router sendiri bukan jalur `forward`
- sudah ada `return` di `prerouting` untuk `hotspot=!auth`, jadi traffic login/unauth memang sengaja dibypass dari penandaan routing yang tidak perlu

Kesimpulan praktis:

- di `raw`: `!auth,!local-dst` perlu dipertahankan
- di `mangle`: `hotspot=!auth` cukup, `!local-dst` cenderung redundant

### 4. Hubungan `raw` dengan `ip-binding` sudah cukup baik, tapi masih bergantung pada hygiene list backend

Konfigurasi sekarang sudah cocok dengan model backend yang menjadikan `ip-binding` sebagai sinyal trust, bukan matcher langsung di firewall `raw`.

Namun ada konsekuensi penting:

- `raw` tidak membaca `ip-binding` secara langsung
- `raw` hanya membaca `address-list`
- jadi keamanan real tetap bergantung pada sinkronisasi backend yang cepat menghapus IP trusted dari `unauthorized`

Ini bukan salah desain, tetapi artinya drift pada `address-list` tetap bisa membuat device trusted ikut terpukul sementara. Karena itu hygiene `unauthorized` dan job `sync_unauthorized_hosts` tetap menjadi komponen kritis.

### 5. Kebijakan antar VLAN sekarang sudah konsisten, tetapi menjadi lebih permisif

Pada konfigurasi terbaru, dua rule `Cegah Leak LAN ke LAN` sudah `disabled=yes`, sementara rule `Allow Inter-LAN/VLAN` tetap aktif. Jadi kontradiksi lama memang hilang, tetapi hasil akhirnya adalah default inter-LAN allow.

Itu valid jika memang kebutuhan operasional Anda seperti itu. Tetapi dari perspektif keamanan hotspot multi-segmen, ini lebih longgar daripada model default deny + allow exception.

Kalau tidak semua VLAN memang harus saling bicara, model yang lebih aman tetap:

- aktifkan kembali drop antar LAN/VLAN
- buat allow exception yang eksplisit untuk kebutuhan nyata seperti controller, printer, server, atau management

## Snapshot Operasional

Snapshot saat audit:

| Item | Nilai |
|---|---:|
| `klient_aktif` | 82 |
| `klient_fup` | 5 |
| `klient_habis` | 0 |
| `klient_expired` | 0 |
| `klient_blocked` | 0 |
| `unauthorized` live | sekitar 120 |
| `Bypass_Server` | 7 static entries |
| `Bypass_Inet` | 11 static entries |
| `bypass_wartel` | 6 static entries |
| `Akses-Banking` | 75 static entries |
| `walled-garden-midtrans-prod` | 31 static entries |
| `DoH_Servers` | 8 static entries |

Catatan:

- `unauthorized` live diambil dari snapshot `print detail`, bukan hanya `export terse`, karena list itu banyak berisi entry dinamis.
- `queue tree` kosong. Implementasi shaping yang aktif saat ini adalah `simple queue`, bukan `queue tree`.

## Temuan Utama

### 1. Port API RouterOS masih terlalu lebar ke seluruh `LIST_LAN`

Rule input saat ini masih mengizinkan:

- `8728,8729/tcp` dari `in-interface-list=LIST_LAN`
- `80,443/tcp` dari `in-interface-list=LIST_LAN`

Ini terlalu longgar untuk model bisnis aplikasi ini. Backend memang perlu reach router, tetapi yang benar-benar perlu akses hanya:

- Pi / backend / WireGuard management path
- subnet management tertentu

Risiko:

- client LAN biasa bisa mencoba akses API RouterOS atau WebFig
- attack surface router jauh lebih besar dari kebutuhan aplikasi

Rekomendasi:

- batasi `8728/8729` hanya ke subnet management dan host backend yang memang dipakai aplikasi
- batasi `80/443` ke MGT saja kecuali memang ada kebutuhan WebFig dari LAN umum

Prioritas: tinggi.

### 2. Policy pembayaran untuk `habis` / `expired` tidak konsisten antara `raw` dan `walled-garden`

Saat ini ada inkonsistensi penting:

- `walled-garden ip` mengizinkan `walled-garden-midtrans-prod`
- tetapi rule `raw` untuk `klient_habis` dan `klient_expired` hanya memberi pengecualian ke:
  - `Bypass_Server`
  - `Akses-Banking`
  - `whatsapp_otp_ips`
  - `5222,5223,5228/tcp`
- rule filter lama yang eksplisit mengizinkan Midtrans untuk `habis` / `expired` justru `disabled=yes`

Implikasi:

- alur pembayaran atau recovery yang bergantung pada Midtrans bisa rusak sebelum walled-garden sempat membantu, karena `raw` terjadi lebih awal
- desain kebijakan menjadi sulit dipahami karena policy tersebar di dua tempat dan salah satunya sudah tidak aktif

Rekomendasi:

- tetapkan satu sumber enforcement utama untuk `habis` / `expired`
- jika `raw` tetap menjadi enforcement utama, tambahkan Midtrans dan pengecualian recovery yang benar-benar dibutuhkan ke `raw`
- jika ingin policy recovery dikelola oleh `filter`/hotspot, sederhanakan `raw` agar tidak memblok terlalu awal

Prioritas: tinggi.

### 3. Rule `Allow Inter-LAN/VLAN` bertabrakan dengan rule `Cegah Leak LAN ke LAN`

Di `filter` ada dua niat kebijakan yang bertolak belakang:

- `STABIL: Cegah Leak LAN ke LAN`
- `FORWARD: Allow Inter-LAN/VLAN (UniFi etc)`

Urutan saat ini membuat rule drop lebih dulu, lalu rule allow inter-LAN datang belakangan. Dari counter snapshot:

- rule drop leak punya hit
- rule allow inter-LAN bernilai `0`

Interpretasi paling mungkin:

- rule allow inter-LAN saat ini efektifnya mati
- perilaku real router adalah default-segmentation, bukan inter-VLAN open access

Kalau memang tujuan bisnisnya segmentasi ketat, komentar `Allow Inter-LAN/VLAN` menyesatkan. Kalau memang ada VLAN yang harus saling bicara untuk operasional AP/controller/printer/server, pengecualian itu harus dibuat eksplisit sebelum drop, bukan sesudahnya.

Rekomendasi:

- pilih salah satu model secara tegas:
  - segmentasi default deny antar VLAN, lalu allow exception spesifik
  - atau inter-LAN allowed by default
- untuk lingkungan ini, model pertama jauh lebih aman dan lebih cocok

Prioritas: tinggi.

### 4. `Drop Invalid Connections` masih disabled

Rule invalid di `forward` ada, tetapi `disabled=yes`.

Dalam firewall produksi dengan hotspot, multi-WAN, dan NAT, rule invalid biasanya tetap dibutuhkan untuk:

- membersihkan state rusak
- mengurangi noise conntrack
- mencegah traffic aneh lolos ke rule bawah

Memang ada kasus tertentu di hotspot yang membuat invalid drop terlalu agresif. Tetapi status sekarang berarti rule itu tidak memberi manfaat sama sekali.

Rekomendasi:

- uji aktifkan `drop invalid` dalam window observasi pendek
- bila ada false positive pada hotspot path, sempitkan matcher, jangan dibiarkan disabled permanen tanpa alasan operasional tertulis

Prioritas: menengah.

### 5. DNS enforcement kuat, tetapi upstream router masih single-vendor

Kondisi saat ini:

- client DNS dipaksa ke router dengan `dstnat redirect` port `53`
- DoH ke `DoH_Servers` diblok di `forward`
- DoT `853/tcp` diblok di `forward`
- resolver router sendiri memakai `8.8.8.8,8.8.4.4`

Ini sudah kuat dari sisi enforcement. Namun availability masih bergantung pada satu vendor resolver publik.

Risiko:

- kalau Google DNS bermasalah dari salah satu upstream, seluruh hotspot ikut terdampak

Rekomendasi:

- gunakan pasangan upstream lintas vendor, misalnya Google + Cloudflare atau Google + Quad9
- tetap pertahankan redirect ke router dan blok DoH/DoT client

Prioritas: menengah.

### 6. Ada rule NAT bypass lama yang masih disabled dan berpotensi jadi kebingungan jangka panjang

Ada beberapa rule `srcnat accept` yang disabled untuk:

- WireGuard ke VLAN
- WireGuard ke segmen `10.x`
- bypass NAT untuk server

Sementara rule aktif yang sekarang adalah:

- `masquerade` ke `LIST_WAN`
- `masquerade` ke `wireguard-do`
- `masquerade` ke `zerotier1`

Ini bukan bug langsung, tetapi menandakan ada jalur desain lama yang sudah tidak dipakai atau belum diputuskan final.

Rekomendasi:

- audit apakah router-to-server memang harus preserve source asli pada jalur WireGuard
- jika tidak diperlukan, hapus rule disabled agar policy lebih bersih
- jika diperlukan, aktifkan rule bypass yang tepat dan dokumentasikan konsekuensinya

Prioritas: menengah.

### 7. Hygiene list `unauthorized` perlu dipantau

Snapshot live menunjukkan `unauthorized` cukup besar, sekitar `120` entry saat audit.

Itu belum tentu salah, tetapi untuk sistem yang sinkron ke backend secara aktif, jumlah sebesar ini biasanya perlu dijawab dengan salah satu dari dua kemungkinan:

- memang ada populasi perangkat non-login yang tinggi dan itu normal
- atau ada entry dinamis yang tidak cepat bersih

Rekomendasi:

- definisikan SLO operasional untuk `unauthorized`
- bedakan entry baru vs stale dengan TTL/age review
- jika banyak stale, pertimbangkan cleanup policy yang lebih agresif tetapi tetap aman

Prioritas: menengah.

## Yang Sudah Selaras Dengan Aplikasi

### Raw chain

Bagian ini sudah sesuai untuk status-based captive enforcement:

- `inactive`, `blocked`, `unauthorized`, `habis`, `expired` dibatasi sangat awal
- pengecualian server dan recovery channel sudah mulai dipikirkan
- model ini cocok untuk mengurangi beban conntrack dan membuat drop lebih murah di CPU

### Mangle chain

Struktur `mangle` saat ini secara konsep baik:

- bypass local/server/banking terjadi sebelum PCC
- login / hotspot-unauth dibypass dari penandaan routing tertentu
- status user diterjemahkan ke `paket-aktif`, `paket-fup`, `paket-habis`, `paket-whatsapp`
- PCC 4:1 memberi distribusi yang konsisten: `Starlink` empat bucket, `Telkom` satu bucket
- traffic VIP bisa dipaksa ke Telkom atau Starlink sebelum PCC umum berjalan

Untuk model bisnis hotspot, ini masuk akal.

### NAT chain

Desain NAT juga secara umum tepat:

- exception DNS tertentu dipasang sebelum redirect `53`
- redirect DNS ke router ada di bawah exception khusus
- masquerade WAN disatukan dan sederhana

### Queue model

Queue yang aktif sekarang memakai `simple queue` dan bukan `queue tree`. Itu valid dan konsisten dengan packet mark yang ada:

- `paket-whatsapp` untuk unauth recovery
- `paket-habis` untuk habis/expired
- `paket-fup` untuk FUP
- `paket-aktif` untuk user aktif

Untuk hotspot ini, model simple queue masih cukup jelas dan operasionalnya lebih ringan dibanding queue tree yang kompleks.

### Hotspot / walled-garden / ip-binding

Integrasi dengan aplikasi sudah terlihat kuat:

- `ip-binding` memakai comment metadata user dari backend
- `walled-garden` memuat server aplikasi, Midtrans, banking, OTP WhatsApp, dan bypass tertentu
- profile hotspot memisahkan aktif, fup, habis, blokir, unlimited

Ini sangat cocok dengan arsitektur backend `lpsaring`.

## Review Urutan Rule Yang Direkomendasikan

Urutan optimal untuk lingkungan ini sebaiknya seperti berikut.

### 1. Input

- accept established/related
- accept management yang benar-benar perlu
- accept DNS/DHCP/RADIUS yang diperlukan router
- drop new dari WAN
- final drop

### 2. Raw prerouting

- CPU-saver dan bogon/noise dari WAN
- restricted-status policy untuk `blocked`, `unauthorized`, `habis`, `expired`
- semua pengecualian recovery bisnis harus selesai di sini bila raw tetap dipakai sebagai enforcement utama

### 3. Mangle prerouting / forward / postrouting

- bypass local/server/banking dulu
- VIP connection-mark dulu
- PCC setelah VIP
- routing-mark setelah connection-mark
- packet-mark status user
- anti-tethering di postrouting paling akhir

### 4. NAT

- exception DNS atau traffic khusus yang memang harus lolos tanpa redirect
- redirect DNS ke router
- masquerade per uplink/tunnel di paling bawah

### 5. Filter forward

- established/related
- invalid drop
- management isolation
- DoH/DoT block
- allow LAN ke WAN
- allow exception antar-VLAN yang sangat spesifik
- final drop

### 6. Hotspot walled-garden

- hanya memuat portal/recovery/business exception yang benar-benar perlu
- jangan dibiarkan bertentangan dengan raw

## Rekomendasi Perubahan Bertahap

### Tahap 1

- restriksi `8728/8729` dan `80/443` ke MGT + host backend saja
- dokumentasikan subnet/host mana saja yang memang boleh mengelola router

### Tahap 2

- selaraskan policy `raw` vs `walled-garden` untuk `habis` / `expired` / `unauthorized`
- putuskan dengan jelas apakah Midtrans harus diizinkan pada fase restricted

### Tahap 3

- rapikan kontradiksi `Allow Inter-LAN` vs `Cegah Leak`
- ubah ke model `default deny antar VLAN + explicit allow` bila itu memang niat bisnis

### Tahap 4

- evaluasi aktifkan `drop invalid`
- review stale disabled NAT rules
- review health dan aging list `unauthorized`

### Tahap 5

- tambah resiliency DNS upstream router
- review apakah ada list bisnis yang terlalu besar, terlalu umum, atau terlalu cepat stale

## Kesimpulan

Firewall MikroTik ini bukan firewall yang acak. Fondasinya sudah cukup bagus dan secara konsep cocok dengan model bisnis `lpsaring`: captive portal berbasis status, recovery terbatas, bypass server aplikasi, dan multi-WAN dengan policy exception.

Masalah utamanya bukan ketiadaan desain, tetapi konsistensi antar-layer enforcement:

- `raw` vs `walled-garden`
- segmentation drop vs allow inter-VLAN
- exposure input management yang masih terlalu luas
- beberapa rule disabled lama yang membuat intent arsitektur tidak lagi bersih

Jika dirapikan di empat titik itu, firewall ini bisa menjadi jauh lebih stabil, lebih aman, dan lebih mudah dipelihara tanpa mengubah filosofi jaringan yang sudah ada.