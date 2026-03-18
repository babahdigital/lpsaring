/**
 * Session MAC Binding Utility
 *
 * Handles MAC randomization by storing first-seen MAC in sessionStorage
 * for 24 hours. Subsequent requests in same session accept new MAC if:
 * - Session binding exists AND
 * - User Agent hash matches AND
 * - Request within 24h of first binding
 *
 * Security: Session binding is temporary (same browser session only)
 * If new browser/session → Require OTP again
 */

export interface SessionMacBinding {
  mac: string
  userAgentHash: string
  timestamp: number
  expiryTime: number
}

const SESSION_MAC_BINDING_KEY = 'lpsaring:session-mac-binding'
const SESSION_BINDING_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours

/**
 * Generate hash of user agent for consistency check
 * Prevents same session token being used from different device/browser
 */
function hashUserAgent(): string {
  if (typeof window === 'undefined') return ''
  const ua = window.navigator.userAgent
  let hash = 0
  for (let i = 0; i < ua.length; i++) {
    const char = ua.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36)
}

/**
 * Store MAC binding in sessionStorage (first time connection with randomized MAC)
 */
export function storeSessionMacBinding(macAddress: string): SessionMacBinding {
  if (typeof window === 'undefined') {
    return {
      mac: macAddress,
      userAgentHash: '',
      timestamp: 0,
      expiryTime: 0,
    }
  }

  const now = Date.now()
  const binding: SessionMacBinding = {
    mac: macAddress,
    userAgentHash: hashUserAgent(),
    timestamp: now,
    expiryTime: now + SESSION_BINDING_TTL_MS,
  }

  try {
    window.sessionStorage.setItem(
      SESSION_MAC_BINDING_KEY,
      JSON.stringify(binding)
    )
  } catch (e) {
    console.warn('Failed to store session MAC binding:', e)
  }

  return binding
}

/**
 * Get stored session MAC binding if still valid
 * Returns null if:
 * - No binding stored
 * - Binding expired (> 24h)
 * - User Agent changed (security check)
 */
export function getSessionMacBinding(): SessionMacBinding | null {
  if (typeof window === 'undefined') return null

  try {
    const raw = window.sessionStorage.getItem(SESSION_MAC_BINDING_KEY)
    if (!raw) return null

    const binding = JSON.parse(raw) as SessionMacBinding
    const now = Date.now()

    // Check 1: Expiry time
    if (now > binding.expiryTime) {
      window.sessionStorage.removeItem(SESSION_MAC_BINDING_KEY)
      return null
    }

    // Check 2: User Agent consistency (security)
    const currentUserAgentHash = hashUserAgent()
    if (binding.userAgentHash !== currentUserAgentHash) {
      console.warn('Session MAC binding User Agent mismatch (security)')
      window.sessionStorage.removeItem(SESSION_MAC_BINDING_KEY)
      return null
    }

    return binding
  } catch (e) {
    console.warn('Failed to retrieve session MAC binding:', e)
    return null
  }
}

/**
 * Clear stored session MAC binding
 * Called on logout or when explicitly clearing session
 */
export function clearSessionMacBinding(): void {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.removeItem(SESSION_MAC_BINDING_KEY)
  } catch (e) {
    console.warn('Failed to clear session MAC binding:', e)
  }
}

/**
 * Generate token to send to backend for verification
 * Token includes: MAC + User Agent Hash + Timestamp
 * Backend validates: Token matches current session + TTL within 24h
 */
export function generateSessionMacToken(binding: SessionMacBinding): string {
  if (!binding) return ''

  const payload = {
    mac: binding.mac,
    uah: binding.userAgentHash, // User Agent Hash
    ts: binding.timestamp,
  }

  try {
    // Simple base64 encoding (not cryptographic, just for transport)
    return btoa(JSON.stringify(payload))
  } catch {
    return ''
  }
}

/**
 * Parse session MAC token from backend response/request
 * For debugging and verification
 */
export function parseSessionMacToken(token: string): Partial<SessionMacBinding> | null {
  if (!token) return null

  try {
    const decoded = atob(token)
    const payload = JSON.parse(decoded)
    return {
      mac: payload.mac,
      userAgentHash: payload.uah,
      timestamp: payload.ts,
    }
  } catch {
    return null
  }
}

/**
 * Check if new MAC should be accepted as same device
 * Returns: Fallback MAC if should accept, null if should reject
 */
export function getFallbackMacForSession(newMac: string, excludeExactMatch = false): string | null {
  const binding = getSessionMacBinding()
  if (!binding) return null

  // If new MAC is same as stored → No need for fallback
  if (!excludeExactMatch && binding.mac === newMac) {
    return binding.mac
  }

  // If new MAC different but session valid → Accept as same device (fallback)
  if (binding.mac !== newMac) {
    return binding.mac
  }

  return null
}
