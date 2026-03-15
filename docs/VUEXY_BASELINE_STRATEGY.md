# Vuexy Baseline Strategy

Dokumen ini menjelaskan batas aman antara baseline Vuexy yang diadopsi dan layer domain custom di repo ini.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Baseline vs Custom

- Baseline referensi: `typescript-version/full-version` hanya dipakai sebagai acuan desain dan struktur.
- Runtime produksi tetap berada di `frontend/`.
- Tidak boleh ada import runtime langsung dari baseline atau starter-kit ke aplikasi aktif.

## Boundary Folder

### Baseline yang dipelihara

- `frontend/@core/**`
- `frontend/@layouts/**`
- `frontend/assets/styles/**`

### Area produk

- `frontend/pages/**`
- `frontend/components/**`
- `frontend/composables/**`
- `frontend/store/**`
- `frontend/plugins/**`

## Aturan UI Aktif

### Wrapper komponen wajib

- Gunakan `AppPerfectScrollbar` untuk panel scroll dan body dialog panjang.
- Gunakan `DataTableToolbar` untuk selector entries dan search di tabel.
- Gunakan `TablePagination` sebagai pagination tunggal, bukan footer bawaan datatable.
- Gunakan `AppSelect` untuk filter/select standar.

### Styling

- Hindari rule global yang menyerang seluruh list atau table tanpa class pembeda.
- Gunakan theme token dan utilitas Vuetify, bukan warna hard-coded baru.
- Styling khusus halaman diletakkan di scope lokal atau class lokal yang jelas.

### Sinkronisasi baseline

- Adaptasi dari Vuexy harus berupa copy terkontrol ke `@core` atau `@layouts`.
- Perubahan mayor pada area baseline wajib divalidasi dengan lint, typecheck, dan test yang relevan.
- PR yang menyentuh area baseline harus menjelaskan delta terhadap baseline yang diadopsi.

## Enforcement

- Script penjaga: `scripts/enforce_ui_standards.py`
- Script tersebut memblok referensi runtime ke `typescript-version/full-version` atau `starter-kit/src`.

## Checklist Singkat PR Frontend

- Tidak mengimpor runtime dari baseline eksternal.
- Tabel baru mengikuti pola toolbar plus pagination standar.
- Perubahan theme tidak membuat token warna atau font baru tanpa alasan jelas.
- Halaman admin dan user tetap responsif tanpa styling override massal.