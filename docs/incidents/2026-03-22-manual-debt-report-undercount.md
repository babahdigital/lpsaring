# Incident 2026-03-22: Manual Debt Report Undercount — Nominal Manual Ikut Jatuh ke Estimator Aggregate

**Severity:** Medium  
**Status:** Resolved  
**Kategori:** Aplikasi / correctness bug / billing representation

---

## Ringkasan

Ringkasan tunggakan manual user sempat menampilkan nominal total yang lebih rendah dari jumlah item debt sebenarnya. Kasus nyata yang dilaporkan menunjukkan dua item debt manual `20 GB` masing-masing `Rp 200.000` tampil sebagai total `Rp 270.000`, padahal total yang benar adalah `Rp 400.000`.

Masalah ini terjadi karena jalur report menghitung nominal manual dari aggregate `manual_debt_mb`, lalu meneruskannya ke estimator paket termurah aktif, alih-alih menjumlah item debt manual yang masih terbuka.

---

## Dampak

- User bisa menerima ringkasan nominal debt manual yang undercount.
- Admin bisa salah membaca total nominal manual di report/PDF/WA share.
- Risiko keputusan penagihan atau komunikasi ke user menjadi tidak akurat.
- Tidak ditemukan indikasi data debt item di database rusak; bug ada pada layer representasi/reporting.

---

## Gejala

- Total debt manual GB benar.
- Daftar item debt benar.
- Tetapi total nominal rupiah manual lebih kecil dari penjumlahan item yang ditampilkan.

Contoh gejala:

- item 1: `20 GB`, `Rp 200.000`
- item 2: `20 GB`, `Rp 200.000`
- total manual tampil: `40 GB`, `Rp 270.000`

---

## Root Cause

Builder report manual debt mencampur dua domain yang seharusnya dipisahkan:

- **manual debt** yang sudah punya item dan harga tersimpan,
- **auto debt** yang memang hanya punya pendekatan estimasi referensi.

Alih-alih menjumlah `remaining_rp` dari item debt manual yang masih terbuka, code lama:

1. mengambil aggregate `quota_debt_manual_mb`,
2. menganggap aggregate itu boleh diterjemahkan ke rupiah via estimator paket termurah aktif,
3. memakai hasil estimator tersebut sebagai total nominal manual.

Pendekatan itu valid hanya untuk debt otomatis yang memang tidak menyimpan harga exact per item. Untuk manual debt, pendekatan itu salah secara konsep dan menghasilkan undercount/overcount tergantung kombinasi paket aktif saat report dibangun.

---

## Timeline Ringkas

1. User melaporkan mismatch antara item debt manual dan total nominal yang tampil.
2. Dilakukan audit builder report debt manual.
3. Ditemukan bahwa total nominal manual diturunkan dari estimator aggregate MB.
4. Builder diperbaiki untuk menjumlah item terbuka yang aktual.
5. Admin route diselaraskan ke builder bersama agar output PDF/WA/admin tetap konsisten.
6. Ditambahkan regression test untuk full-open item dan partial item.
7. Label UI/template juga diperjelas agar debt otomatis tetap terbaca sebagai nilai referensi.

---

## Resolusi

Perbaikan yang diterapkan:

- `backend/app/services/manual_debt_report_service.py`
  - tambah helper penjumlahan item terbuka,
  - `debt_manual_estimated_rp` kini mengikuti total `remaining_rp` item terbuka bila tersedia,
  - `debt_total_estimated_rp` menjadi `auto reference + manual exact/open total`.

- `backend/app/infrastructure/http/admin/user_management_routes.py`
  - jalur admin PDF/WA tidak lagi memelihara builder lokal yang bisa drift.

- `backend/tests/test_manual_debt_report_service.py`
  - lock regression untuk total exact multi-item,
  - lock regression untuk prorata item parsial.

---

## Guardrail Baru

- Debt manual harus memprioritaskan nominal item yang tersimpan bila tersedia.
- Debt otomatis tetap boleh memakai estimator, tetapi labelnya harus `nilai referensi`.
- Builder report debt yang dipakai lintas kanal harus dibagi bersama, bukan disalin ke route/template lain.

---

## Pelajaran

1. Aggregate MB bukan sumber kebenaran yang cukup untuk billing manual jika item debt sudah punya harga sendiri.
2. `Manual` dan `auto` debt harus diperlakukan sebagai dua domain akuntansi yang berbeda.
3. Ketika satu angka tampil sebagai total, regression test harus memastikan angka itu benar terhadap daftar item yang sama, bukan hanya benar terhadap aggregate terpisah.