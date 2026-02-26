// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '../store/auth'
import { getStatusRouteForAccessStatus, GUEST_ROUTES, isLegalPublicPath } from '../utils/authRoutePolicy'
import {
  getSafeRedirectTarget,
  resolveExpiredOrHabisRedirect,
  resolveGuestProtectedRedirect,
  resolveLoggedInRoleRedirect,
} from '../utils/authGuardDecisions'

/**
 * Middleware untuk otentikasi dan otorisasi.
 * Berjalan setelah middleware maintenance.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  if (isLegalPublicPath(to.path))
    return

  const authStore = useAuthStore()

  // Penting: Tunggu hingga pengecekan otentikasi awal selesai.
  // Ini mencegah race condition di mana middleware berjalan sebelum user/token dimuat.
  if (!authStore.initialAuthCheckDone) {
    await authStore.initializeAuth({ path: to.path, query: to.query as any })
  }

  const isLoggedIn = authStore.isLoggedIn
  const isAdmin = authStore.isAdmin
  const isKomandan = authStore.isKomandan

  // Halaman publik: boleh diakses siapa pun, dan tidak dipaksa redirect ke dashboard.
  // Catatan: `auth: false` dipakai untuk modul auth eksternal; jangan diasumsikan sebagai public.
  const isPublicPage = Boolean((to.meta as any)?.public === true)

  // Halaman yang dapat diakses oleh pengguna yang belum login (guest).
  // Rute root '/' tidak termasuk di sini karena akan di-redirect.
  // Jika tujuan rute adalah halaman maintenance, lewati middleware ini.
  // Logika untuk maintenance sudah ditangani sepenuhnya oleh maintenance.global.ts
  if (to.path === '/maintenance') {
    return
  }

  // --- Logika untuk Pengguna yang Belum Login ---
  if (!isLoggedIn) {
    // Halaman public diizinkan untuk guest.
    if (isPublicPage)
      return

    // Jika tujuan rute BUKAN halaman untuk tamu, redirect ke halaman login yang sesuai.
    const guestRedirect = resolveGuestProtectedRedirect(to.path, to.fullPath)
    if (guestRedirect)
      return navigateTo(guestRedirect, { replace: true })
  }
  // --- Logika untuk Pengguna yang Sudah Login ---
  else {
    const userDashboard = '/dashboard'
    const adminDashboard = '/admin/dashboard'

    // Halaman public diizinkan untuk semua role (hindari auto-redirect ke dashboard).
    if (isPublicPage)
      return

    const roleRedirect = resolveLoggedInRoleRedirect(to.path, isAdmin, isKomandan)
    if (roleRedirect)
      return navigateTo(roleRedirect, { replace: true })

    if (!isAdmin) {
      const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
      const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
      if (statusRoute && to.path === statusRoute)
        return

      const expiredOrHabisRedirect = resolveExpiredOrHabisRedirect(to.path, accessStatus, isKomandan)
      if (expiredOrHabisRedirect)
        return navigateTo(expiredOrHabisRedirect, { replace: true })
    }

    // Aturan 2: Pengguna yang sudah login (admin/biasa) tidak boleh kembali ke halaman tamu atau root.
    // Arahkan mereka ke dashboard masing-masing.
    if (GUEST_ROUTES.includes(to.path) || to.path === '/') {
      const redirectQuery = Array.isArray(to.query.redirect) ? to.query.redirect[0] : to.query.redirect
      const redirectTarget = getSafeRedirectTarget(redirectQuery, isAdmin)
      if (redirectTarget)
        return navigateTo(redirectTarget, { replace: true })

      if (!isAdmin) {
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
        if (statusRoute && to.path === statusRoute)
          return
      }
      return navigateTo(isAdmin ? adminDashboard : userDashboard, { replace: true })
    }
  }
})
