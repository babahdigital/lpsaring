# Devlog: 2026-03-22 — User Detail Report Trust, Mobile Density, dan Contract Sync

**Tanggal**: 22 Maret 2026  
**Author**: Abdullah (via GitHub Copilot)  
**Scope**: trust wording status user admin, PDF/WhatsApp detail report, tombol debt-only pada dialog detail, density mobile topbar, OpenAPI, typed contract, dan test coverage.

---

## Konteks

Batch ini dimulai dari dua masalah operasional yang saling terkait.

1. Panel admin user masih menampilkan bahasa yang terasa dummy, terutama fallback seperti `Belum ada akun MikroTik` dan `Belum terset`, padahal banyak user sebenarnya punya akun hotspot dan hanya field sinkron lokal yang stale.
2. Layout topbar dialog edit user di mobile terlalu boros tinggi, sehingga form inti cepat terdorong ke bawah dan operator harus scroll lebih jauh sebelum bisa bertindak.

Permintaan lanjutan dari user juga menegaskan bahwa aksi operasional tidak boleh berhenti di dialog edit saja. Dialog detail harus bisa:

- kirim PDF detail pengguna,
- kirim ringkasan debt saja,
- dan menyediakan tombol WhatsApp debt yang kecil/cepat untuk follow up.

---

## Ringkasan Hasil

- Topbar mobile `Edit Pengguna` diringkas menjadi grid dua kolom yang lebih pendek dan helper text panjang disembunyikan di layar kecil.
- Status layanan tetap terlihat lewat chip ringkas di header, sehingga informasi penting tidak hilang walau pill status penuh disembunyikan di mobile.
- Dialog `Detail Pengguna` sekarang memiliki aksi debt-only langsung pada section `Riwayat Tunggakan Manual`: `Detail`, `PDF`, dan `WA Debt`.
- OpenAPI, typed contract frontend, dan dokumen API ikut diselaraskan untuk endpoint baru detail user.
- Ditambahkan regression test backend untuk ringkasan detail user, antre WhatsApp detail report, token detail report, dan smoke contract path baru.

---

## 1. Trust Layer untuk Detail User Admin

Problem awal bukan sekadar copywriting. UI sebelumnya terlalu bergantung pada field sinkron lokal seperti `mikrotik_user_exists` dan `mikrotik_profile_name`, sehingga saat data belum tersinkron atau live check belum jalan, panel mudah menampilkan kesan seolah user memang tidak ada di MikroTik.

Untuk itu ditambahkan jalur backend terpusat:

- `GET /api/admin/users/{user_id}/mikrotik-status`
- `GET /api/admin/users/{user_id}/detail-summary`
- `GET /api/admin/users/{user_id}/detail-report/export?format=pdf`
- `POST /api/admin/users/{user_id}/detail-report/send-whatsapp`
- `GET /api/admin/users/detail-report/temp/{token}.pdf`

Dengan jalur ini, frontend admin tidak perlu menebak status/profile sendiri ketika response backend tersedia.

---

## 2. Density Mobile Dialog Edit User

Audit visual pada mode mobile menunjukkan topbar meta di `UserEditDialog.vue` terlalu tinggi karena semua pill tetap menampilkan helper text panjang, ditambah status layanan juga ikut mengambil ruang penuh.

Perubahannya:

- grid pill mobile menjadi 2 kolom, bukan 1 kolom vertikal panjang,
- padding, radius, dan ukuran font pill diperkecil,
- helper text pill disembunyikan pada breakpoint mobile,
- pill `Status Layanan` versi panjang disembunyikan di mobile,
- status layanan dipindah ke chip ringkas tepat di bawah subtitle header.

Hasilnya, operator tetap bisa melihat konteks cepat tanpa kehilangan terlalu banyak tinggi layar sebelum masuk ke form.

---

## 3. Debt-Only Actions di Dialog Detail

Sebelumnya aksi debt yang lengkap lebih banyak terpusat di `UserEditDialog` dan popup ledger. Ini membuat operator yang sedang hanya membaca detail user harus berpindah layar untuk follow up sederhana.

Sekarang di `UserDetailDialog.vue`, bagian `Riwayat Tunggakan Manual` memiliki aksi kecil langsung:

- `Detail` untuk membuka popup ledger penuh,
- `PDF` untuk export debt report,
- `WA Debt` untuk mengantrekan ringkasan tunggakan ke WhatsApp.

Action ini diletakkan persis di section debt agar konteksnya jelas dan tidak bercampur dengan action laporan detail pengguna umum.

---

## 4. Contract Sync

Karena endpoint baru sudah masuk area admin operasional yang dipakai frontend langsung, batch ini juga memperbarui:

- `contracts/openapi/openapi.v1.yaml`
- `frontend/types/api/contracts.generated.ts`
- `frontend/types/api/contracts.ts`
- `docs/API_DETAIL.md`

Tujuannya agar gate kontrak tidak hanya lolos secara file timestamp, tetapi juga benar-benar mewakili shape request/response terbaru.

---

## 5. Test dan Smoke Coverage

Batch ini menambahkan coverage berikut:

- route test untuk `detail-summary` agar payload operasional yang dikonsumsi dialog tetap stabil,
- route test untuk antre `detail-report/send-whatsapp`,
- token roundtrip test untuk PDF detail user,
- template render test untuk `user_detail_report_with_pdf`,
- smoke contract test untuk path OpenAPI baru,
- payload ref test agar path baru tetap menunjuk schema yang benar.

Coverage ini sengaja difokuskan ke trust layer, queue trigger, dan contract drift karena ketiganya paling berisiko rusak diam-diam walau UI tampak baik-baik saja.

---

## 6. Validasi

Validasi yang ditargetkan untuk batch ini:

- diagnostics editor pada file frontend/backend yang diubah,
- typecheck frontend,
- lint frontend file yang tersentuh,
- pytest terfokus untuk route, notification template, dan contract smoke.

Jika commit/push dilakukan setelah batch ini, kontrak dan test sudah ikut bergerak bersama perubahan UI/backend, bukan menyusul belakangan.

---

## 7. Pelajaran

1. Fallback UX yang terlihat sederhana bisa berubah menjadi trust bug bila data live dan data sinkron lokal tidak dibedakan secara eksplisit.
2. Layout mobile dialog fullscreen harus diaudit berdasarkan tinggi nyata viewport, bukan sekadar apakah komponen masih muat secara lebar.
3. Jika fitur baru menambah endpoint backend yang dipakai frontend langsung, OpenAPI dan typed contract harus digerakkan pada batch yang sama, bukan dianggap pekerjaan dokumentasi terpisah.
4. Action operasional paling sering dipakai sebaiknya tersedia juga di layar baca/detail, bukan hanya di layar edit.