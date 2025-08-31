// middleware/03-user-status.global.ts

import { useAuthStore } from '~/store/auth'
import { API_ENDPOINTS } from '~/constants/api-endpoints'
import { useClientDetection } from '~/composables/useClientDetection'

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
  const { isLoggedIn, isAdmin, isBlocked, isQuotaFinished, isInactive } = authStore

  if (!isLoggedIn || isAdmin)
    return

  // 0. OTORISASI PERANGKAT SEBAGAI PRASYARAT
  // Jika otorisasi perangkat sedang atau masih diperlukan, prioritaskan halaman otorisasi
  const targetAuthPage = isCaptiveBrowser() ? '/captive/otorisasi-perangkat' : '/akun/otorisasi-perangkat'
  if (authStore.isDeviceAuthRequired || authStore.isNewDeviceDetected) {
    const allowedDuringAuth = [targetAuthPage, '/logout']
    if (!allowedDuringAuth.some(path => to.path.startsWith(path))) {
      return navigateTo(targetAuthPage, { replace: true })
    }
    return // Jangan proses status lain sampai otorisasi selesai
  }

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

  // Pengguna non-aktif: arahkan ke halaman info/inactive atau izinkan akses ke pembelian
  if (isInactive) {
    const allowedRoutes = ['/akun/inactive', '/beli', '/payment', '/logout']
    if (!allowedRoutes.some(path => to.path.startsWith(path))) {
      const target = '/akun/inactive'
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

      // Tambah validasi perangkat pasca-sync: pastikan MAC saat ini memang terotorisasi
      try {
        const { detectClientInfo } = useClientDetection()
        const det = await detectClientInfo()
        const currentMac = det?.summary?.detected_mac || null
        if (currentMac) {
          const { $api } = useNuxtApp()
          const res = await $api(API_ENDPOINTS.DEVICE_VALIDATE, {
            method: 'POST',
            body: { mac_address: currentMac },
            retry: false,
          }) as any
          if (res && res.is_valid === false) {
            console.warn('[USER-STATUS] Perangkat belum terotorisasi, mengarahkan ke halaman otorisasi')
            authStore.setDeviceAuthRequired(true)
            const targetAuthPage = isCaptiveBrowser() ? '/captive/otorisasi-perangkat' : '/akun/otorisasi-perangkat'
            return navigateTo(targetAuthPage, { replace: true })
          }
        }
      }
      catch (e) {
        console.warn('[USER-STATUS] Validasi perangkat gagal, lanjutkan tanpa redirect:', e)
      }
    }
  }

  // Setelah state mungkin diperbarui oleh syncDevice, pengecekan redirect otorisasi tidak diperlukan di sini

  // 3. PEMBERSIHAN FINAL UNTUK PENGGUNA NORMAL (tanpa menyebabkan loop)
  // Jangan pernah memaksa redirect dari halaman otorisasi perangkat saat otorisasi masih diperlukan.
  if (to.path.startsWith('/akun/otorisasi-perangkat')) {
    if (!authStore.isDeviceAuthRequired && !authStore.isNewDeviceDetected) {
      // Otorisasi sudah selesai, barulah kembalikan ke dashboard
      return navigateTo('/dashboard', { replace: true })
    }
    return // tetap di halaman otorisasi
  }

  // Untuk halaman status lain (blokir/habis), arahkan ke tujuan yang sesuai bila perlu.
  if (to.path.startsWith('/akun/blokir')) {
    if (!isBlocked) return navigateTo('/dashboard', { replace: true })
  }
  if (to.path.startsWith('/akun/habis')) {
    if (!isQuotaFinished) return navigateTo('/dashboard', { replace: true })
  }
})
