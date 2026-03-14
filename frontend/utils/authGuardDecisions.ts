import { normalizeRedirectTarget } from './authGuards'
import type { AccessStatus } from '../types/accessStatus'
import { GUEST_ROUTES, getStatusRouteForAccessStatus } from './authRoutePolicy'

function matchesPath(path: string, candidate: string): boolean {
  return path === candidate || path.startsWith(`${candidate}/`)
}

export function getQuotaRecoveryDestination(isKomandan: boolean): string {
  return isKomandan ? '/requests' : '/beli'
}

export function isStatusSelfServicePath(path: string, accessStatus: AccessStatus, isKomandan: boolean): boolean {
  const statusRoute = getStatusRouteForAccessStatus(accessStatus, 'login')
  const allowedPaths = new Set<string>()

  if (statusRoute)
    allowedPaths.add(statusRoute)

  if (accessStatus === 'expired' || accessStatus === 'habis' || accessStatus === 'fup') {
    allowedPaths.add(getQuotaRecoveryDestination(isKomandan))
    allowedPaths.add('/payment/status')
    allowedPaths.add('/payment/finish')
  }

  if (accessStatus === 'fup')
    allowedPaths.add('/dashboard')

  return Array.from(allowedPaths).some(candidate => matchesPath(path, candidate))
}

export function getSafeRedirectTarget(redirectValue: unknown, isAdmin: boolean): string | null {
  const normalized = normalizeRedirectTarget(redirectValue, '')
  if (normalized.length === 0)
    return null

  const disallowedPrefixes = ['/login', '/register', '/daftar', '/captive', '/policy', '/session/consume']
  if (disallowedPrefixes.some(prefix => normalized === prefix || normalized.startsWith(`${prefix}/`)))
    return null

  if (normalized === '/admin' || normalized === '/admin/login' || normalized.startsWith('/admin/login/'))
    return null

  if (!isAdmin && (normalized === '/admin' || normalized.startsWith('/admin/')))
    return null

  return normalized
}

export function resolveGuestProtectedRedirect(path: string, fullPath: string): string | null {
  if (GUEST_ROUTES.includes(path))
    return null

  if (path.startsWith('/admin/'))
    return '/admin'

  if (!path.startsWith('/admin'))
    return `/login?redirect=${encodeURIComponent(fullPath)}`

  return null
}

export function resolveLoggedInRoleRedirect(path: string, isAdmin: boolean, isKomandan: boolean): string | null {
  const userDashboard = '/dashboard'
  const adminDashboard = '/admin/dashboard'

  if (path.startsWith('/captive'))
    return null

  if (!isAdmin && path.startsWith('/admin'))
    return userDashboard

  if (isAdmin && !path.startsWith('/admin') && !path.startsWith('/captive') && !path.startsWith('/akun'))
    return adminDashboard

  if (!isAdmin) {
    if (isKomandan && (path === '/beli' || path.startsWith('/beli/') || path === '/riwayat' || path.startsWith('/riwayat/')))
      return '/requests'

    if (!isKomandan && (path === '/requests' || path.startsWith('/requests/')))
      return userDashboard
  }

  return null
}

export function resolveExpiredOrHabisRedirect(path: string, accessStatus: string, isKomandan: boolean): string | null {
  if (accessStatus !== 'expired' && accessStatus !== 'habis')
    return null

  if (isStatusSelfServicePath(path, accessStatus, isKomandan))
    return null

  return getQuotaRecoveryDestination(isKomandan)
}
