import type { AccessStatus } from '~/types/accessStatus'
export type GuardContext = 'login' | 'captive'

export const LEGAL_PUBLIC_PATHS = ['/merchant-center/privacy', '/merchant-center/terms', '/privacy', '/terms']

export const STATUS_ROUTES = [
  '/policy/blocked',
  '/policy/inactive',
  '/policy/expired',
  '/policy/habis',
  '/policy/fup',
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

export const GUEST_ROUTES = ['/login', '/register', '/daftar', '/admin', '/admin/login', '/captive', '/session/consume', ...STATUS_ROUTES]

export function isLegalPublicPath(path: string): boolean {
  return LEGAL_PUBLIC_PATHS.some(item => path === item || path.startsWith(`${item}/`))
}

export function getStatusRouteForAccessStatus(status: AccessStatus, context: GuardContext): string | null {
  const slugMap: Record<AccessStatus, string> = {
    ok: '',
    blocked: 'blocked',
    inactive: 'inactive',
    expired: 'expired',
    habis: 'habis',
    fup: 'fup',
  }
  const slug = slugMap[status]
  if (!slug)
    return null
  return `/policy/${slug}`
}
