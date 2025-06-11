// frontend/middleware/00.maintenance.global.ts
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk menangani Maintenance Mode.
 * Middleware ini sekarang sangat cepat dan sinkron karena hanya membaca
 * state dari Pinia store yang sudah diisi oleh plugin `00.load-initial-state.ts`.
 */
export default defineNuxtRouteMiddleware((to) => {
  const maintenanceStore = useMaintenanceStore()
  const authStore = useAuthStore()

  const isMaintenanceActive = maintenanceStore.isActive
  const isMaintenancePage = to.path === '/maintenance'
  const isAdminPath = to.path.startsWith('/admin')
  
  // Rute yang selalu bisa diakses meskipun maintenance aktif
  const allowedPathsDuringMaintenance = ['/maintenance']

  // Jika mode maintenance aktif
  if (isMaintenanceActive) {
    // Izinkan admin yang sudah login untuk mengakses area admin
    if (isAdminPath && authStore.isLoggedIn && authStore.isAdmin) {
      return
    }

    // Jika tujuan adalah salah satu halaman yang diizinkan, biarkan
    if (allowedPathsDuringMaintenance.includes(to.path)) {
      return
    }

    // Untuk semua kasus lain, redirect ke halaman maintenance
    if (!isMaintenancePage) {
        return navigateTo('/maintenance', { replace: true })
    }
  }
  // Jika mode maintenance TIDAK aktif
  else {
    // Jika pengguna mencoba mengakses halaman maintenance, redirect ke halaman utama
    if (isMaintenancePage) {
      return navigateTo('/', { replace: true })
    }
  }
})