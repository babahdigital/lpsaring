// frontend/middleware/maintenance.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'
import { useMaintenanceStore } from '~/store/maintenance'
import { isLegalPublicPath } from '~/utils/authRoutePolicy'

/**
 * Middleware untuk menangani Maintenance Mode.
 * Logika ini diprioritaskan untuk mengontrol akses selama maintenance.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  const isPathLegalPublic = isLegalPublicPath(to.path)

  const maintenanceStore = useMaintenanceStore()
  const authStore = useAuthStore()

  // Pastikan status auth dan settings sudah dicek/dimuat sebelum middleware berjalan.
  if (!authStore.initialAuthCheckDone) {
    await authStore.initializeAuth({ path: to.path, query: to.query as any })
  }

  const isMaintenanceActive = maintenanceStore.isActive
  const isMaintenancePage = to.path === '/maintenance'
  const isAdminPath = to.path.startsWith('/admin')
  const isUserLoggedInAdmin = authStore.isLoggedIn && authStore.isAdmin

  // --- LOGIKA UTAMA ---

  // Jika Mode Maintenance AKTIF
  if (isMaintenanceActive) {
    if (isPathLegalPublic)
      return

    // KASUS 1: Pengguna adalah ADMIN atau SUPER_ADMIN yang sudah login.
    if (isUserLoggedInAdmin) {
      // PERBAIKAN: Izinkan akses ke semua halaman di dalam '/admin' DAN ke halaman '/akun'.
      if (isAdminPath || to.path === '/akun') {
        // Lanjutkan navigasi
      }
      // Jika admin mencoba akses halaman non-admin lainnya,
      // redirect ke dashboard admin mereka.
      else {
        return navigateTo('/admin/dashboard', { replace: true })
      }
    }

    // KASUS 2: Pengguna BUKAN admin yang login (guest, user biasa, atau admin belum login).
    else {
      // Izinkan akses ke halaman login admin (/admin) dan halaman maintenance itu sendiri.
      if (isAdminPath || isMaintenancePage) {
        return // Lanjutkan navigasi ke /admin (login) atau /maintenance
      }

      // Untuk SEMUA PATH LAIN (termasuk /login, /, /dashboard, dll),
      // paksa redirect ke halaman maintenance.
      return navigateTo('/maintenance', { replace: true })
    }
  }
  // Jika Mode Maintenance TIDAK AKTIF
  else {
    // Jika maintenance TIDAK aktif, dan pengguna mencoba akses /maintenance,
    // redirect mereka ke halaman utama.
    if (isMaintenancePage) {
      return navigateTo('/', { replace: true })
    }
  }
})
