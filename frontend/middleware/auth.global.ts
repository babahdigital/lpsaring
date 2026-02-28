// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp } from '#app'
import { useAuthStore } from '../store/auth'
import { getStatusRouteForAccessStatus, GUEST_ROUTES, isLegalPublicPath } from '../utils/authRoutePolicy'
import { isCaptiveContextActive, isCaptiveRoutePath, isRestrictedInCaptiveContext, markCaptiveContextActive } from '../utils/captiveContext'
import {
  getSafeRedirectTarget,
  resolveExpiredOrHabisRedirect,
  resolveGuestProtectedRedirect,
  resolveLoggedInRoleRedirect,
} from '../utils/authGuardDecisions'
import { shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

const HOTSPOT_PRECHECK_ROUTES = new Set<string>(['/', '/login', '/register', '/daftar'])

function getQueryValueFromKeys(query: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = query[key]
    if (Array.isArray(value)) {
      const first = String(value[0] ?? '').trim()
      if (first)
        return first
      continue
    }
    const text = String(value ?? '').trim()
    if (text)
      return text
  }
  return null
}

function pickHotspotIdentityQuery(query: Record<string, unknown>): Record<string, string> {
  const clientIp = getQueryValueFromKeys(query, ['client_ip', 'ip', 'client-ip'])
  const clientMac = getQueryValueFromKeys(query, ['client_mac', 'mac', 'mac-address', 'client-mac'])
  return {
    ...(clientIp ? { client_ip: clientIp } : {}),
    ...(clientMac ? { client_mac: clientMac } : {}),
  }
}

/**
 * Middleware untuk otentikasi dan otorisasi.
 * Berjalan setelah middleware maintenance.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  if (isLegalPublicPath(to.path))
    return

  if (isCaptiveRoutePath(to.path))
    markCaptiveContextActive()

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
    const isDemoUser = authStore.currentUser?.is_demo_user === true
    const routeQuery = (to.query as Record<string, unknown>) ?? {}

    // Halaman public diizinkan untuk semua role (hindari auto-redirect ke dashboard).
    if (isPublicPage)
      return

    if (!isAdmin && HOTSPOT_PRECHECK_ROUTES.has(to.path)) {
      try {
        const { $api } = useNuxtApp()
        const identityQuery = pickHotspotIdentityQuery(routeQuery)
        const hotspotStatus = await $api<{ hotspot_login_required?: boolean | null, hotspot_binding_active?: boolean | null, hotspot_session_active?: boolean | null }>('/auth/hotspot-session-status', {
          method: 'GET',
          query: identityQuery,
        })

        if (shouldRedirectToHotspotRequired({
          hotspotLoginRequired: hotspotStatus?.hotspot_login_required,
          hotspotBindingActive: hotspotStatus?.hotspot_binding_active,
          hotspotSessionActive: hotspotStatus?.hotspot_session_active,
        })) {
          const hotspotQuery = pickHotspotIdentityQuery(routeQuery)
          const queryString = new URLSearchParams(hotspotQuery).toString()
          const hotspotRequiredPath = queryString.length > 0
            ? `/login/hotspot-required?${queryString}`
            : '/login/hotspot-required'
          return navigateTo(hotspotRequiredPath, { replace: true })
        }
      }
      catch {
        // Best effort. Jika endpoint status gagal, lanjut ke alur guard normal.
      }
    }

    const roleRedirect = resolveLoggedInRoleRedirect(to.path, isAdmin, isKomandan)
    if (roleRedirect)
      return navigateTo(roleRedirect, { replace: true })

    if (!isAdmin && isDemoUser) {
      const demoAllowedPaths = ['/beli', '/payment/status', '/payment/finish']
      const isAllowedDemoPath = demoAllowedPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
      if (!isAllowedDemoPath)
        return navigateTo('/beli', { replace: true })
    }

    if (!isAdmin) {
      if (isCaptiveContextActive() && isRestrictedInCaptiveContext(to.path)) {
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        const captiveStatusRoute = getStatusRouteForAccessStatus(accessStatus, 'captive')
        if (captiveStatusRoute && captiveStatusRoute !== to.path)
          return navigateTo(captiveStatusRoute, { replace: true })
        return navigateTo('/captive/terhubung', { replace: true })
      }

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
