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

export function normalizeHotspotLoginUrl(raw: string): string {
  const input = String(raw || '').trim()
  if (!input)
    return ''

  const candidate = input.startsWith('//') ? `http:${input}` : input

  try {
    const parsed = new URL(candidate)
    if (parsed.protocol === 'https:' && shouldForceHttpForHost(parsed.hostname))
      parsed.protocol = 'http:'
    if (shouldAppendLoginPath(parsed.hostname, parsed.pathname))
      parsed.pathname = '/login'
    return parsed.toString()
  }
  catch {
    const withScheme = /^https?:\/\//i.test(candidate) ? candidate : `http://${candidate.replace(/^\/+/, '')}`
    try {
      const parsed = new URL(withScheme)
      if (parsed.protocol === 'https:' && shouldForceHttpForHost(parsed.hostname))
        parsed.protocol = 'http:'
      if (shouldAppendLoginPath(parsed.hostname, parsed.pathname))
        parsed.pathname = '/login'
      return parsed.toString()
    }
    catch {
      return candidate
    }
  }
}

export function resolveHotspotBridgeTarget(mikrotikLoginUrl: string, configuredProbeUrl: string): string {
  const preferredLoginUrl = normalizeHotspotLoginUrl(mikrotikLoginUrl)
  if (preferredLoginUrl)
    return preferredLoginUrl

  const configuredProbe = normalizeHotspotLoginUrl(configuredProbeUrl)
  if (configuredProbe)
    return configuredProbe

  return 'http://neverssl.com/'
}
