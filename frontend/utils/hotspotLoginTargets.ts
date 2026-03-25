function shouldForceHttpForHost(hostname: string): boolean {
  const host = String(hostname || '').trim().toLowerCase()
  if (!host)
    return false

  if (host === 'localhost' || host.endsWith('.local') || host.endsWith('.home.arpa'))
    return true

  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    const octets = host.split('.').map(n => Number.parseInt(n, 10))
    if (octets.length === 4) {
      const [a, b] = octets
      if (a === 10)
        return true
      if (a === 172 && b >= 16 && b <= 31)
        return true
      if (a === 192 && b === 168)
        return true
      if (a === 169 && b === 254)
        return true
    }
  }

  return false
}

function shouldAppendLoginPath(hostname: string, pathname: string): boolean {
  if (!shouldForceHttpForHost(hostname))
    return false

  const normalizedPath = String(pathname || '').trim()
  return normalizedPath === '' || normalizedPath === '/'
}

function isLocalHotspotTarget(raw: string): boolean {
  const normalized = normalizeHotspotBridgeUrl(raw)
  if (!normalized)
    return false

  try {
    return shouldForceHttpForHost(new URL(normalized).hostname)
  }
  catch {
    return false
  }
}

function normalizeHotspotUrl(
  raw: string,
  options: { appendLoginPathForRoot: boolean, preferPortalRoot: boolean },
): string {
  const input = String(raw || '').trim()
  if (!input)
    return ''

  const candidate = input.startsWith('//') ? `http:${input}` : input

  const normalizeParsedTarget = (parsed: URL): string => {
    if (parsed.protocol === 'https:' && shouldForceHttpForHost(parsed.hostname))
      parsed.protocol = 'http:'

    if (options.preferPortalRoot && shouldForceHttpForHost(parsed.hostname) && parsed.pathname === '/login')
      parsed.pathname = '/'

    if (options.appendLoginPathForRoot && shouldAppendLoginPath(parsed.hostname, parsed.pathname))
      parsed.pathname = '/login'

    return parsed.toString()
  }

  try {
    const parsed = new URL(candidate)
    return normalizeParsedTarget(parsed)
  }
  catch {
    const withScheme = /^https?:\/\//i.test(candidate) ? candidate : `http://${candidate.replace(/^\/+/, '')}`
    try {
      const parsed = new URL(withScheme)
      return normalizeParsedTarget(parsed)
    }
    catch {
      return candidate
    }
  }
}

export function normalizeHotspotLoginUrl(raw: string): string {
  return normalizeHotspotUrl(raw, {
    appendLoginPathForRoot: true,
    preferPortalRoot: false,
  })
}

export function normalizeHotspotBridgeUrl(raw: string): string {
  return normalizeHotspotUrl(raw, {
    appendLoginPathForRoot: false,
    preferPortalRoot: true,
  })
}

export function resolveHotspotBridgeTarget(mikrotikLoginUrl: string, configuredProbeUrl: string): string {
  const preferredLoginUrl = normalizeHotspotBridgeUrl(mikrotikLoginUrl)
  const configuredProbe = normalizeHotspotBridgeUrl(configuredProbeUrl)

  // Always prefer the MikroTik login URL directly — it is the most reliable bridge target.
  // MikroTik will either intercept (if hotspot not active) and redirect with client_ip/mac params,
  // or serve its own page (if active) which is harmless and stays on the local network.
  // Using neverssl.com as bridge is problematic: if hotspot IS active, MikroTik won't intercept
  // and the user ends up stuck on neverssl.com with no way back.
  if (preferredLoginUrl)
    return preferredLoginUrl

  if (configuredProbe)
    return configuredProbe

  return 'http://neverssl.com/'
}
