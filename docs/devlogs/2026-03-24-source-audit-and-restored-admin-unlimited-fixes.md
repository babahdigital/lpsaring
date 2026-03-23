# Devlog: 2026-03-24 - Source Audit and Restored Admin, Unlimited, WA, and Self-Heal Fixes

**Tanggal**: 24 Maret 2026  
**Author**: Abdullah (via GitHub Copilot)  
**Scope**: audit histori chat, verifikasi source vs image produksi, pemulihan patch yang hilang dari `main`, dokumentasi perubahan aktual

---

## Konteks

Batch ini dimulai dari laporan bahwa perubahan yang sebelumnya sudah diminta dan pernah dibahas di sesi chat masih belum terlihat di produksi, walaupun alur operasional sudah dilakukan: commit, push, publish Docker image, lalu `deploy_pi.sh --recreate`.

Audit kemudian dilakukan dalam tiga lapisan:

1. verifikasi image yang sedang berjalan di host produksi,
2. verifikasi isi source `main` yang benar-benar menjadi bahan image,
3. pencocokan terhadap histori chat dan daftar perubahan yang sebelumnya sudah diminta user.

Hasil paling penting dari audit ini adalah: **recreate produksi bukan akar masalahnya**. Produksi memang sudah menjalankan image terbaru dari `main` saat itu, tetapi beberapa patch yang sebelumnya dibahas ternyata **tidak ada** di source `main` yang aktif. Karena itu, image yang benar pun tetap menampilkan perilaku lama.

---

## Ringkasan Temuan Audit

### 1. Produksi sudah memakai image terbaru yang tersedia

Verifikasi terhadap container, image ID, dan label OCI revision menunjukkan stack produksi memang sudah memakai image terbaru yang berasal dari `main` saat itu. Dengan kata lain, masalah bukan pada `docker pull`, bukan pada `force-recreate`, dan bukan pada container yang tertinggal di image lama.

### 2. Beberapa patch dari histori chat tidak ada di source aktif

Setelah source frontend dan backend dibaca ulang, ditemukan beberapa mismatch nyata antara histori chat dan isi repo aktif:

- dialog konfirmasi hapus log masih memakai flow lama,
- filter log untuk sumber `auth.device_binding_self_heal` belum ada,
- kolom `AKSI` pada daftar user masih terlalu sempit,
- layout selector section di `Edit Pengguna` belum sesuai baseline yang diminta,
- receipt pelunasan masih bergantung pada `window.open(receipt_url)` mentah,
- template WhatsApp debt/unlimited masih versi lama,
- aktivasi paket unlimited masih belum memulihkan seluruh perilaku yang diharapkan,
- self-heal backend untuk device binding belum ada di source aktif.

### 3. Root cause operasional: drift antara histori kerja dan source `main`

Ini bukan kasus "deploy gagal membawa commit terbaru" melainkan kasus "source `main` saat dipublish memang belum berisi patch yang diasumsikan sudah masuk". Karena itu, penyelesaiannya harus dilakukan di repo terlebih dahulu, baru diikuti publish dan deploy ulang.

---

## Perubahan yang Dipulihkan

Bagian ini mencatat patch yang benar-benar dipulihkan ulang ke source kerja saat audit dilakukan.

### Frontend

#### 1. `frontend/pages/admin/logs.vue`

Dipulihkan ulang:

- quick filter untuk event self-heal login,
- query param `source` ke backend,
- parser details yang lebih aman,
- label aksi yang membedakan event sistem dan self-heal,
- state `confirmDialog.loading` agar popup hapus tidak bisa double-submit,
- auto-close popup setelah aksi hapus berhasil,
- render admin/system yang aman saat entri log berasal dari sistem.

Tujuan perubahan ini adalah memastikan layar log admin benar-benar bisa dipakai untuk memantau event self-heal, sekaligus menghilangkan regresi UX pada popup hapus log.

#### 2. `frontend/components/admin/users/UserActionConfirmDialog.vue`

Dipulihkan ulang:

- loading guard pada `confirm` dan `close`,
- heading, subtitle, dan warning yang wrap-safe,
- overlay width yang lebih aman di viewport sempit,
- tombol aksi yang stack dengan rapi di mobile.

Ini menutup keluhan visual sebelumnya bahwa subtitle popup masih terpotong dan tombol aksi mudah bertabrakan di layar kecil.

#### 3. `frontend/pages/admin/users.vue`

Dipulihkan ulang:

- lebar kolom `AKSI` dari `182px` menjadi `236px`,
- group tombol aksi agar tidak collapse di render awal,
- helper responsive untuk titlebar dialog.

Perubahan ini secara langsung menutup gejala tombol aksi yang sempat tampak hilang, mepet, atau terpotong saat tabel pertama kali dirender.

#### 4. `frontend/components/admin/users/UserEditDialog.vue`

Dipulihkan ulang:

- section grid untuk navigasi area edit,
- visual state aktif/inaktif pada card selector,
- alignment kiri untuk judul dan deskripsi,
- ritme spacing yang lebih dekat ke referensi `dev-lpsaring/coba.html` tanpa merusak theme Vuexy/Vuetify.

Fokus batch ini bukan mengganti seluruh arsitektur dialog, tetapi memastikan layout section card yang sebelumnya sempat hilang kembali muncul sesuai intent yang sudah disepakati.

#### 5. `frontend/components/admin/users/UserDebtLedgerDialog.vue`

Dipulihkan ulang:

- helper `openPdfDocument(...)`,
- alur fetch blob lalu `objectURL` untuk export dan receipt PDF,
- penanganan preview window yang lebih aman,
- cleanup window jika pembukaan PDF gagal.

Perubahan ini menutup masalah blank tab pada receipt/laporan pelunasan dan menjaga admin tetap berada di konteks halaman yang sama.

### Backend

#### 6. `backend/app/infrastructure/http/admin/action_log_routes.py`

Dipulihkan ulang:

- dukungan filter `source` pada endpoint log admin,
- jalur pencarian untuk entri sistem `auth.device_binding_self_heal`.

Ini adalah pasangan backend dari quick filter yang dipakai layar log admin.

#### 7. `backend/app/notifications/templates.json`

Dipulihkan ulang:

- template debt baru,
- template pelunasan parsial/lunas dengan wording terbaru,
- template aktivasi unlimited oleh admin.

Perubahan ini penting karena user secara eksplisit melaporkan WhatsApp masih memakai teks lama walaupun perbaikan tersebut sebelumnya sudah dibahas.

#### 8. `backend/app/services/user_management/user_quota.py`

Dipulihkan ulang:

- reset `total_quota_purchased_mb`,
- reset `total_quota_used_mb`,
- reset `auto_debt_offset_mb`

saat user berpindah ke mode unlimited.

Ini menjaga agar state numerik quota tidak tertinggal ketika akses user diubah menjadi unlimited.

#### 9. `backend/app/services/user_management/user_profile.py`

Dipulihkan ulang:

- pembentukan `access_grant_summary`,
- trigger WA `user_unlimited_activated_by_admin`,
- jalur debt package yang kembali sinkron dengan perilaku unlimited,
- context tambahan untuk notification render.

Catatan penting: file ini memang masih memakai sentinel `debt_add_mb_pkg = 1 if is_unlimited_pkg else ...` untuk kompatibilitas debt record, tetapi jalur aktivasi unlimited dan payload notifikasi kini kembali selaras dengan perilaku bisnis yang diminta.

#### 10. `backend/app/services/device_management_service.py`

Dipulihkan ulang:

- pembacaan hotspot host aktif,
- cleanup artefak jaringan device,
- audit log self-heal,
- recovery device inactive untuk retry,
- retry once pada `apply_device_binding_for_login`,
- integrasi source log `auth.device_binding_self_heal`.

Ini adalah pemulihan paling besar dalam batch ini karena menyentuh akar masalah login yang sempat terkait device lama, binding lama, atau state router yang sudah tidak valid.

### Tests

#### 11. `backend/tests/test_device_management_service.py`

Diselaraskan ulang dengan perilaku baru, terutama untuk expectation data DHCP lease yang kini kembali mengikuti jalur backend aktif.

#### 12. `backend/tests/test_smoke_session_2026_03_19_s4.py`

Diselaraskan ulang agar template render test menyuplai `access_grant_summary` yang kini memang menjadi bagian kontrak payload notifikasi.

---

## Validasi yang Sudah Dijalankan

Validasi pada batch pemulihan ini tidak berhenti di editor diff. Yang dijalankan adalah:

1. pembacaan ulang source untuk memastikan patch benar-benar ada,
2. diagnostics editor pada file frontend dan backend yang dipulihkan,
3. lint frontend untuk file admin yang diubah,
4. focused pytest backend pada file yang paling terpengaruh,
5. penyesuaian test expectation yang tidak lagi cocok setelah perilaku lama dipulihkan,
6. re-run focused pytest sampai hijau.

Hasil final validasi backend fokus:

- `28 passed in 1.54s`

Ringkasan diff batch pemulihan saat audit selesai:

- `12 files changed, 707 insertions(+), 105 deletions(-)`

---

## Cakupan Histori Chat yang Sudah Tercermin di Source

Setelah audit ulang terhadap histori chat dan source kerja saat ini, area berikut dinilai sudah tercermin dalam perubahan lokal aktif:

- perbaikan popup admin log dan confirm dialog,
- stabilisasi action column pada daftar user,
- penyelarasan visual section card pada `Edit Pengguna`,
- pembukaan PDF receipt/export yang lebih aman,
- wording dan payload notifikasi WA debt/unlimited,
- reset counter quota saat aktivasi unlimited,
- self-heal device binding berikut audit log dan filter admin.

Dengan kata lain, **tidak ditemukan lagi gap besar tambahan dari batch terakhir** selain kebutuhan untuk mendokumentasikan dan kemudian mendorong patch ini ke alur release.

---

## Dampak Operasional

Batch ini penting bukan hanya karena memperbaiki fitur, tetapi karena menutup blind spot proses release:

1. image terbaru tidak menjamin perilaku terbaru jika source `main` sendiri drift,
2. verifikasi pascadeploy harus membandingkan image revision dengan source aktual dan gejala UI yang dilaporkan user,
3. dokumentasi release perlu mencatat dengan jelas mana perubahan yang benar-benar sudah ada di repo dan mana yang baru dipulihkan.

---

## Langkah Lanjut

Urutan aman setelah batch ini adalah:

1. commit patch pemulihan,
2. push ke `main`,
3. publish image baru,
4. jalankan `deploy_pi.sh --recreate`,
5. smoke-test ulang skenario yang sebelumnya dilaporkan user.

Smoke-test prioritas setelah deploy ulang:

- popup hapus log wrap dengan benar,
- tombol aksi admin user tidak terpotong saat render awal,
- section card `Edit Pengguna` tampil sesuai intent,
- receipt pelunasan tidak lagi blank tab,
- WA debt/unlimited memakai template baru,
- self-heal login tercatat di admin log bila path tersebut terpakai.
