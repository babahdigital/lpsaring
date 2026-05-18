const CAPTIVE_CONTEXT_KEY = 'captive_context_active'
const CAPTIVE_CONTEXT_TS_KEY = 'captive_context_active_ts'
// Sprint 9 BUG-2: TTL supaya stale flag tidak stuck user di /captive/terhubung
// kalau user refresh/close tab tanpa klik "Done". 30 menit cukup untuk flow normal,
// expire kalau idle / abandoned.
const CAPTIVE_CONTEXT_TTL_MS = 30 * 60 * 1000

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
    storage?.setItem(CAPTIVE_CONTEXT_TS_KEY, String(Date.now()))
  }
  catch {
    // ignore storage failures
  }
}

export function clearCaptiveContext(): void {
  try {
    const storage = getSessionStorage()
    storage?.removeItem(CAPTIVE_CONTEXT_KEY)
    storage?.removeItem(CAPTIVE_CONTEXT_TS_KEY)
  }
  catch {
    // ignore storage failures
  }
}

export function isCaptiveContextActive(): boolean {
  try {
    const storage = getSessionStorage()
    const raw = storage?.getItem(CAPTIVE_CONTEXT_KEY)
    if (raw !== '1')
      return false
    // Sprint 9 BUG-2: cek TTL — flag expired bila > 30 menit.
    const tsRaw = storage?.getItem(CAPTIVE_CONTEXT_TS_KEY)
    if (tsRaw) {
      const ts = Number(tsRaw)
      if (!Number.isNaN(ts) && Date.now() - ts > CAPTIVE_CONTEXT_TTL_MS) {
        clearCaptiveContext()
        return false
      }
    }
    return true
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
