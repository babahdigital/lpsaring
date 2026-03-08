export interface HotspotIdentity {
  clientIp: string
  clientMac: string
}

interface HotspotIdentityRecord extends HotspotIdentity {
  at: number
}

const STORAGE_KEY = 'lpsaring:last-hotspot-identity'
const MAX_AGE_MS = 10 * 60 * 1000

function isBrowserRuntime(): boolean {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined'
}

function decodeMaybeRepeated(raw: string): string {
  let next = String(raw ?? '').trim()
  for (let i = 0; i < 3; i++) {
    try {
      const decoded = decodeURIComponent(next)
      if (decoded === next)
        break
      next = decoded
    }
    catch {
      break
    }
  }
  return next.trim()
}

function getFirstQueryValue(query: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const raw = query[key]
    const value = Array.isArray(raw) ? String(raw[0] ?? '').trim() : String(raw ?? '').trim()
    if (value.length > 0)
      return decodeMaybeRepeated(value)
  }
  return ''
}

function normalizeClientMac(raw: string): string {
  const normalized = decodeMaybeRepeated(raw)
  if (!normalized)
    return ''
  return normalized.replace(/-/g, ':').toUpperCase()
}

function pickIdentityFromQuery(query: Record<string, unknown>): HotspotIdentity {
  return {
    clientIp: getFirstQueryValue(query, ['client_ip', 'ip', 'client-ip']),
    clientMac: normalizeClientMac(getFirstQueryValue(query, ['client_mac', 'mac', 'mac-address', 'client-mac'])),
  }
}

function pickIdentityFromReferrer(): HotspotIdentity {
  if (!isBrowserRuntime())
    return { clientIp: '', clientMac: '' }

  const referrer = String(window.document.referrer ?? '').trim()
  if (!referrer)
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

export function rememberHotspotIdentity(identity: Partial<HotspotIdentity>): void {
  if (!isBrowserRuntime())
    return

  const clientIp = String(identity.clientIp ?? '').trim()
  const clientMac = normalizeClientMac(String(identity.clientMac ?? ''))
  if (!clientIp && !clientMac)
    return

  try {
    const payload: HotspotIdentityRecord = {
      clientIp,
      clientMac,
      at: Date.now(),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }
  catch {
    // ignore storage failures
  }
}

export function getStoredHotspotIdentity(): HotspotIdentity {
  if (!isBrowserRuntime())
    return { clientIp: '', clientMac: '' }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw)
      return { clientIp: '', clientMac: '' }

    const parsed = JSON.parse(raw) as Partial<HotspotIdentityRecord>
    const at = Number(parsed?.at ?? 0)
    if (!Number.isFinite(at) || at <= 0 || (Date.now() - at) > MAX_AGE_MS)
      return { clientIp: '', clientMac: '' }

    return {
      clientIp: String(parsed?.clientIp ?? '').trim(),
      clientMac: normalizeClientMac(String(parsed?.clientMac ?? '')),
    }
  }
  catch {
    return { clientIp: '', clientMac: '' }
  }
}

export function resolveHotspotIdentity(query: Record<string, unknown>): HotspotIdentity {
  const fromQuery = pickIdentityFromQuery(query)
  if (fromQuery.clientIp && fromQuery.clientMac)
    return fromQuery

  const fromReferrer = pickIdentityFromReferrer()
  const fromStorage = getStoredHotspotIdentity()

  return {
    clientIp: fromQuery.clientIp || fromReferrer.clientIp || fromStorage.clientIp,
    clientMac: fromQuery.clientMac || fromReferrer.clientMac || fromStorage.clientMac,
  }
}
