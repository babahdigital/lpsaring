// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'
import { normalizeRedirectTarget } from '~/utils/authGuards'

/**
 * Middleware untuk otentikasi dan otorisasi.
 * Berjalan setelah middleware maintenance.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
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

  const getRedirectTarget = (): string | null => {
    const redirectQuery = to.query.redirect
    const redirectPath = Array.isArray(redirectQuery) ? redirectQuery[0] : redirectQuery
    const normalized = normalizeRedirectTarget(redirectPath, '')
    if (normalized.length === 0)
      return null

    // Selalu blokir rute auth/guest umum agar tidak terjadi loop.
    const disallowedPrefixes = ['/login', '/register', '/daftar', '/captive', '/session/consume']
    if (disallowedPrefixes.some(prefix => normalized === prefix || normalized.startsWith(`${prefix}/`)))
      return null

    // Untuk admin/superadmin: izinkan redirect ke /admin/* KECUALI halaman login admin itu sendiri.
    // Ini penting karena plugin API bisa menambahkan redirect=/admin/settings/... saat 401, dan
    // jika kita blokir semua /admin, user akan selalu jatuh ke /admin/dashboard.
    if (normalized === '/admin' || normalized === '/admin/login' || normalized.startsWith('/admin/login/'))
      return null

    // Untuk non-admin: jangan izinkan redirect ke area /admin.
    if (!isAdmin && (normalized === '/admin' || normalized.startsWith('/admin/')))
      return null

    return normalized
  }

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
    // Halaman public diizinkan untuk guest.
    if (isPublicPage)
      return

    // Jika tujuan rute BUKAN halaman untuk tamu, redirect ke halaman login yang sesuai.
    if (!GUEST_ROUTES.includes(to.path)) {
      // Jika mencoba akses path admin yang dilindungi (bukan /admin itu sendiri),
      // arahkan ke login admin.
      if (to.path.startsWith('/admin/')) {
        return navigateTo('/admin', { replace: true })
      }
      // Jika mencoba akses path user yang dilindungi, arahkan ke login user.
      if (!to.path.startsWith('/admin')) {
        // Simpan tujuan awal agar setelah login tidak jatuh ke dashboard.
        const redirect = encodeURIComponent(to.fullPath)
        return navigateTo(`/login?redirect=${redirect}`, { replace: true })
      }
    }
  }
  // --- Logika untuk Pengguna yang Sudah Login ---
  else {
    const userDashboard = '/dashboard'
    const adminDashboard = '/admin/dashboard'

    // Halaman public diizinkan untuk semua role (hindari auto-redirect ke dashboard).
    if (isPublicPage)
      return

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

    // Aturan khusus Komandan:
    // - Komandan tidak belanja paket dan tidak memakai riwayat transaksi biasa.
    // - Hanya Komandan yang boleh mengakses halaman request.
    if (!isAdmin) {
      if (isKomandan && (to.path === '/beli' || to.path.startsWith('/beli/') || to.path === '/riwayat' || to.path.startsWith('/riwayat/')))
        return navigateTo('/requests', { replace: true })

      if (!isKomandan && (to.path === '/requests' || to.path.startsWith('/requests/')))
        return navigateTo(userDashboard, { replace: true })
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
        const destination = isKomandan ? '/requests' : '/beli'
        const allowedPaths = [destination, '/payment/status', '/payment/finish', statusRouteMap.expired, statusRouteMap.habis]
        if (!allowedPaths.includes(to.path))
          return navigateTo(destination, { replace: true })
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
