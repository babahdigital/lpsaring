# Devlog: 2026-03-22 — Manual Debt Accuracy and Admin Edit UX

**Tanggal**: 22 Maret 2026  
**Author**: Abdullah (via GitHub Copilot)  
**Scope**: debt manual nominal accuracy, debt auto wording, admin edit dialog UX, mobile touch responsiveness, docs, lint, typecheck, release

---

## Konteks

Batch ini dimulai dari laporan produksi bahwa ringkasan tunggakan manual menampilkan nominal yang lebih rendah dari jumlah item sebenarnya. Contoh kasus nyata: dua item debt manual `20 GB` masing-masing `Rp 200.000` tampil sebagai total `Rp 270.000`, padahal total yang benar adalah `Rp 400.000`.

Setelah root cause backend beres, batch dilanjutkan ke penyempurnaan UX admin agar operator tidak salah mengaktifkan kombinasi `Unlimited` dan `Tunggakan`, serta merapikan tampilan dialog edit user agar konsisten dengan baseline template premium dan tetap proporsional di mobile kecil.

---

## Ringkasan Hasil

- Total nominal debt manual sekarang mengikuti item debt terbuka yang aktual.
- Jalur admin debt report/WA share dipusatkan ke builder bersama agar tidak drift.
- Label debt otomatis diperjelas sebagai `nilai referensi` di notifikasi, PDF, dashboard, dan riwayat.
- Dialog `Edit Pengguna` admin sekarang memakai tab header custom yang lebih proporsional dan mobile-friendly.
- Toggle `Unlimited` dan `Tunggakan Kuota` kini saling eksklusif.
- Selector satuan koreksi kuota SuperAdmin diganti ke tombol biasa yang stabil secara visual.
- Placeholder dropdown paket debt ditambahkan.
- Area `Koreksi Kuota Langsung` dirapikan menjadi kartu operasional yang lebih ringkas dan mudah dibaca.
- Ringkasan `Tunggakan Kuota` sekarang mengikuti pola kartu aksi seperti `Riwayat Mutasi Kuota`, sementara detail lengkap tetap muncul lewat popup khusus.
- Dialog admin yang masih memakai `perfect-scrollbar` kini fallback ke native scroll pada mobile untuk menghilangkan lag sentuhan fullscreen.

---

## 1. Root Cause Nominal Debt Manual Salah

Masalah inti ada di jalur builder report debt manual.

Sebelumnya, total debt manual rupiah diambil dari aggregate `manual_debt_mb`, lalu diterjemahkan lagi ke nominal menggunakan estimator paket termurah aktif. Pendekatan ini salah untuk debt manual yang sebenarnya sudah punya sumber kebenaran lebih baik, yaitu item debt terbuka dengan `price_rp` dan `remaining_rp`.

Akibatnya, total nominal manual bisa lebih rendah atau lebih tinggi dari angka sebenarnya, tergantung hubungan antara jumlah MB total dengan paket termurah aktif saat report dirender.

---

## 2. Perbaikan Backend

### 2.1. Total nominal manual dari item terbuka

`backend/app/services/manual_debt_report_service.py` sekarang:

- membangun `open_items` dari debt manual yang belum lunas,
- menjumlah `remaining_mb` dan `remaining_rp` dari item terbuka,
- memakai total item terbuka itu sebagai sumber nominal manual bila tersedia,
- hanya fallback ke estimator bila item debt lama belum punya nominal tersimpan.

Ini memastikan debt manual bersifat exact-by-record, bukan exact-by-guess.

### 2.2. Admin route diselaraskan

`backend/app/infrastructure/http/admin/user_management_routes.py` tidak lagi memelihara builder debt report lokal yang berpotensi drift. Admin PDF dan WA share sekarang memakai builder bersama yang sama dengan report/reminder user.

### 2.3. Regression coverage

Ditambahkan `backend/tests/test_manual_debt_report_service.py` untuk mengunci dua kasus:

- dua item full-open harus menjumlah exact ke total nominal yang benar,
- item parsial harus mem-prorata `remaining_rp` dengan benar.

---

## 3. Penyelarasan Semantik Auto Debt

Setelah bug nominal manual beres, ditemukan bahwa UI dan template masih berisiko menyesatkan operator karena semua angka rupiah debt terlihat setara, padahal tidak.

Policy yang ditegaskan ulang:

- **debt manual**: nominal aktif boleh dianggap exact bila item debt menyimpan `price_rp`,
- **debt otomatis**: nominal tetap estimasi referensi berbasis paket aktif termurah.

Karena itu wording diubah menjadi:

- `Nilai referensi` untuk auto debt / total reference,
- `Nominal aktif` untuk debt manual bila konteksnya exact-by-record.

Area yang diperbarui:

- `backend/app/notifications/templates.json`
- `backend/app/templates/admin_user_debt_report.html`
- `backend/app/templates/admin_sales_report.html`
- `frontend/pages/dashboard/index.vue`
- `frontend/pages/riwayat/index.vue`

---

## 4. Penyempurnaan Dialog Edit User Admin

User kemudian meminta audit UX untuk dialog `Edit Pengguna`, terutama di area admin quota/debt operations.

### 4.1. Header tab terlalu besar di mobile

Komponen `CustomRadiosWithIcon` yang dipakai sebelumnya terlalu tinggi di mobile kecil dan membuat viewport cepat habis. Solusinya adalah mengganti tab header menjadi button card custom yang:

- tetap 2 kolom di desktop,
- tetap 2 kolom di mobile,
- tetapi punya tinggi lebih pendek di layar kecil,
- menyembunyikan deskripsi panjang di breakpoint kecil agar fokus ke ikon + judul + indikator aktif.

### 4.2. Toggle satuan input SuperAdmin rusak secara visual

`VBtnToggle` untuk pilihan `GB` vs `MB` tidak render baik pada kombinasi density/theme dialog ini. Solusinya: ganti ke dua tombol biasa dengan state aktif yang eksplisit. Hasilnya lebih stabil dan lebih sesuai dengan pola premium template.

### 4.3. Unlimited vs Tunggakan harus saling eksklusif

Secara operasional, admin tidak boleh mudah mengaktifkan `Unlimited` sambil tetap membuka mode `Tunggakan`. Di batch ini, guardrail frontend diperketat:

- saat `Tunggakan` diaktifkan, `Unlimited` langsung dinonaktifkan dan disembunyikan dari alur aktif,
- saat `Unlimited` diaktifkan, mode `Tunggakan` dimatikan dan payload debt dibersihkan,
- kedua switch punya disabled-state dan hint yang menjelaskan kenapa operasi tertentu sedang tidak tersedia.

### 4.4. Placeholder paket debt

Dropdown `Tambah Tunggakan (Pilih Paket)` sekarang menampilkan placeholder `Silakan pilih paket` agar form tidak terasa kosong/ambigu saat pertama dibuka.

### 4.5. Area koreksi kuota terlalu ramai dan repetitif

Setelah batch UX awal, area `Koreksi Kuota Langsung` masih terasa padat karena label, helper, placeholder, dan penjelasan satuan saling mengulang. Ini membuat tombol unit terlihat sempit dan operator harus membaca blok teks yang sebenarnya menjelaskan hal yang sama.

Perbaikannya:

- label `Satuan input:` dihapus,
- penjelasan mode satuan dipusatkan ke satu deskripsi singkat di header kartu,
- nilai kuota saat ini dipindahkan ke kartu statistik `dibeli / terpakai / sisa`,
- field input kini cukup menampilkan contoh input dan satu baris `Saat ini ...`, bukan placeholder plus helper panjang yang duplikatif.

Hasilnya, tombol `GB` dan `MB` punya ruang sentuh yang lebih lega dan alur koreksi lebih cepat dipahami.

### 4.6. Tunggakan kuota dipindah ke pola kartu aksi

Bagian `Tunggakan Kuota` sebelumnya terasa seperti blok status teknis terpisah dari pola dialog lain. Sementara `Riwayat Mutasi Kuota` sudah memakai kartu aksi yang lebih mudah dipindai, area debt masih bergantung pada ikon kecil di header dan detail yang terasa terlalu padat di layar utama.

Perbaikannya:

- ringkasan debt disusun menjadi kartu aksi seragam dengan tombol `Detail Tunggakan`, `PDF`, dan `WhatsApp`,
- tiga angka utama (`total`, `otomatis`, `manual`) dipisah ke stat cards,
- form `Tambah Tunggakan Baru` diberi pengantar sendiri agar operator paham ini adalah langkah lanjutan, bukan bagian dari ringkasan.

Detail ledger tetap memakai popup khusus agar layar utama `Edit Pengguna` tidak berubah menjadi panel analisis yang terlalu panjang.

### 4.7. Mobile lag tidak bisa diselesaikan dengan CSS saja

Audit terhadap warning browser menunjukkan sumber utama lag berasal dari listener `touchstart` dan `wheel` non-passive yang dipasang `perfect-scrollbar`. Karena listener itu dibuat oleh JavaScript library, CSS murni tidak cukup untuk menghilangkan bottleneck interaksi.

Solusi yang dipilih:

- `AppPerfectScrollbar` ditambah jalur `nativeScroll`,
- pada mobile, dialog admin yang relevan menggunakan native scroll container dengan `overflow-y: auto`, `touch-action: pan-y`, dan `-webkit-overflow-scrolling: touch`,
- desktop tetap bisa memakai `perfect-scrollbar` agar perilaku visual tidak berubah di layout besar.

Pola ini diterapkan ke `UserEditDialog`, `UserDetailDialog`, `UserDebtLedgerDialog`, `UserQuotaHistoryDialog`, `ProfileManagerDialog`, dan `UserFilterDialog`.

---

## 5. Responsive Target yang Dijaga

Penyempurnaan dialog admin mengikuti prinsip berikut:

- tidak ada elemen kontrol penting yang pecah ke bentuk tak terbaca di mobile,
- tab atas tetap usable di layar sempit,
- tombol aksi injeksi dan selector satuan tetap bisa disentuh dengan nyaman,
- layout desktop tetap memakai ritme visual premium tanpa berubah jadi tabel sempit atau card terlalu tinggi.

Referensi visual yang dipakai selama audit adalah baseline internal premium template dan mockup ringan pada `dev-lpsaring/coba.html`.

---

## 6. Validasi

Validasi yang dijalankan untuk batch ini:

- backend focused pytest untuk debt report service dan notification templates,
- smoke test backend yang relevan,
- lint frontend untuk file yang disentuh,
- typecheck frontend,
- diagnostics editor untuk file yang diubah.

Batch dokumentasi ini juga disertai lint backend/frontend dan typecheck ulang sebelum release.

---

## 7. Dokumen yang Diperbarui

- `CHANGELOG.md`
- `docs/REFERENCE_PENGEMBANGAN.md`
- `docs/devlogs/README.md`
- `docs/incidents/README.md`
- `docs/incidents/2026-03-22-manual-debt-report-undercount.md`

---

## 8. Pelajaran

1. Debt manual tidak boleh diperlakukan seperti debt auto saat menyusun nominal rupiah.
2. UI admin untuk operasi quota/debt harus meminimalkan kombinasi state yang bisa membuat operator salah langkah.
3. Komponen generic dari template premium tidak selalu cocok untuk semua density/theme; kadang button custom yang sederhana lebih stabil.
4. Responsive mobile pada dialog fullscreen perlu diaudit dengan tinggi nyata, bukan hanya lebar viewport.
5. Jika warning performa berasal dari listener JS pihak ketiga, CSS saja biasanya hanya merapikan gejala, bukan menghapus penyebab utama.