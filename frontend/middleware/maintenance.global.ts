// frontend/middleware/maintenance.global.ts
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk menangani Maintenance Mode.
 * Logika ini diprioritaskan untuk mengontrol akses selama maintenance.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  const maintenanceStore = useMaintenanceStore()
  const authStore = useAuthStore()

  // Pastikan status auth dan settings sudah dicek/dimuat sebelum middleware berjalan.
  if (!authStore.initialAuthCheckDone) {
    await authStore.initializeAuth();
  }

  const isMaintenanceActive = maintenanceStore.isActive;
  const isMaintenancePage = to.path === '/maintenance';
  const isAdminPath = to.path.startsWith('/admin');
  const isUserLoggedInAdmin = authStore.isLoggedIn && authStore.isAdmin;

  // --- LOGIKA UTAMA ---

  // Jika Mode Maintenance AKTIF
  if (isMaintenanceActive) {
    // KASUS 1: Pengguna adalah ADMIN atau SUPER_ADMIN yang sudah login.
    if (isUserLoggedInAdmin) {
      // PERBAIKAN: Izinkan akses ke semua halaman di dalam '/admin' DAN ke halaman '/akun'.
      if (isAdminPath || to.path === '/akun') {
        return; // Lanjutkan navigasi
      }
      // Jika admin mencoba akses halaman non-admin lainnya,
      // redirect ke dashboard admin mereka.
      else {
        return navigateTo('/admin/dashboard', { replace: true });
      }
    }

    // KASUS 2: Pengguna BUKAN admin yang login (guest, user biasa, atau admin belum login).
    else {
      // Izinkan akses ke halaman login admin (/admin) dan halaman maintenance itu sendiri.
      if (isAdminPath || isMaintenancePage) {
        return; // Lanjutkan navigasi ke /admin (login) atau /maintenance
      }
      
      // Untuk SEMUA PATH LAIN (termasuk /login, /, /dashboard, dll),
      // paksa redirect ke halaman maintenance.
      return navigateTo('/maintenance', { replace: true });
    }
  }
  // Jika Mode Maintenance TIDAK AKTIF
  else {
    // Jika maintenance TIDAK aktif, dan pengguna mencoba akses /maintenance,
    // redirect mereka ke halaman utama.
    if (isMaintenancePage) {
      return navigateTo('/', { replace: true });
    }
  }
})