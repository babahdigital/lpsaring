// plugins/03.init.client.ts
import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin(async () => {
  const authStore = useAuthStore()

  // Jika pengecekan autentikasi sudah selesai (misalnya karena navigasi antar halaman),
  // tidak perlu melakukan inisialisasi ulang.
  if (authStore.isAuthCheckDone)
    return

  try {
    // `initializeAuth` akan secara cerdas menggunakan token dari localStorage
    // jika cookie HttpOnly tidak dapat diakses, lalu fetch data pengguna.
    await authStore.initializeAuth()

    // Device sync will be handled by middleware - no need to duplicate here
    if (authStore.isLoggedIn && !authStore.isAdmin) {
      console.log('[AUTH INIT PLUGIN] Auth initialized, device sync will be handled by middleware')
    }
  }
  catch (error) {
    console.error('[AUTH INIT PLUGIN] Gagal melakukan inisialisasi autentikasi di klien:', error)

    // Walaupun gagal, kita harus tetap menandai pengecekan selesai
    // agar middleware navigasi bisa berjalan dan tidak terjebak menunggu.
    authStore.finishAuthCheck()
  }
})
