# Devlog: 2026-03-21 — Timezone Centralization, Debt WA Accuracy, dan Release Ops

**Tanggal**: 21 Maret 2026  
**Author**: Abdullah (via GitHub Copilot)  
**Scope**: backend formatting/timezone, debt notification, dokumentasi, release, deploy verification

---

## Konteks

Sesi ini dimulai dari dua kebutuhan yang berurutan:

1. merilis perubahan WhatsApp debt notification agar total nominal tunggakan ikut tampil,
2. mengaudit laporan user bahwa pesan WA masih menunjukkan selisih satu jam antara timestamp utama dan detail item debt.

Dalam prosesnya juga ditemukan satu near-miss operasional saat `deploy_pi.sh --recreate` pertama mengembalikan RC=1, walaupun stack app sebenarnya sudah hidup. Karena itu sesi ini tidak hanya menutup bug aplikasi, tetapi juga memperbarui dokumentasi release dan operasi produksi.

---

## Ringkasan Hasil

- Commit fitur WA debt nominal berhasil dibuat dan di-push ke `main`.
- Docker publish dipicu manual terhadap `main`, kemudian image terbaru berhasil dipakai di produksi.
- Recreate deploy kedua terverifikasi memakai image backend/frontend terbaru.
- Root cause selisih satu jam di pesan WA ditemukan dan diperbaiki.
- Timezone handling dipusatkan agar tidak ada lagi campuran helper lokal vs offset hardcoded.
- Normalisasi tampilan `GB` dilanjutkan ke helper bersama, tanpa menyentuh arithmetic kuota mentah.
- Backend lint/tests, frontend lint/typecheck/tests, dan editor diagnostics berada dalam kondisi hijau.

---

## 1. Release Sebelum Audit Timezone

Batch pertama di sesi ini adalah perubahan WhatsApp debt notification:

- template `user_debt_added` diperluas agar menampilkan total nominal tunggakan,
- payload backend diperluas untuk membawa `total_manual_debt_amount_rp` dan display string terkait,
- regression test notifikasi dan smoke test backend diperbarui.

Perubahan ini kemudian:

1. di-commit ke `main`,
2. di-push untuk memicu CI,
3. diikuti manual dispatch `docker-publish.yml`.

Run Docker publish yang dipakai untuk batch ini berhasil, lalu dijadikan target deploy produksi.

---

## 2. Near-Miss Saat Recreate Pertama

Setelah publish Docker hijau, deploy `./deploy_pi.sh --recreate` dijalankan untuk memaksa container memakai image terbaru.

### Gejala

- recreate pertama berakhir dengan `RC=1`,
- log deploy menunjukkan error pada health check berbasis `global-nginx-proxy`,
- tetapi pengecekan terpisah menunjukkan stack `backend`, `frontend`, `celery_worker`, `celery_beat`, `db`, dan `redis` sebenarnya sudah hidup.

### Tindakan verifikasi

- dijalankan postdeploy healthcheck terpisah dari workspace lokal,
- diverifikasi bahwa `/login` dan asset `_nuxt` dapat diakses,
- dibandingkan image ID container runtime vs image `latest` di host.

### Temuan

Pada titik itu stack memang sudah naik, tetapi backend/frontend yang berjalan belum sepenuhnya cocok dengan image `latest` hasil publish. Karena itu recreate dijalankan sekali lagi.

### Hasil akhir

- recreate kedua berakhir `RC=0`,
- image backend runtime cocok dengan image backend `latest`,
- image frontend runtime cocok dengan image frontend `latest`,
- seluruh service compose utama berada dalam status sehat.

RCA khusus kejadian ini ditulis terpisah di `docs/incidents/2026-03-21-recreate-healthcheck-false-negative.md`.

---

## 3. Audit Selisih 1 Jam di WhatsApp Debt Notification

User memberikan contoh pesan WhatsApp dengan pola berikut:

- header pesan: waktu lokal yang tampak benar,
- baris detail debt: satu jam lebih mundur.

Contoh gejala ini tidak cocok dengan dugaan konfigurasi produksi salah, sehingga audit dilakukan pada dua level:

1. konfigurasi runtime produksi,
2. call-site formatter di backend.

### Verifikasi runtime produksi

Baik file `.env.prod` maupun environment container backend sudah menunjukkan:

```env
APP_TIMEZONE=Asia/Makassar
```

Artinya, problem bukan karena production masih memakai timezone lama.

### Root cause aplikasi

Jalur `user_debt_added` memang tidak sepenuhnya konsisten:

- header notifikasi sudah memakai helper timezone aplikasi,
- tetapi detail item debt di `backend/app/services/user_management/user_profile.py` masih mengubah `created_at` memakai WIB hardcoded (`UTC+7`).

Akibatnya, dalam runtime `Asia/Makassar`, header dan detail item bisa berbeda satu jam.

---

## 4. Perubahan Code Timezone

### 4.1. Sentralisasi konfigurasi timezone

`backend/config.py` sekarang menurunkan dua field turunan langsung dari `APP_TIMEZONE`:

- `APP_TIMEZONE_OFFSET`
- `APP_TIMEZONE_LABEL`

Resolver ini mencoba membaca zoneinfo runtime. Jika timezone valid, offset dan label ikut disesuaikan tanpa perlu hardcode terpisah.

### 4.2. Helper timezone terpusat

`backend/app/utils/formatters.py` sekarang menjadi titik utama untuk:

- `get_app_timezone()`
- `get_app_timezone_offset_hours()`
- `get_app_timezone_label()`
- `get_app_local_datetime()`

Helper lama `format_datetime_to_wita()` tidak dihapus agar kompatibilitas tetap terjaga, tetapi implementasinya sekarang mengikuti timezone aplikasi aktif.

### 4.3. Call-site yang diselaraskan

Beberapa jalur yang diperbarui untuk mengikuti helper yang sama:

- `backend/app/services/user_management/user_profile.py`
- `backend/app/tasks.py`
- `backend/app/infrastructure/http/admin_routes.py`
- `backend/app/infrastructure/http/transactions_routes.py`
- `backend/app/infrastructure/http/transactions/invoice_routes.py`
- `backend/app/infrastructure/http/admin_contexts/reports.py`

Tujuannya bukan mengubah business logic, tetapi memastikan semua render tanggal/jam mengambil timezone lokal dengan cara yang sama.

---

## 5. Perubahan Code Normalisasi GB

Setelah audit timezone, dilakukan sweep hati-hati untuk display kuota `GB`.

### Prinsip yang dijaga

- render user-facing `GB` harus konsisten, dua desimal, dan berasal dari helper bersama,
- arithmetic internal kuota tidak boleh berubah hanya karena kita sedang merapikan display string.

### Implementasi

`format_mb_to_gb()` dijadikan helper utama untuk string `xx.xx GB`, lalu dipakai pada jalur berikut:

- payload WhatsApp debt manual,
- task reminder debt,
- warning quota debt,
- notification service,
- quota history service,
- command remediation yang menampilkan kuota ke operator.

### Area yang sengaja tidak diubah

Contoh seperti berikut sengaja dipertahankan:

- `limit_bytes_total = mb * 1024 * 1024`
- `bytes_total = bytes_in + bytes_out`
- arithmetic monotonic counter hotspot

Itu semua adalah domain enforcement/accounting, bukan presentasi.

---

## 6. Regression dan Perbaikan Turunan

Saat patch timezone diperluas, sempat muncul beberapa regresi kecil:

- anotasi return type lokal timezone di admin route terlalu sempit,
- import `timedelta` sempat hilang di `user_profile.py`,
- variabel `app_tz` di salah satu task debt reminder belum terdefinisi.

Semua regresi tersebut diperbaiki sebelum validasi akhir dijalankan.

Selain itu, beberapa helper display `GB` yang masih membangun string sendiri di layer notifikasi/history/remediation juga dipusatkan ke helper bersama agar konsistensi tidak hanya berhenti di jalur debt notification.

---

## 7. Validasi

### Backend

- editor diagnostics: bersih,
- focused pytest untuk debt notification/timezone: lulus,
- `ruff check`: lulus.

### Frontend

- lint: lulus,
- typecheck: lulus,
- Vitest: `18` file test lulus, `159` test lulus.

### Produksi

- runtime backend dan frontend cocok dengan image terbaru yang dipublish,
- stack compose utama sehat,
- konfigurasi runtime tetap `APP_TIMEZONE=Asia/Makassar`.

---

## 8. Dokumentasi yang Diperbarui

Batch ini memperbarui dokumen aktif berikut:

- `CHANGELOG.md`
- `docs/REFERENCE_PENGEMBANGAN.md`
- `docs/workflows/PRODUCTION_OPERATIONS.md`
- `docs/devlogs/README.md`
- `docs/incidents/README.md`

Serta menambahkan:

- devlog ini,
- RCA near-miss recreate false negative.

---

## 9. Keputusan Teknis yang Ditegaskan Ulang

1. `APP_TIMEZONE` adalah source of truth tunggal untuk waktu lokal aplikasi.
2. Render tanggal/jam user-facing tidak boleh lagi memakai offset hardcoded yang tersebar.
3. Display helper `GB` boleh dipusatkan, tetapi quota arithmetic mentah tidak boleh dirombak demi kosmetik.
4. Deploy dianggap benar-benar selesai hanya jika health check, image runtime, dan endpoint publik sama-sama cocok.

---

## 10. Dampak Operasional

Dengan batch ini:

- pesan WA debt tidak lagi membingungkan user/admin karena selisih satu jam antarbagian pesan,
- perubahan timezone masa depan lebih aman karena offset/label tidak disebar manual ke banyak file,
- operator memiliki runbook yang lebih jelas saat `deploy_pi.sh --recreate` gagal secara semu padahal stack sudah naik,
- semua jalur display GB yang paling sering terlihat user bergerak ke format yang lebih konsisten.