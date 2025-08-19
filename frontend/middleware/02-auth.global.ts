// middleware/02-auth.global.ts

import { useAuthStore } from '~/store/auth'
import { UserRole } from '~/types/enums'
import { extractClientParams } from '~/utils/url-params'

/**
 * Middleware utama yang menangani semua logika redirect berdasarkan status login dan peran.
 * Logika ini telah dikonsolidasi untuk mencakup deteksi Captive Portal.
 * Berjalan SETELAH 01-wait-for-auth.global.ts.
 */
function isCaptiveBrowser(): boolean {
  if (import.meta.server)
    return false

  // Cek flag global yang mungkin sudah di-set
  if ((window as any).__IS_CAPTIVE_BROWSER__)
    return true

  // Lakukan deteksi jika flag belum ada
  const userAgent = navigator.userAgent
  const captivePatterns = [
    /CaptiveNetworkSupport/i,
    /Apple-captive/i,
    /iOS.*CaptiveNetworkSupport/i,
    /Android.*CaptivePortalLogin/i,
    /dalvik/i,
    /Microsoft-CryptoAPI/i,
    /Microsoft NCSI/i,
    /wispr/i,
    /CaptivePortal/i,
    /ConnectivityCheck/i,
    /NetworkProbe/i,
  ]

  const detected = captivePatterns.some(pattern => pattern.test(userAgent))
  if (detected) {
    (window as any).__IS_CAPTIVE_BROWSER__ = true
  }
  return detected
}

export default defineNuxtRouteMiddleware((to) => {
  const authStore = useAuthStore()
  let { isLoggedIn, isAdmin, isDeviceAuthRequired } = authStore

  // OPTIMASI: Jangan lakukan redirect jika sedang dalam proses otorisasi perangkat
  if (isDeviceAuthRequired && isLoggedIn) {
    console.log('[AUTH-MIDDLEWARE] Mendeteksi otorisasi perangkat aktif, skip redirect')
    return // Biarkan render normal tanpa redirect
  }

  // Also check localStorage for admin flag as backup
  if (!isAdmin && typeof window !== 'undefined') {
    const localStorageAdmin = localStorage.getItem('is_admin_user') === 'true'
    if (localStorageAdmin) {
      console.log('[AUTH-MIDDLEWARE] Admin flag found in localStorage but not in store')
      isAdmin = true

      // Check for redirect after reload
      const redirectAfterReload = localStorage.getItem('admin_redirect_after_reload')
      if (redirectAfterReload) {
        console.log('[AUTH-MIDDLEWARE] Found redirect instruction after reload:', redirectAfterReload)
        localStorage.removeItem('admin_redirect_after_reload')
        window.location.href = redirectAfterReload
        return
      }
    }
  }

  const captiveDetected = isCaptiveBrowser()

  // --- ATURAN 1: UNTUK PENGGUNA YANG SUDAH LOGIN ---
  if (isLoggedIn) {
    // Check admin status from multiple sources to ensure consistency
    const isAdminUser = isAdmin || localStorage.getItem('is_admin_user') === 'true'

    // Ensure user role is properly set if admin flag exists
    if (isAdminUser && authStore.user && !authStore.user.role) {
      console.log('[AUTH-MIDDLEWARE] User has admin flag but no role, fixing user object')

      // Set admin role in user object
      authStore.setUser({
        ...authStore.user,
        role: UserRole.ADMIN, // Default to ADMIN, will be verified later if needed
      })
    }

    console.log('[AUTH-MIDDLEWARE] User is logged in:', isLoggedIn, 'isAdmin:', isAdminUser, 'Role:', authStore.user?.role)
    const guestOnlyRoutes = ['/login', '/register', '/admin/login']
    const isGoingToGuestPage = guestOnlyRoutes.some(path => to.path.startsWith(path))

    if (isGoingToGuestPage) {
      const destination = isAdminUser ? '/admin/dashboard' : '/dashboard'
      console.log('[AUTH-MIDDLEWARE] Redirecting from guest page to:', destination, '(isAdmin:', isAdminUser, ')')
      return navigateTo(destination, { replace: true })
    }

    if (to.path.startsWith('/admin')) {
      // Extra check for admin paths
      const isAdminInStore = authStore.isAdmin
      const isAdminInLocalStorage = localStorage.getItem('is_admin_user') === 'true'

      console.log('[AUTH-MIDDLEWARE] Accessing admin path:', to.path)
      console.log('[AUTH-MIDDLEWARE] Admin checks - store:', isAdminInStore, 'localStorage:', isAdminInLocalStorage)

      if (isAdminInLocalStorage && !isAdminInStore) {
        // If admin flag is in localStorage but not in store, need to refresh user data
        console.log('[AUTH-MIDDLEWARE] Admin flag found in localStorage but not in store')

        // Force admin status immediately for this navigation
        isAdmin = true

        // If admin/dashboard specifically, allow access (we know they're admin)
        if (to.path === '/admin/dashboard') {
          console.log('[AUTH-MIDDLEWARE] Allowing admin dashboard access based on localStorage flag')
          // Let it proceed to dashboard
          return
        }
      }

      // If not admin, redirect to user dashboard
      if (!isAdmin && !isAdminInLocalStorage) {
        console.log('[AUTH-MIDDLEWARE] Non-admin accessing admin route, redirecting to user dashboard')
        return navigateTo('/dashboard', { replace: true })
      }
    }

    // Jika pengguna login berada di captive portal tapi tidak di halaman /captive/*, arahkan.
    if (captiveDetected && !to.path.startsWith('/captive')) {
      // (Logika ini akan ditangani oleh 03-user-status untuk mengarahkan ke halaman status yang benar)
      console.log('[AUTH] Pengguna login terdeteksi di captive browser, biarkan 03-user-status menangani.')
    }
  }
  // --- ATURAN 2: UNTUK TAMU (BELUM LOGIN) ---
  else {
    const publicRoutes = ['/login', '/register', '/admin/login', '/captive', '/', '/maintenance', '/error', '/access-denied']
    const isGoingToPublicPage = publicRoutes.some(path => to.path.startsWith(path))

    // Jika tamu terdeteksi di captive browser dan belum di halaman captive,
    // arahkan ke sana dengan membawa parameter.
    if (captiveDetected && !to.path.startsWith('/captive')) {
      const { clientIp, clientMac } = extractClientParams(to.query)
      const query = (clientIp || clientMac) ? { client_ip: clientIp, client_mac: clientMac } : {}
      return navigateTo({ path: '/captive', query, replace: true })
    }

    // Jika tamu mencoba mengakses halaman yang tidak publik, arahkan ke login.
    if (!isGoingToPublicPage) {
      // Determine the appropriate login page based on the path
      const destination = to.path.startsWith('/admin') ? '/admin/login' : '/login'

      // Add the redirect query parameter for post-login redirection
      const query = to.fullPath !== '/' ? { redirect: to.fullPath } : undefined

      return navigateTo({
        path: destination,
        query,
        replace: true
      })
    }
  }
})
