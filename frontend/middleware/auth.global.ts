// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp, useRuntimeConfig } from '#app'
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
import {
  extractTrustedHotspotLoginHintFromQuery,
  resolveHotspotTrustConfig,
  sanitizeHotspotLoginHint,
  sanitizeResolvedHotspotIdentity,
  type HotspotTrustConfig,
} from '../utils/hotspotTrust'
import { shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

const HOTSPOT_PRECHECK_ROUTES = new Set<string>(['/', '/login', '/register', '/daftar'])
const HOTSPOT_AUTO_START_QUERY_KEY = 'auto_start'
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'
const REDIRECT_CHAIN_KEY = 'lpsaring:auth-redirect-chain'
const MAX_AUTH_REDIRECTS = 5

interface RedirectChainState {
  count: number
  lastPath: string
  ts: number
}

function readRedirectChain(): RedirectChainState | null {
  if (!import.meta.client)
    return null
  try {
    const raw = window.sessionStorage.getItem(REDIRECT_CHAIN_KEY)
    if (!raw)
      return null
    const parsed = JSON.parse(raw) as Partial<RedirectChainState>
    if (typeof parsed?.count === 'number' && typeof parsed?.lastPath === 'string' && typeof parsed?.ts === 'number')
      return parsed as RedirectChainState
  }
  catch {}
  return null
}

function writeRedirectChain(state: RedirectChainState | null): void {
  if (!import.meta.client)
    return
  try {
    if (state == null)
      window.sessionStorage.removeItem(REDIRECT_CHAIN_KEY)
    else
      window.sessionStorage.setItem(REDIRECT_CHAIN_KEY, JSON.stringify(state))
  }
  catch {}
}

function trackRedirect(currentPath: string, target: string): boolean {
  if (!import.meta.client)
    return true
  const now = Date.now()
  const prior = readRedirectChain()
  if (prior == null || now - prior.ts > 5000 || prior.lastPath !== currentPath) {
    writeRedirectChain({ count: 1, lastPath: target, ts: now })
    return true
  }
  if (prior.count >= MAX_AUTH_REDIRECTS) {
    if (import.meta.dev)
      console.warn(`[auth.global] Redirect loop terdeteksi (${prior.count}x), abort: ${currentPath} -> ${target}`)
    writeRedirectChain(null)
    return false
  }
  writeRedirectChain({ count: prior.count + 1, lastPath: target, ts: now })
  return true
}

function clearRedirectChain(): void {
  writeRedirectChain(null)
}

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

function pickHotspotIdentityQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): Record<string, string> {
  return buildHotspotIdentityQuery(sanitizeResolvedHotspotIdentity({
    clientIp: getQueryValueFromKeys(query, ['client_ip', 'ip', 'client-ip']),
    clientMac: getQueryValueFromKeys(query, ['client_mac', 'mac', 'mac-address', 'client-mac']),
  }, trustConfig))
}

function resolveHotspotIdentityQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): Record<string, string> {
  return buildHotspotIdentityQuery(resolveHotspotIdentity(query, trustConfig))
}

function pickHotspotRouteQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): Record<string, string> {
  const identity = pickHotspotIdentityQuery(query, trustConfig)
  const linkLoginOnly = extractTrustedHotspotLoginHintFromQuery(query, trustConfig)

  return {
    ...identity,
    ...(linkLoginOnly ? { link_login_only: linkLoginOnly } : {}),
  }
}

function resolveHotspotRouteQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): Record<string, string> {
  const identity = resolveHotspotIdentityQuery(query, trustConfig)
  const linkLoginOnly = extractTrustedHotspotLoginHintFromQuery(query, trustConfig)

  return {
    ...identity,
    ...(linkLoginOnly ? { link_login_only: linkLoginOnly } : {}),
  }
}

function getStoredHotspotLoginHint(trustConfig: HotspotTrustConfig): string | null {
  if (typeof window === 'undefined' || typeof window.localStorage === 'undefined')
    return null

  try {
    const value = String(window.localStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
    if (!value)
      return null

    const sanitized = sanitizeHotspotLoginHint(value, trustConfig)
    if (!sanitized) {
      window.localStorage.removeItem(LAST_MIKROTIK_LOGIN_HINT_KEY)
      return null
    }

    return sanitized
  }
  catch {
    return null
  }
}

function resolveHotspotRecoveryRouteQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): Record<string, string> {
  const routeQuery = resolveHotspotRouteQuery(query, trustConfig)
  if (routeQuery.link_login_only)
    return routeQuery

  const storedHint = getStoredHotspotLoginHint(trustConfig)
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

function hasHotspotContextQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): boolean {
  return Object.keys(pickHotspotRouteQuery(query, trustConfig)).length > 0
}

/**
 * Middleware untuk otentikasi dan otorisasi.
 *
 * CATATAN ORDER: Nuxt 3 load global middleware alphabetically. File ini
 * (`auth.global`) jalan SEBELUM `maintenance.global`. Maka di awal, kita
 * cek maintenance mode dulu; kalau aktif (dan user bukan admin login),
 * return cepat supaya `maintenance.global` yang melakukan redirect ke
 * `/maintenance` (cegah flicker `/dashboard → /login → /maintenance`).
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  if (isLegalPublicPath(to.path)) {
    clearRedirectChain()
    return
  }

  // Sprint 16 BUG (frontend agent): early-exit kalau maintenance aktif &
  // user bukan admin login. Maintenance middleware jalan setelah ini dan
  // akan handle redirect ke /maintenance. Tanpa early-exit, auth logic
  // bisa redirect ke /login dulu → maintenance.global redirect lagi ke
  // /maintenance → flicker 2-hop di address bar.
  try {
    const { useMaintenanceStore } = await import('~/store/maintenance')
    const maintenanceStore = useMaintenanceStore()
    if (maintenanceStore.isActive && to.path !== '/maintenance' && !to.path.startsWith('/admin')) {
      const authStore = useAuthStore()
      const isAdminLoggedIn = authStore.isLoggedIn && authStore.isAdmin
      if (!isAdminLoggedIn) {
        // Biarkan maintenance.global yang redirect.
        return
      }
    }
  }
  catch {
    // Store belum init — lanjut auth logic biasa.
  }

  const guardedNavigate = (target: string) => {
    if (!trackRedirect(to.path, target))
      return undefined
    return navigateTo(target, { replace: true })
  }

  if (isCaptiveRoutePath(to.path))
    markCaptiveContextActive()

  const authStore = useAuthStore()
  const runtimeConfig = useRuntimeConfig()
  const hotspotTrustConfig = resolveHotspotTrustConfig({
    hotspotAllowedClientCidrs: runtimeConfig.public.hotspotAllowedClientCidrs,
    hotspotTrustedLoginHosts: runtimeConfig.public.hotspotTrustedLoginHosts,
    trustedLoginUrls: [runtimeConfig.public.appLinkMikrotik, runtimeConfig.public.mikrotikLoginUrl],
  })

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

    // L-C6: Cegah lock-in di /captive. Guest yang sudah AKTIF di /captive (atau
    // page /captive/*) jangan di-redirect lagi ke /captive — biarkan flow continue
    // di /captive page itu sendiri. Sebelumnya: user di /captive klik link/refresh
    // → middleware re-redirect ke /captive dengan query baru → infinite loop
    // sampai trackRedirect chain guard kena 5-redirect-max.
    // CATATAN: /login TETAP boleh di-redirect ke /captive — karena user dari portal
    // MikroTik datang dengan client_ip/mac di /login dan harus diarahkan ke
    // /captive bridge page (existing behavior, ada test runtime untuk ini).
    if (
      !to.path.startsWith('/admin')
      && !to.path.startsWith('/captive')
      && hasHotspotContextQuery((to.query as Record<string, unknown>) ?? {}, hotspotTrustConfig)
    ) {
      const hotspotRouteQuery = pickHotspotRouteQuery((to.query as Record<string, unknown>) ?? {}, hotspotTrustConfig)
      const queryString = new URLSearchParams(hotspotRouteQuery).toString()
      const captivePath = queryString.length > 0
        ? `/captive?${queryString}`
        : '/captive'
      return guardedNavigate(captivePath)
    }

    // Jika tujuan rute BUKAN halaman untuk tamu, redirect ke halaman login yang sesuai.
    const guestRedirect = resolveGuestProtectedRedirect(to.path, to.fullPath)
    if (guestRedirect)
      return guardedNavigate(guestRedirect)
  }
  // --- Logika untuk Pengguna yang Sudah Login ---
  else {
    const userDashboard = '/dashboard'
    const adminDashboard = '/admin/dashboard'
    const isDemoUser = authStore.currentUser?.is_demo_user === true
    const routeQuery = (to.query as Record<string, unknown>) ?? {}
    const resolvedHotspotRecoveryQuery = resolveHotspotRecoveryRouteQuery(routeQuery, hotspotTrustConfig)
    const hasResolvedHotspotRecoveryContext = Object.keys(resolvedHotspotRecoveryQuery).length > 0
    const hotspotIdentityQuery = buildHotspotIdentityQuery({
      clientIp: resolvedHotspotRecoveryQuery.client_ip,
      clientMac: resolvedHotspotRecoveryQuery.client_mac,
    })
    const hasResolvedHotspotIdentity = Object.keys(hotspotIdentityQuery).length > 0

    // Halaman public diizinkan untuk semua role (hindari auto-redirect ke dashboard).
    if (isPublicPage) {
      // Khusus halaman captive (hotspotOnly): admin tidak boleh nyasar ke flow user
      const isHotspotOnly = Boolean((to.meta as any)?.hotspotOnly === true)
      if (isHotspotOnly && isAdmin)
        return guardedNavigate('/admin/dashboard')
      return
    }

    if (!isAdmin) {
      const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
      const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
      if ((accessStatus === 'blocked' || accessStatus === 'inactive') && statusRoute && to.path !== statusRoute)
        return guardedNavigate(statusRoute)
    }

    if (!isAdmin && isDemoUser) {
      const demoAllowedPaths = ['/beli', '/payment/status', '/payment/finish']
      const isAllowedDemoPath = demoAllowedPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
      if (!isAllowedDemoPath)
        return guardedNavigate('/beli')
    }

    const shouldRunHotspotPrecheck = !isAdmin && (
      (HOTSPOT_PRECHECK_ROUTES.has(to.path) && hasResolvedHotspotRecoveryContext && hasResolvedHotspotIdentity)
      || (to.path === '/dashboard' && hasResolvedHotspotIdentity)
    )

    if (shouldRunHotspotPrecheck) {
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
          return guardedNavigate(buildHotspotRequiredPath(resolvedHotspotRecoveryQuery, { autoStart: true }))
        }
      }
      catch {
        // Best effort. Jika endpoint status gagal, lanjut ke alur guard normal.
      }
    }

    const roleRedirect = resolveLoggedInRoleRedirect(to.path, isAdmin, isKomandan)
    if (roleRedirect)
      return guardedNavigate(roleRedirect)

    if (!isAdmin) {
      if (isCaptiveContextActive() && isRestrictedInCaptiveContext(to.path)) {
        // Sprint 17 BUG-F3: refresh TS supaya TTL 30 menit tidak silent-expire
        // saat user idle navigasi internal di dalam flow captive (mis. dari
        // /captive/terhubung ke /dashboard). Tanpa refresh, setelah 30 menit
        // flag auto-clear → user lolos restriction tanpa hand-off explicit.
        markCaptiveContextActive()
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        if (isStatusSelfServicePath(to.path, accessStatus, isKomandan))
          return
        const captiveStatusRoute = getStatusRouteForAccessStatus(accessStatus, 'captive')
        if (captiveStatusRoute && captiveStatusRoute !== to.path)
          return guardedNavigate(captiveStatusRoute)
        return guardedNavigate('/captive/terhubung')
      }

      const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
      const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
      if (statusRoute && to.path === statusRoute)
        return

      const expiredOrHabisRedirect = resolveExpiredOrHabisRedirect(to.path, accessStatus, isKomandan)
      if (expiredOrHabisRedirect)
        return guardedNavigate(expiredOrHabisRedirect)
    }

    // Aturan 2: Pengguna yang sudah login (admin/biasa) tidak boleh kembali ke halaman tamu atau root.
    // Arahkan mereka ke dashboard masing-masing.
    if (GUEST_ROUTES.includes(to.path) || to.path === '/') {
      const redirectQuery = Array.isArray(to.query.redirect) ? to.query.redirect[0] : to.query.redirect
      const redirectTarget = getSafeRedirectTarget(redirectQuery, isAdmin)
      if (redirectTarget)
        return guardedNavigate(redirectTarget)

      if (!isAdmin) {
        const accessStatus = authStore.getAccessStatusFromUser(authStore.currentUser ?? authStore.lastKnownUser)
        const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
        if (statusRoute && to.path === statusRoute)
          return
      }
      return guardedNavigate(isAdmin ? adminDashboard : userDashboard)
    }
  }
})
