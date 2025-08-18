// middleware/03-user-status.global.ts

import { useAuthStore } from '~/store/auth'

const isCaptiveBrowser = () => import.meta.client && (window as any).__IS_CAPTIVE_BROWSER__

/**
 * Middleware UTAMA (VERSI FINAL) untuk menangani semua status pengguna yang sudah login.
 * PERBAIKAN: Mencegah infinite loop dengan hanya menjalankan syncDevice jika
 * status 'isNewDeviceDetected' belum aktif.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server)
    return

  const authStore = useAuthStore()
  const { isLoggedIn, isAdmin, isBlocked, isQuotaFinished } = authStore

  if (!isLoggedIn || isAdmin)
    return

  // 1. TANGANI STATUS KRITIS TERLEBIH DAHULU
  if (isBlocked) {
    const allowedRoutes = ['/akun/blokir', '/logout', '/captive/blokir']
    if (!allowedRoutes.some(path => to.path.startsWith(path))) {
      const target = isCaptiveBrowser() ? '/captive/blokir' : '/akun/blokir'
      return navigateTo(target, { replace: true })
    }
    return
  }

  if (isQuotaFinished) {
    const allowedRoutes = ['/akun/habis', '/beli', '/payment', '/logout', '/captive/habis', '/captive/beli']
    if (!allowedRoutes.some(path => to.path.startsWith(path))) {
      const target = isCaptiveBrowser() ? '/captive/habis' : '/beli'
      return navigateTo(target, { replace: true })
    }
    return
  }

  // 2. LOGIKA SINKRONISASI DAN OTORISASI PERANGKAT (ANTI-LOOP)
  // Cek dulu apakah state sudah `isNewDeviceDetected`
  if (!authStore.isNewDeviceDetected) {
    // Check if we're on a page that should sync device
    const shouldSync = !to.path.startsWith('/captive') // biarkan middleware captive menangani /captive
      && !to.path.startsWith('/akun/otorisasi-perangkat')
      && !to.path.startsWith('/logout')

    if (shouldSync) {
      // Jika belum, baru jalankan sinkronisasi untuk memeriksa status terkini.
      // ✅ PERBAIKAN: Tambahkan parameter allowAuthorizationFlow: false untuk mencegah
      // popup otorisasi perangkat muncul sebelum login
      const syncResult = await authStore.syncDevice({ allowAuthorizationFlow: false })

      console.log('[USER-STATUS] Sinkronisasi dengan allowAuthorizationFlow=false, status:', syncResult?.status)

      // Handle throttling responses
      if (syncResult?.status === 'THROTTLED' || syncResult?.status === 'RATE_LIMITED') {
        console.log('[USER-STATUS] Sync sedang di-throttle, menunggu...')
        return // Don't redirect, just wait
      }
    }
  }

  // Setelah state mungkin diperbarui oleh syncDevice, cek sekali lagi.
  if (authStore.isNewDeviceDetected) {
    const targetAuthPage = isCaptiveBrowser() ? '/captive/otorisasi-perangkat' : '/akun/otorisasi-perangkat'
    const allowedDuringAuth = [targetAuthPage, '/logout']

    if (!allowedDuringAuth.some(path => to.path.startsWith(path))) {
      console.log(`[USER-STATUS] Perangkat baru terdeteksi. Memaksa redirect ke ${targetAuthPage}`)
      return navigateTo(targetAuthPage, { replace: true })
    }
  }

  // 3. PEMBERSIHAN FINAL UNTUK PENGGUNA NORMAL
  // Hanya alihkan dari halaman status versi non-captive ke dashboard.
  // Jangan ganggu halaman captive agar UX portal berjalan benar.
  const nonCaptiveStatusPages = [
    '/akun/blokir',
    '/akun/habis',
    '/akun/otorisasi-perangkat',
  ]
  if (nonCaptiveStatusPages.some(path => to.path.startsWith(path))) {
    return navigateTo('/dashboard', { replace: true })
  }
})
