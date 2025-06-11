// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'
// useMaintenanceStore tidak perlu diimpor di sini lagi karena sudah ditangani oleh 00.maintenance.global.ts

export default defineNuxtRouteMiddleware((to: RouteLocationNormalized) => {
  const authStore = useAuthStore()

  // --- Catatan: Logika Maintenance SUDAH DITANGANI oleh 00.maintenance.global.ts ---
  // Middleware ini hanya akan berjalan jika tidak di-redirect oleh middleware maintenance.
  // Jadi, kita tidak perlu lagi memeriksa maintenance mode di sini.

  const isLoggedIn = authStore.isLoggedIn;
  const isAdmin = authStore.isAdmin;
  
  const isTargetingAdminRoute = to.path.startsWith('/admin');
  const isTargetingAdminLoginPage = to.path === '/admin';
  const isTargetingPublicUserRoute = ['/login', '/register'].includes(to.path);
  // Tambahkan rute publik lain jika ada, misal: '/', '/about', '/contact'
  const isPublicRoute = isTargetingPublicUserRoute || to.path === '/' || to.path === '/about'; // Sesuaikan dengan rute publik Anda

  if (!isLoggedIn) {
    // Jika belum login & mencoba akses halaman admin (selain login) -> ke login admin
    if (isTargetingAdminRoute && !isTargetingAdminLoginPage) {
      return navigateTo('/admin', { replace: true });
    }
    // Jika belum login & mencoba akses halaman non-publik non-admin -> ke login user
    // Perhatikan: ini akan menangkap rute dashboard user jika tidak public
    if (!isTargetingAdminRoute && !isPublicRoute) { 
      return navigateTo('/login', { replace: true });
    }
  } else { // Jika sudah login
    // Jika admin, tapi mencoba ke halaman login admin/user atau register -> ke dashboard admin
    if (isAdmin && (isTargetingPublicUserRoute || isTargetingAdminLoginPage || isPublicRoute)) {
      return navigateTo('/admin/dashboard', { replace: true });
    }
    // Jika user biasa, tapi mencoba ke area admin -> ke dashboard user
    if (!isAdmin && isTargetingAdminRoute) {
      return navigateTo('/dashboard', { replace: true });
    }
    // Jika user biasa, tapi mencoba ke halaman login/register/publik lain yang tidak seharusnya diakses setelah login -> ke dashboard user
    if (!isAdmin && (isTargetingPublicUserRoute || isPublicRoute)) {
        return navigateTo('/dashboard', { replace: true });
    }
  }
})