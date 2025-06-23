// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk otentikasi dan otorisasi.
 * Berjalan setelah middleware maintenance.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  const authStore = useAuthStore()

  // Penting: Tunggu hingga pengecekan otentikasi awal selesai.
  // Ini mencegah race condition di mana middleware berjalan sebelum user/token dimuat.
  if (!authStore.initialAuthCheckDone) {
    await authStore.initializeAuth()
  }

  const isLoggedIn = authStore.isLoggedIn
  const isAdmin = authStore.isAdmin

  // Halaman yang dapat diakses oleh pengguna yang belum login (guest).
  // Rute root '/' tidak termasuk di sini karena akan di-redirect.
  const GUEST_ROUTES = ['/login', '/register', '/admin']

  // Jika tujuan rute adalah halaman maintenance, lewati middleware ini.
  // Logika untuk maintenance sudah ditangani sepenuhnya oleh maintenance.global.ts
  if (to.path === '/maintenance') {
    return
  }

  // --- Logika untuk Pengguna yang Belum Login ---
  if (!isLoggedIn) {
    // Jika tujuan rute BUKAN halaman untuk tamu, redirect ke halaman login yang sesuai.
    if (!GUEST_ROUTES.includes(to.path)) {
      // Jika mencoba akses path admin yang dilindungi (bukan /admin itu sendiri),
      // arahkan ke login admin.
      if (to.path.startsWith('/admin/')) {
        return navigateTo('/admin', { replace: true })
      }
      // Jika mencoba akses path user yang dilindungi, arahkan ke login user.
      if (!to.path.startsWith('/admin')) {
        return navigateTo('/login', { replace: true })
      }
    }
  }
  // --- Logika untuk Pengguna yang Sudah Login ---
  else {
    const userDashboard = '/dashboard'
    const adminDashboard = '/admin/dashboard'

    // Aturan 1: Pengguna biasa tidak boleh mengakses area admin.
    if (!isAdmin && to.path.startsWith('/admin')) {
      return navigateTo(userDashboard, { replace: true })
    }

    // Aturan 2: Pengguna yang sudah login (admin/biasa) tidak boleh kembali ke halaman tamu atau root.
    // Arahkan mereka ke dashboard masing-masing.
    if (GUEST_ROUTES.includes(to.path) || to.path === '/') {
      return navigateTo(isAdmin ? adminDashboard : userDashboard, { replace: true })
    }
  }
})
