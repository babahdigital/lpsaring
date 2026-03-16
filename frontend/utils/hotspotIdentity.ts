export interface HotspotIdentity {
  clientIp: string
  clientMac: string
}

import {
  decodeHotspotValue,
  isTrustedHotspotReferrer,
  normalizeHotspotClientMac,
  resolveHotspotTrustConfig,
  sanitizeResolvedHotspotIdentity,
  type HotspotTrustConfig,
} from './hotspotTrust'

interface HotspotIdentityRecord extends HotspotIdentity {
  at: number
}

const STORAGE_KEY = 'lpsaring:last-hotspot-identity'
const MAX_AGE_MS = 10 * 60 * 1000

function isBrowserRuntime(): boolean {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined'
}

const DEFAULT_HOTSPOT_TRUST_CONFIG = resolveHotspotTrustConfig()

function getFirstQueryValue(query: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const raw = query[key]
    const value = Array.isArray(raw) ? String(raw[0] ?? '').trim() : String(raw ?? '').trim()
    if (value.length > 0)
      return decodeHotspotValue(value)
  }
  return ''
}

function pickIdentityFromQuery(query: Record<string, unknown>): HotspotIdentity {
  return {
    clientIp: getFirstQueryValue(query, ['client_ip', 'ip', 'client-ip']),
    clientMac: normalizeHotspotClientMac(getFirstQueryValue(query, ['client_mac', 'mac', 'mac-address', 'client-mac'])),
  }
}

function clearStoredHotspotIdentity(): void {
  if (!isBrowserRuntime())
    return

  try {
    localStorage.removeItem(STORAGE_KEY)
  }
  catch {
    // ignore storage failures
  }
}

function pickIdentityFromReferrer(trustConfig: HotspotTrustConfig): HotspotIdentity {
  if (!isBrowserRuntime())
    return { clientIp: '', clientMac: '' }

  const referrer = String(window.document.referrer ?? '').trim()
  if (!referrer)
    return { clientIp: '', clientMac: '' }

  if (!isTrustedHotspotReferrer(referrer, trustConfig))
    return { clientIp: '', clientMac: '' }

  try {
    const parsed = new URL(referrer)
    const entries: Record<string, string> = {}
    for (const [key, value] of parsed.searchParams.entries())
      entries[key] = value
    return pickIdentityFromQuery(entries)
  }
  catch {
    return { clientIp: '', clientMac: '' }
  }
}

export function getHotspotIdentityFromQuery(query: Record<string, unknown>): HotspotIdentity {
  return pickIdentityFromQuery(query)
}

export function rememberHotspotIdentity(identity: Partial<HotspotIdentity>, trustConfig: HotspotTrustConfig = DEFAULT_HOTSPOT_TRUST_CONFIG): void {
  if (!isBrowserRuntime())
    return

  const rawClientIp = String(identity.clientIp ?? '').trim()
  const rawClientMac = String(identity.clientMac ?? '').trim()
  if (!rawClientIp && !rawClientMac)
    return

  const sanitized = sanitizeResolvedHotspotIdentity({
    clientIp: rawClientIp,
    clientMac: rawClientMac,
  }, trustConfig)

  if (!sanitized.clientIp && !sanitized.clientMac) {
    if (rawClientIp)
      clearStoredHotspotIdentity()
    return
  }

  try {
    const payload: HotspotIdentityRecord = {
      clientIp: sanitized.clientIp,
      clientMac: sanitized.clientMac,
      at: Date.now(),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }
  catch {
    // ignore storage failures
  }
}

export function getStoredHotspotIdentity(trustConfig: HotspotTrustConfig = DEFAULT_HOTSPOT_TRUST_CONFIG): HotspotIdentity {
  if (!isBrowserRuntime())
    return { clientIp: '', clientMac: '' }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw)
      return { clientIp: '', clientMac: '' }

    const parsed = JSON.parse(raw) as Partial<HotspotIdentityRecord>
    const at = Number(parsed?.at ?? 0)
    if (!Number.isFinite(at) || at <= 0 || (Date.now() - at) > MAX_AGE_MS) {
      clearStoredHotspotIdentity()
      return { clientIp: '', clientMac: '' }
    }

    const sanitized = sanitizeResolvedHotspotIdentity({
      clientIp: String(parsed?.clientIp ?? '').trim(),
      clientMac: String(parsed?.clientMac ?? '').trim(),
    }, trustConfig)

    if (!sanitized.clientIp && !sanitized.clientMac) {
      clearStoredHotspotIdentity()
      return { clientIp: '', clientMac: '' }
    }

    return sanitized
  }
  catch {
    return { clientIp: '', clientMac: '' }
  }
}

export function resolveHotspotIdentity(query: Record<string, unknown>, trustConfig: HotspotTrustConfig = DEFAULT_HOTSPOT_TRUST_CONFIG): HotspotIdentity {
  const fromQuery = pickIdentityFromQuery(query)
  const fromReferrer = pickIdentityFromReferrer(trustConfig)
  const fromStorage = getStoredHotspotIdentity(trustConfig)

  return sanitizeResolvedHotspotIdentity({
    clientIp: fromQuery.clientIp || fromReferrer.clientIp || fromStorage.clientIp,
    clientMac: fromQuery.clientMac || fromReferrer.clientMac || fromStorage.clientMac,
  }, trustConfig)
}
