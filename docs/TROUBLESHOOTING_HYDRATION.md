# Troubleshooting Hydration Mismatch

Dokumen ini merangkum error hydration yang muncul di browser dan langkah perbaikannya.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Ringkasan Error

**Gejala:**
- Console menampilkan warning seperti:
  - `Hydration completed but contains mismatches`
  - `Hydration class mismatch on <div class="v-slide-group v-slide-group--mobile ...">`
  - `Hydration style mismatch on <div style="width:...">`

**Lokasi utama:**
- Halaman `admin/users`.
- Komponen yang terlibat: `VChipGroup`, layout responsif yang memakai `useDisplay`.

---

## 2) Akar Masalah

- SSR merender markup berbeda dengan client saat hydrasi.
- `useDisplay()` dari Vuetify bergantung pada ukuran layar (client), sedangkan SSR tidak memiliki ukuran layar aktual.
- Akibatnya class seperti `v-slide-group--mobile` hanya muncul di SSR atau client, menimbulkan mismatch.

---

## 3) Perbaikan yang Diterapkan

### A. Menunda layout responsif sampai client ter-hydrate
Di `frontend/pages/admin/users.vue`:
- Tambah flag `isHydrated`.
- Gunakan `isMobile` yang hanya aktif setelah `onMounted()`.

### B. Render komponen sensitif hanya setelah hydration
- Bagian `VChipGroup` sekarang hanya dirender saat `isHydrated && !isMobile`.

---

## 4) File yang Diubah

- `frontend/pages/admin/users.vue`
  - `isHydrated` + `isMobile`
  - Render `VChipGroup` setelah hydration

---

## 5) Validasi

1. Refresh halaman `/admin/users`.
2. Pastikan warning hydration terkait `VChipGroup` tidak muncul lagi.
3. Jika masih ada mismatch, identifikasi komponen yang menggunakan `useDisplay`/`window` API dan lakukan strategi serupa.

---

## 6) Catatan Tambahan

- Warning terkait New Relic (`ERR_BLOCKED_BY_CLIENT`) berasal dari adblock dan **bukan error aplikasi**.
- Warning Sass `mixed-decls` hanya deprecation (bukan error fatal).
