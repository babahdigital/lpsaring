// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk otentikasi dan otorisasi.
 * Berjalan setelah middleware maintenance.
 * Logika ini telah disederhanakan untuk kejelasan dan efisiensi.
 */
export default defineNuxtRouteMiddleware((to: RouteLocationNormalized) => {
  const authStore = useAuthStore()

  const isLoggedIn = authStore.isLoggedIn
  const isAdmin = authStore.isAdmin

  // Halaman yang dapat diakses oleh semua orang (pengguna belum login)
  // Rute root '/' TIDAK termasuk di sini, karena harusnya me-redirect.
  const GUEST_ROUTES = ['/login', '/register', '/admin']

  // Jika halaman tujuan adalah halaman maintenance, lewati middleware ini.
  if (to.path === '/maintenance') {
    return
  }
  
  // --- Logika untuk Pengguna yang Belum Login ---
  if (!isLoggedIn) {
    // Jika tujuan rute BUKAN halaman untuk tamu, redirect ke halaman login yang sesuai.
    if (!GUEST_ROUTES.includes(to.path)) {
      // Jika mencoba akses path admin, arahkan ke login admin.
      if (to.path.startsWith('/admin')) {
        return navigateTo('/admin', { replace: true });
      }
      // Jika tidak, arahkan ke login pengguna biasa.
      return navigateTo('/login', { replace: true });
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
      return navigateTo(isAdmin ? adminDashboard : userDashboard, { replace: true });
    }
  }
})