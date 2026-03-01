const CAPTIVE_CONTEXT_KEY = 'captive_context_active'

const RESTRICTED_CAPTIVE_PATH_PREFIXES = ['/dashboard', '/beli', '/requests', '/akun']

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined')
    return null
  return window.sessionStorage
}

export function markCaptiveContextActive(): void {
  try {
    const storage = getSessionStorage()
    storage?.setItem(CAPTIVE_CONTEXT_KEY, '1')
  }
  catch {
    // ignore storage failures
  }
}

export function clearCaptiveContext(): void {
  try {
    const storage = getSessionStorage()
    storage?.removeItem(CAPTIVE_CONTEXT_KEY)
  }
  catch {
    // ignore storage failures
  }
}

export function isCaptiveContextActive(): boolean {
  try {
    const storage = getSessionStorage()
    return storage?.getItem(CAPTIVE_CONTEXT_KEY) === '1'
  }
  catch {
    return false
  }
}

export function isCaptiveRoutePath(path: string): boolean {
  return path === '/captive' || path.startsWith('/captive/')
}

export function isRestrictedInCaptiveContext(path: string): boolean {
  return RESTRICTED_CAPTIVE_PATH_PREFIXES.some(prefix => path === prefix || path.startsWith(`${prefix}/`))
}
