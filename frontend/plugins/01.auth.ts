// frontend/plugins/01.auth.ts
import { useAuthStore } from '~/store/auth'
// PERBAIKAN: Hapus impor yang tidak lagi digunakan
// import { useSettingsStore } from '~/store/settings'
// import { useNuxtApp } from '#app'
// import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const authStore = useAuthStore()

  // 1. Inisialisasi auth
  // Fungsi ini akan memeriksa cookie dan mengambil data pengguna jika token ada.
  await authStore.initializeAuth()

  // 2. PERBAIKAN: Logika untuk memuat pengaturan aplikasi telah dihapus dari file ini.
  //    Tanggung jawab ini sekarang sepenuhnya ditangani oleh plugin '00.load-initial-state.ts'
  //    untuk memastikan satu sumber kebenaran dan menghindari race condition.
})