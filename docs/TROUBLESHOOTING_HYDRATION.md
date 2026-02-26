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

**Lokasi utama (historis + lanjutan):**
- Halaman `admin/users`.
- Halaman `beli` dan `captive/beli` (khususnya saat flow auth/session demo login).
- Komponen yang terlibat: `VChipGroup`, layout responsif yang memakai `useDisplay`, serta elemen dialog/status yang sensitif terhadap timing hydration.

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

### C. Stabilkan output formatting SSR vs client
- Hindari perbedaan hasil `Intl`/`toLocaleString` yang bergantung locale runtime host.
- Gunakan formatter deterministik terpusat di `frontend/utils/formatters.ts` untuk angka, mata uang, tanggal, dan jam.

### D. Tunda mutasi auth/session client sampai mounted
- Inisialisasi auth client yang memicu update state selama fase hydration dipindah ke lifecycle setelah mounted.
- Efek global yang dapat mengubah state route/session saat hydration diberi guard mounted.

### E. Kurangi render dini komponen sensitif di flow beli
- Komponen dialog/payment state yang mudah mismatch dirender setelah hydration siap.
- Diterapkan pada halaman `frontend/pages/beli/index.vue` dan `frontend/pages/captive/beli.vue`.

---

## 4) File yang Diubah

- `frontend/pages/admin/users.vue`
  - `isHydrated` + `isMobile`
  - Render `VChipGroup` setelah hydration
- `frontend/pages/beli/index.vue`
  - Format nominal deterministik dan penyesuaian render aman hydration
- `frontend/pages/captive/beli.vue`
  - Format nominal deterministik, gating komponen payment dialog
- `frontend/utils/formatters.ts`
  - Helper format konsisten SSR/client
- `frontend/plugins/01.auth.ts`
  - Client auth init dipindah ke `app:mounted`
- `frontend/app.vue`
  - Efek terkait session dipagari state mounted

---

## 5) Validasi

1. Refresh halaman `/admin/users`.
2. Pastikan warning hydration terkait `VChipGroup` tidak muncul lagi.
3. Uji halaman `/beli` dan `/captive/beli` setelah login (termasuk akun demo), pastikan warning hydration mismatch berkurang/hilang.
4. Verifikasi halaman legal (`/merchant-center/privacy`, `/merchant-center/terms`) tetap bisa dibuka walau status akun non-ok.
5. Jika masih ada mismatch, identifikasi komponen yang menggunakan `useDisplay`/`window` API atau mutasi store pada fase hydration, lalu terapkan strategi serupa.

---

## 6) Catatan Tambahan

- Warning terkait New Relic (`ERR_BLOCKED_BY_CLIENT`) berasal dari adblock dan **bukan error aplikasi**.
- Warning Sass `mixed-decls` hanya deprecation (bukan error fatal).
