// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp } from '#app'
import { useAuthStore } from '../store/auth'
import { getStatusRouteForAccessStatus, GUEST_ROUTES, isLegalPublicPath } from '../utils/authRoutePolicy'
import { isCaptiveContextActive, isCaptiveRoutePath, isRestrictedInCaptiveContext, markCaptiveContextActive } from '../utils/captiveContext'
import {
  getSafeRedirectTarget,
  isStatusSelfServicePath,
  resolveExpiredOrHabisRedirect,
  resolveGuestProtectedRedirect,
  resolveLoggedInRoleRedirect,
} from '../utils/authGuardDecisions'
import { resolveHotspotIdentity } from '../utils/hotspotIdentity'
import { shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

const HOTSPOT_PRECHECK_ROUTES = new Set<string>(['/', '/login', '/register', '/daftar'])
const HOTSPOT_AUTO_START_QUERY_KEY = 'auto_start'
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'

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

function buildHotspotIdentityQuery(identity: { clientIp?: string | null, clientMac?: string | null }): Record<string, string> {
  const clientIp = String(identity.clientIp ?? '').trim()
  const clientMac = String(identity.clientMac ?? '').trim()

  return {
    ...(clientIp ? { client_ip: clientIp } : {}),
    ...(clientMac ? { client_mac: clientMac } : {}),
  }
}

function pickHotspotIdentityQuery(query: Record<string, unknown>): Record<string, string> {
  return buildHotspotIdentityQuery({
    clientIp: getQueryValueFromKeys(query, ['client_ip', 'ip', 'client-ip']),
    clientMac: getQueryValueFromKeys(query, ['client_mac', 'mac', 'mac-address', 'client-mac']),
  })
}

function resolveHotspotIdentityQuery(query: Record<string, unknown>): Record<string, string> {
  return buildHotspotIdentityQuery(resolveHotspotIdentity(query))
}

function extractHotspotLoginHint(query: Record<string, unknown>): string | null {
  const directLink = getQueryValueFromKeys(query, ['link_login_only', 'link-login-only', 'link_login', 'link-login', 'linkloginonly'])
  if (directLink)
    return directLink

  const redirectRaw = getQueryValueFromKeys(query, ['redirect'])
  if (!redirectRaw || !redirectRaw.includes('link_login_only='))
    return null

  try {
    const parsed = new URL(redirectRaw, 'https://example.invalid')
    const nested = String(parsed.searchParams.get('link_login_only') ?? '').trim()
    return nested || null
  }
  catch {
    const marker = 'link_login_only='
    const markerIndex = redirectRaw.indexOf(marker)
    if (markerIndex < 0)
      return null
    const after = redirectRaw.slice(markerIndex + marker.length)
    const ampIndex = after.indexOf('&')
    return (ampIndex >= 0 ? after.slice(0, ampIndex) : after).trim() || null
  }
}

function pickHotspotRouteQuery(query: Record<string, unknown>): Record<string, string> {
  const identity = pickHotspotIdentityQuery(query)
  const linkLoginOnly = extractHotspotLoginHint(query)

  return {
    ...identity,
    ...(linkLoginOnly ? { link_login_only: linkLoginOnly } : {}),
  }
}

function resolveHotspotRouteQuery(query: Record<string, unknown>): Record<string, string> {
  const identity = resolveHotspotIdentityQuery(query)
  const linkLoginOnly = extractHotspotLoginHint(query)

  return {
    ...identity,
    ...(linkLoginOnly ? { link_login_only: linkLoginOnly } : {}),
  }
}

function getStoredHotspotLoginHint(): string | null {
  if (typeof window === 'undefined' || typeof window.localStorage === 'undefined')
    return null

  try {
    const value = String(window.localStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
    return value || null
  }
  catch {
    return null
  }
}

function resolveHotspotRecoveryRouteQuery(query: Record<string, unknown>): Record<string, string> {
  const routeQuery = resolveHotspotRouteQuery(query)
  if (routeQuery.link_login_only)
    return routeQuery

  const storedHint = getStoredHotspotLoginHint()
  if (!storedHint)
    return routeQuery

  return {
    ...routeQuery,
    link_login_only: storedHint,
  }
}

function buildHotspotRequiredPath(query: Record<string, string>, options: { autoStart?: boolean } = {}): string {
  const params = new URLSearchParams(query)
  if (options.autoStart)
    params.set(HOTSPOT_AUTO_START_QUERY_KEY, '1')

  const queryString = params.toString()
  return queryString.length > 0
    ? `/login/hotspot-required?${queryString}`
    : '/login/hotspot-required'
}

function hasHotspotContextQuery(query: Record<string, unknown>): boolean {
  return Object.keys(pickHotspotRouteQuery(query)).length > 0
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

    if (!to.path.startsWith('/admin') && hasHotspotContextQuery((to.query as Record<string, unknown>) ?? {})) {
      const hotspotRouteQuery = pickHotspotRouteQuery((to.query as Record<string, unknown>) ?? {})
      const queryString = new URLSearchParams(hotspotRouteQuery).toString()
      const captivePath = queryString.length > 0
        ? `/captive?${queryString}`
        : '/captive'
      return navigateTo(captivePath, { replace: true })
    }

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
    const resolvedHotspotRecoveryQuery = resolveHotspotRecoveryRouteQuery(routeQuery)
    const hasResolvedHotspotRecoveryContext = Object.keys(resolvedHotspotRecoveryQuery).length > 0
    const hotspotIdentityQuery = buildHotspotIdentityQuery({
      clientIp: resolvedHotspotRecoveryQuery.client_ip,
      clientMac: resolvedHotspotRecoveryQuery.client_mac,
    })
    const hasResolvedHotspotIdentity = Object.keys(hotspotIdentityQuery).length > 0

    // Halaman public diizinkan untuk semua role (hindari auto-redirect ke dashboard).
    if (isPublicPage)
      return

    if (!isAdmin) {
      const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
      const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
      if ((accessStatus === 'blocked' || accessStatus === 'inactive') && statusRoute && to.path !== statusRoute)
        return navigateTo(statusRoute, { replace: true })
    }

    if (!isAdmin && isDemoUser) {
      const demoAllowedPaths = ['/beli', '/payment/status', '/payment/finish']
      const isAllowedDemoPath = demoAllowedPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
      if (!isAllowedDemoPath)
        return navigateTo('/beli', { replace: true })
    }

    const shouldRunHotspotPrecheck = (
      HOTSPOT_PRECHECK_ROUTES.has(to.path) && hasResolvedHotspotRecoveryContext
    ) || to.path === '/dashboard'

    if (!isAdmin && HOTSPOT_PRECHECK_ROUTES.has(to.path) && hasResolvedHotspotRecoveryContext && !hasResolvedHotspotIdentity) {
      return navigateTo(buildHotspotRequiredPath(resolvedHotspotRecoveryQuery, { autoStart: true }), { replace: true })
    }

    if (!isAdmin && shouldRunHotspotPrecheck) {
      try {
        const { $api } = useNuxtApp()
        const hotspotStatus = await $api<{ hotspot_login_required?: boolean | null, hotspot_binding_active?: boolean | null }>('/auth/hotspot-session-status', {
          method: 'GET',
          query: hotspotIdentityQuery,
        })

        if (shouldRedirectToHotspotRequired({
          hotspotLoginRequired: hotspotStatus?.hotspot_login_required,
          hotspotBindingActive: hotspotStatus?.hotspot_binding_active,
        })) {
          return navigateTo(buildHotspotRequiredPath(resolvedHotspotRecoveryQuery, { autoStart: true }), { replace: true })
        }
      }
      catch {
        // Best effort. Jika endpoint status gagal, lanjut ke alur guard normal.
      }
    }

    const roleRedirect = resolveLoggedInRoleRedirect(to.path, isAdmin, isKomandan)
    if (roleRedirect)
      return navigateTo(roleRedirect, { replace: true })

    if (!isAdmin) {
      if (isCaptiveContextActive() && isRestrictedInCaptiveContext(to.path)) {
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        if (isStatusSelfServicePath(to.path, accessStatus, isKomandan))
          return
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
