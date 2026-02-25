export function normalizeRedirectTarget(redirectValue: unknown, fallback = '/dashboard'): string {
  if (typeof redirectValue !== 'string' || redirectValue.trim().length === 0)
    return fallback
  if (!redirectValue.startsWith('/') || redirectValue.startsWith('//'))
    return fallback
  return redirectValue
}

export function shouldBypassAuthGuard(routePath: string): boolean {
  return routePath.startsWith('/admin') || routePath.startsWith('/payment')
}
