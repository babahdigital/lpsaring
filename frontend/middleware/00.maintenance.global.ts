import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk menangani Maintenance Mode.
 * Middleware ini membaca state dari Pinia store yang sudah diisi oleh plugin.
 */
export default defineNuxtRouteMiddleware((to) => {
  const maintenanceStore = useMaintenanceStore()
  const authStore = useAuthStore()

  const isMaintenanceActive = maintenanceStore.isActive;
  const isMaintenancePage = to.path === '/maintenance';
  const isAdminPath = to.path.startsWith('/admin');
  
  // PERBAIKAN: Tambahkan path login dan admin ke path yang diizinkan
  // Ini penting agar admin bisa mengakses halaman login saat maintenance aktif.
  const allowedPathsDuringMaintenance = [
    '/maintenance',
    '/login',
    '/admin' // Mengizinkan akses ke root halaman admin (biasanya halaman login admin)
  ];

  // Jika mode maintenance aktif
  if (isMaintenanceActive) {
    // Izinkan admin yang sudah login untuk mengakses area admin manapun
    if (isAdminPath && authStore.isLoggedIn && authStore.isAdmin) {
      return
    }

    // Izinkan akses ke halaman yang secara eksplisit diizinkan (maintenance, login, admin)
    if (allowedPathsDuringMaintenance.includes(to.path)) {
      return
    }

    // Untuk semua kasus lain, redirect ke halaman maintenance
    if (!isMaintenancePage) {
        return navigateTo('/maintenance', { replace: true });
    }
  } 
  // Jika mode maintenance TIDAK aktif
  else {
    // Jika pengguna mencoba mengakses halaman maintenance, redirect ke halaman utama
    if (isMaintenancePage) {
      return navigateTo('/', { replace: true });
    }
  }
})