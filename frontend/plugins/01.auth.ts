// frontend/plugins/01.auth.ts

import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin(async (_nuxtApp) => {
  const authStore = useAuthStore()

  // Plugin ini berjalan sekali di sisi server dan sekali di sisi client saat awal muat.
  // Flag 'initialAuthCheckDone' dari store Anda mencegah eksekusi ganda.
  // Dengan memanggil `initializeAuth` di sini, sesi pengguna (jika ada token di cookie)
  // akan dipulihkan di server SEBELUM halaman di-render, sehingga mencegah hydration mismatch.
  if (process.server) {
    await authStore.initializeAuth()
  }
  else {
    // Di sisi client, kita juga panggil untuk memastikan inisialisasi jika
    // karena suatu hal tidak berjalan di server.
    await authStore.initializeAuth()
  }
})
