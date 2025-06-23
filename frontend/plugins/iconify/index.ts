// frontend/plugins/iconify/index.ts

// Cukup impor file CSS yang dihasilkan oleh skrip build-icons.ts
import './icons.css'

/**
 * Plugin ini hanya bertanggung jawab untuk memuat stylesheet ikon (icons.css)
 * yang dihasilkan pada saat build.
 *
 * Integrasi ikon dengan komponen Vuetify sendiri sudah ditangani oleh
 * plugin vuetify melalui CssIconAdapter.
 */
export default defineNuxtPlugin(() => {
  // Tidak perlu melakukan apa-apa lagi di sini.
  // CSS sudah diimpor dan akan diterapkan secara global.
})