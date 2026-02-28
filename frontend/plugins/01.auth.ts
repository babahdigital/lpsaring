// frontend/plugins/01.auth.ts

import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin(async (nuxtApp) => {
  const authStore = useAuthStore()

  // Plugin ini berjalan sekali di sisi server dan sekali di sisi client saat awal muat.
  // Flag 'initialAuthCheckDone' dari store Anda mencegah eksekusi ganda.
  // Dengan memanggil `initializeAuth` di sini, sesi pengguna (jika ada token di cookie)
  // akan dipulihkan di server SEBELUM halaman di-render, sehingga mencegah hydration mismatch.
  if (import.meta.server) {
    await authStore.initializeAuth()
  }
  else {
    // Di sisi client, hindari mutasi state auth saat fase hydration.
    // Fallback inisialisasi dilakukan setelah app mounted.
    // `initializeAuth` sudah idempotent dan akan return cepat bila tidak perlu,
    // tetapi tetap perlu dipanggil agar auto-login best-effort bisa berjalan di client.
    nuxtApp.hook('app:mounted', async () => {
      await authStore.initializeAuth()
    })
  }
})
