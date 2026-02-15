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

  const getRedirectTarget = (): string | null => {
    const redirectQuery = to.query.redirect
    const redirectPath = Array.isArray(redirectQuery) ? redirectQuery[0] : redirectQuery
    if (typeof redirectPath !== 'string' || redirectPath.length === 0)
      return null
    if (!redirectPath.startsWith('/'))
      return null

    const disallowedExactPaths = new Set(['/login', '/admin', '/admin/login', '/register', '/daftar', '/captive', '/session/consume'])
    if (disallowedExactPaths.has(redirectPath))
      return null

    if (redirectPath.startsWith('/login/') || redirectPath.startsWith('/captive/') || redirectPath.startsWith('/session/consume/'))
      return null

    return redirectPath
  }

  // Penting: Tunggu hingga pengecekan otentikasi awal selesai.
  // Ini mencegah race condition di mana middleware berjalan sebelum user/token dimuat.
  if (!authStore.initialAuthCheckDone) {
    await authStore.initializeAuth()
  }

  const isLoggedIn = authStore.isLoggedIn
  const isAdmin = authStore.isAdmin

  // Halaman yang dapat diakses oleh pengguna yang belum login (guest).
  // Rute root '/' tidak termasuk di sini karena akan di-redirect.
  const STATUS_ROUTES = [
    '/login/blocked',
    '/login/inactive',
    '/login/expired',
    '/login/habis',
    '/login/fup',
    '/captive/blokir',
    '/captive/inactive',
    '/captive/expired',
    '/captive/habis',
    '/captive/fup',
  ]
  const GUEST_ROUTES = ['/login', '/register', '/daftar', '/admin', '/admin/login', '/captive', '/session/consume', ...STATUS_ROUTES]

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

    if (to.path.startsWith('/captive'))
      return

    // Aturan 1: Pengguna biasa tidak boleh mengakses area admin.
    if (!isAdmin && to.path.startsWith('/admin')) {
      return navigateTo(userDashboard, { replace: true })
    }

    // Aturan 1b: Admin tidak boleh mengakses halaman user,
    // kecuali halaman profil bersama (/akun).
    if (isAdmin && !to.path.startsWith('/admin') && !to.path.startsWith('/captive') && !to.path.startsWith('/akun')) {
      return navigateTo(adminDashboard, { replace: true })
    }

    if (!isAdmin) {
      const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
      const statusRouteMap: Record<string, string> = {
        blocked: '/login/blocked',
        inactive: '/login/inactive',
        expired: '/login/expired',
        habis: '/login/habis',
        fup: '/login/fup',
      }
      const statusRoute = statusRouteMap[accessStatus]
      if (statusRoute && to.path === statusRoute)
        return

      if (accessStatus === 'expired' || accessStatus === 'habis') {
        const allowedPaths = ['/beli', '/payment/finish', statusRouteMap.expired, statusRouteMap.habis]
        if (!allowedPaths.includes(to.path))
          return navigateTo('/beli', { replace: true })
      }
    }

    // Aturan 2: Pengguna yang sudah login (admin/biasa) tidak boleh kembali ke halaman tamu atau root.
    // Arahkan mereka ke dashboard masing-masing.
    if (GUEST_ROUTES.includes(to.path) || to.path === '/') {
      const redirectTarget = getRedirectTarget()
      if (redirectTarget)
        return navigateTo(redirectTarget, { replace: true })

      if (!isAdmin) {
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        const statusRouteMap: Record<string, string> = {
          blocked: '/login/blocked',
          inactive: '/login/inactive',
          expired: '/login/expired',
          habis: '/login/habis',
          fup: '/login/fup',
        }
        const statusRoute = statusRouteMap[accessStatus]
        if (statusRoute && to.path === statusRoute)
          return
      }
      return navigateTo(isAdmin ? adminDashboard : userDashboard, { replace: true })
    }
  }
})
