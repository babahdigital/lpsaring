# UI Styling Standards

Tujuan dokumen ini: memastikan semua halaman UI (admin & user) mengikuti pola yang sama, supaya:

- tampilan selaras (mirip demo Vuexy),
- responsif,
- minim styling ulang,
- dan tidak ada “rule global” yang tidak sengaja merusak halaman lain.

## Prinsip utama

1. **Komponen wrapper sebagai single source of truth**
   - Gunakan wrapper/komponen bersama untuk hal yang berulang (select, pagination, toolbar table).
2. **Matikan footer bawaan datatable**
   - Hindari variasi style bawaan Vuetify yang berbeda antar halaman.
3. **Global SCSS hanya untuk hal yang benar-benar generik**
   - Jangan menaruh rule yang mengubah semua list/table tanpa class pembeda.
4. **Tidak hard-code style yang melawan theme**
   - Jangan menambah warna baru; gunakan theme token/Vuetify utilities.

## Komponen standar yang wajib dipakai

### 0) AppPerfectScrollbar

Gunakan ini untuk semua container yang butuh scroll (dialog body, list panjang, panel/filter sidebar), agar scrollbar konsisten seperti demo Vuexy (Perfect Scrollbar).

File:
- frontend/@core/components/AppPerfectScrollbar.vue

Aturan:
- Jangan pakai `style="overflow-y: auto"` untuk container UI yang ingin distandarkan.
- Cukup set batas tinggi: `max-height: ...` lalu bungkus konten dengan `AppPerfectScrollbar`.
- Hindari `VDialog scrollable` jika isi dialog sudah memakai `AppPerfectScrollbar` (mencegah double scrollbar).

### 1) DataTableToolbar

Gunakan untuk layout ala demo:
- **Show (entries selector)**
- **Search field**

File:
- frontend/@core/components/DataTableToolbar.vue

Pola:

- Untuk tabel server-side:
  - `v-model:items-per-page="options.itemsPerPage"`
  - `v-model:search="search"` (jika backend mendukung)
  - reset page saat `itemsPerPage` berubah: `@update:items-per-page="() => (options.page = 1)"`

### 2) TablePagination

Gunakan ini sebagai pagination tunggal (desktop & mobile) setelah tabel.

File:
- frontend/@core/components/TablePagination.vue

Pola:
- Selalu pasang `hide-default-footer` pada datatable.
- Pagination tampil hanya saat dibutuhkan (sudah dihitung di komponen).

### 3) AppSelect

Select/filter standar pakai wrapper ini, bukan `VSelect` langsung.

File:
- frontend/@core/components/app-form-elements/AppSelect.vue

Alasan:
- density/variant/hide-details konsisten.

## Standar untuk table/datatable

### Server-side datatable

Checklist:

1. `VDataTableServer` + `hide-default-footer`
2. Toolbar di atas table:
   - `DataTableToolbar` (entries selalu, search bila perlu)
3. Pagination di bawah table:
   - `TablePagination`

### Local table (VDataTable)

Jika paging dikelola manual (computed `pagedItems`), tetap gunakan:

- `DataTableToolbar` untuk mengatur `itemsPerPage` (tanpa search), dan reset page.
- `TablePagination` untuk navigasi page.

## Standar SCSS

### Lokasi yang benar

- Style table generik: frontend/@core/scss/template/libs/vuetify/components/_table.scss
- Override Vuetify global (hati-hati): frontend/@core/scss/base/libs/vuetify/_overrides.scss

### Aturan penting

1. Jangan mengubah class umum seperti `.card-list` untuk kasus spesifik.
   - Buat class khusus (contoh: `.debt-card-list`) dan pakai di halaman yang butuh.
2. Page-specific styling:
   - pakai `scoped` dan class lokal.
3. Hindari hard-coded warna.
   - pakai theme variables atau utilities.

## Contoh pola halaman baru (ringkas)

1. Filter (jika ada) → `AppSelect`, `AppTextField`
2. Toolbar → `DataTableToolbar`
3. Table → `VDataTableServer hide-default-footer`
4. Pagination → `TablePagination`
