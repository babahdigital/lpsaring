export interface HotspotTrustConfig {
  allowedClientCidrs: string[]
  trustedLoginHosts: string[]
}

interface HotspotTrustConfigInput {
  hotspotAllowedClientCidrs?: unknown
  hotspotTrustedLoginHosts?: unknown
  trustedLoginUrls?: unknown[]
}

interface ParsedCidr {
  network: number
  mask: number
}

const DEFAULT_ALLOWED_CLIENT_CIDRS = ['172.16.2.0/23']
const DEFAULT_TRUSTED_LOGIN_HOSTS = ['login.home.arpa']

export function decodeHotspotValue(raw: string): string {
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

function normalizeHotspotHost(raw: string): string {
  return String(raw ?? '').trim().toLowerCase()
}

function uniqueValues(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.map(value => String(value ?? '').trim()).filter(Boolean)))
}

function parseDelimitedValues(raw: unknown): string[] {
  if (Array.isArray(raw))
    return uniqueValues(raw.map(value => String(value ?? '').trim()))

  const text = String(raw ?? '').trim()
  if (!text)
    return []

  if (text.startsWith('[') && text.endsWith(']')) {
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed))
        return uniqueValues(parsed.map(value => String(value ?? '').trim()))
    }
    catch {
      // ignore invalid JSON, fall back to CSV parsing
    }
  }

  return uniqueValues(text.split(',').map(value => value.trim()))
}

function parseUrlLike(raw: string): URL | null {
  const normalized = decodeHotspotValue(raw)
  if (!normalized)
    return null

  const candidate = normalized.startsWith('//') ? `http:${normalized}` : normalized
  try {
    return new URL(candidate)
  }
  catch {
    const withScheme = /^https?:\/\//i.test(candidate)
      ? candidate
      : `http://${candidate.replace(/^\/+/, '')}`

    try {
      return new URL(withScheme)
    }
    catch {
      return null
    }
  }
}

function extractTrustedHostFromUrl(raw: unknown): string {
  const parsed = parseUrlLike(String(raw ?? ''))
  return parsed ? normalizeHotspotHost(parsed.hostname) : ''
}

function parseIpv4(raw: string): number | null {
  const text = String(raw ?? '').trim()
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(text))
    return null

  const octets = text.split('.').map(part => Number.parseInt(part, 10))
  if (octets.some(octet => !Number.isInteger(octet) || octet < 0 || octet > 255))
    return null

  return (((octets[0] << 24) >>> 0)
    | ((octets[1] << 16) >>> 0)
    | ((octets[2] << 8) >>> 0)
    | (octets[3] >>> 0)) >>> 0
}

function parseCidr(raw: string): ParsedCidr | null {
  const [ipText, prefixText] = String(raw ?? '').trim().split('/')
  const ip = parseIpv4(ipText)
  const prefix = Number.parseInt(prefixText ?? '', 10)
  if (ip == null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32)
    return null

  const mask = prefix === 0 ? 0 : ((0xFFFFFFFF << (32 - prefix)) >>> 0)
  return {
    network: ip & mask,
    mask,
  }
}

function isIpv4InCidr(ip: number, cidr: ParsedCidr): boolean {
  return (ip & cidr.mask) === cidr.network
}

function getFirstQueryValue(query: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const raw = query[key]
    const value = Array.isArray(raw) ? String(raw[0] ?? '').trim() : String(raw ?? '').trim()
    if (value.length > 0)
      return decodeHotspotValue(value)
  }
  return ''
}

export function normalizeHotspotClientMac(raw: string): string {
  const normalized = decodeHotspotValue(raw)
  if (!normalized)
    return ''
  return normalized.replace(/-/g, ':').toUpperCase()
}

export function resolveHotspotTrustConfig(input: HotspotTrustConfigInput = {}): HotspotTrustConfig {
  const allowedClientCidrs = uniqueValues([
    ...DEFAULT_ALLOWED_CLIENT_CIDRS,
    ...parseDelimitedValues(input.hotspotAllowedClientCidrs),
  ])

  const trustedLoginHosts = uniqueValues([
    ...DEFAULT_TRUSTED_LOGIN_HOSTS,
    ...parseDelimitedValues(input.hotspotTrustedLoginHosts).map(normalizeHotspotHost),
    ...(input.trustedLoginUrls ?? []).map(extractTrustedHostFromUrl),
  ])

  return {
    allowedClientCidrs,
    trustedLoginHosts,
  }
}

export function isTrustedHotspotClientIp(raw: string, trustConfig: HotspotTrustConfig): boolean {
  const ip = parseIpv4(String(raw ?? '').trim())
  if (ip == null)
    return false

  return trustConfig.allowedClientCidrs
    .map(parseCidr)
    .filter((value): value is ParsedCidr => value != null)
    .some(cidr => isIpv4InCidr(ip, cidr))
}

export function sanitizeResolvedHotspotIdentity(
  identity: { clientIp?: string | null, clientMac?: string | null },
  trustConfig: HotspotTrustConfig,
): { clientIp: string, clientMac: string } {
  const clientIp = decodeHotspotValue(String(identity.clientIp ?? ''))
  const clientMac = normalizeHotspotClientMac(String(identity.clientMac ?? ''))

  if (!clientIp || !isTrustedHotspotClientIp(clientIp, trustConfig)) {
    return {
      clientIp: '',
      clientMac: '',
    }
  }

  return {
    clientIp,
    clientMac,
  }
}

export function sanitizeHotspotLoginHint(raw: string, trustConfig: HotspotTrustConfig): string {
  const parsed = parseUrlLike(raw)
  if (!parsed)
    return ''

  const hostname = normalizeHotspotHost(parsed.hostname)
  if (!trustConfig.trustedLoginHosts.includes(hostname))
    return ''

  return parsed.toString()
}

export function extractHotspotLoginHintFromQuery(query: Record<string, unknown>): string {
  const direct = getFirstQueryValue(query, ['link_login_only', 'link-login-only', 'link_login', 'link-login', 'linkloginonly'])
  if (direct.length > 0)
    return direct

  const redirectRaw = getFirstQueryValue(query, ['redirect'])
  if (!redirectRaw)
    return ''

  const decodedRedirect = decodeHotspotValue(redirectRaw)
  if (!decodedRedirect.includes('link_login_only='))
    return ''

  try {
    const parsed = new URL(decodedRedirect, 'https://example.invalid')
    return decodeHotspotValue(String(parsed.searchParams.get('link_login_only') ?? '').trim())
  }
  catch {
    const marker = 'link_login_only='
    const markerIndex = decodedRedirect.indexOf(marker)
    if (markerIndex < 0)
      return ''
    const after = decodedRedirect.slice(markerIndex + marker.length)
    const ampIndex = after.indexOf('&')
    return decodeHotspotValue((ampIndex >= 0 ? after.slice(0, ampIndex) : after).trim())
  }
}

export function extractTrustedHotspotLoginHintFromQuery(query: Record<string, unknown>, trustConfig: HotspotTrustConfig): string {
  return sanitizeHotspotLoginHint(extractHotspotLoginHintFromQuery(query), trustConfig)
}

export function isTrustedHotspotReferrer(referrer: string, trustConfig: HotspotTrustConfig): boolean {
  const parsed = parseUrlLike(referrer)
  if (!parsed)
    return false

  const hostname = normalizeHotspotHost(parsed.hostname)
  if (trustConfig.trustedLoginHosts.includes(hostname))
    return true

  if (typeof window === 'undefined' || typeof window.location === 'undefined')
    return false

  return hostname === normalizeHotspotHost(window.location.hostname)
}