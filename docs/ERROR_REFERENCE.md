# Referensi Error & Penyebab (Frontend)

Dokumen ini merangkum penyebab umum error TypeScript/Vue yang muncul agar menjadi referensi ke depan.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Konsistensi Tipe Data
**Gejala**: Banyak error di template (index signature, any, property not exist).
**Penyebab**:
- Kontrak API berubah (tamping, quota, role) tapi type frontend belum diperbarui.
- Ada duplikasi tipe antara berbagai file.

**Solusi**:
- Satukan tipe di folder types/.
- Pastikan response API dan tipe frontend sinkron.

## 2) useFetch/useApiFetch Generics
**Gejala**: Error terkait default, PickFrom, atau data tidak dikenal.
**Penyebab**:
- Generic type tidak diset eksplisit.
- default() mengembalikan object bukan Ref.

**Solusi**:
- Gunakan typed response dan hindari default() jika tidak perlu.
- Gunakan cast terkontrol atau helper typed.

## 3) $vuetify vs useDisplay
**Gejala**: Property $vuetify tidak ada.
**Penyebab**:
- Migrasi dari Vuetify lama ke Nuxt 3 / Vuetify 3.

**Solusi**:
- Gunakan useDisplay() untuk breakpoint dan replace penggunaan $vuetify.

## 4) Icon Adapter & Namespace Types
**Gejala**: IconSet/IconProps tidak terbaca.
**Penyebab**:
- Tipe Vuetify tidak diekspor seperti di versi sebelumnya.

**Solusi**:
- Gunakan type lokal sederhana di adapter.
- Hindari import type yang menyebabkan error.

## 5) Template Slot Typing
**Gejala**: item pada slot dianggap unknown.
**Penyebab**:
- Slot template tidak memiliki tipe eksplisit.

**Solusi**:
- Buat helper function untuk cast item.
- Hindari indexing langsung jika item dianggap any/unknown.

## 6) Perubahan Schema User (Tamping)
**Gejala**: Field is_tamping/tamping_type tidak ada di tipe atau form.
**Penyebab**:
- Perubahan DB & backend tidak diikuti frontend.

**Solusi**:
- Tambahkan field ke type user, form, dan validator.

## 7) ApexCharts Types
**Gejala**: property tidak dikenal di config chart.
**Penyebab**:
- Tipe Apex lebih ketat dari opsi real.

**Solusi**:
- Cast ke any untuk bagian tertentu.
- Simpan tipe strict untuk area inti saja.

## 8) Rekomendasi Pencegahan
- Terapkan lint rule yang konsisten.
- Buat changelog saat kontrak API berubah.
- Tambahkan smoke tests sederhana sebelum merge.
