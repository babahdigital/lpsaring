import { normalizeRedirectTarget } from './authGuards'
import { GUEST_ROUTES, getStatusRouteForAccessStatus } from './authRoutePolicy'

export function getSafeRedirectTarget(redirectValue: unknown, isAdmin: boolean): string | null {
  const normalized = normalizeRedirectTarget(redirectValue, '')
  if (normalized.length === 0)
    return null

  const disallowedPrefixes = ['/login', '/register', '/daftar', '/captive', '/session/consume']
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

  const destination = isKomandan ? '/requests' : '/beli'
  const expiredRoute = getStatusRouteForAccessStatus('expired', 'login')
  const habisRoute = getStatusRouteForAccessStatus('habis', 'login')
  const allowedPaths = [destination, '/payment/status', '/payment/finish', expiredRoute, habisRoute].filter(
    (item): item is string => typeof item === 'string' && item.length > 0,
  )

  if (allowedPaths.includes(path))
    return null

  return destination
}
