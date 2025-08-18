// utils/network-detection.ts
// DYNAMIC Network Detection Utilities - No Hardcore Values

interface NetworkConfig {
  allowPrivateRanges: boolean
  excludeRanges: string[]
  includeRanges: string[]
}

/**
 * Dynamic IP validation based on context
 */
export function isValidIPAddress(ip: string): boolean {
  if (!ip || typeof ip !== 'string')
    return false

  // Basic IP format validation
  const ipRegex = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/
  if (!ipRegex.test(ip))
    return false

  const parts = ip.split('.').map(Number)
  return parts.every(part => part >= 0 && part <= 255)
}

/**
 * Dynamic network type detection without hardcore ranges
 */
export function detectNetworkType(ip: string): 'localhost' | 'private' | 'public' | 'invalid' {
  if (!isValidIPAddress(ip))
    return 'invalid'

  const parts = ip.split('.').map(Number)
  const [a, b] = parts

  // Only hardcore localhost (universal)
  if (a === 127)
    return 'localhost'

  // Dynamic detection - in hotspot environment, most IPs are "private" but valid
  if (
    a === 10
    || (a === 172 && b !== undefined && b >= 16 && b <= 31)
    || (a === 192 && b === 168)
    || (a === 169 && b === 254) // Link-local
  ) {
    return 'private'
  }

  return 'public'
}

/**
 * Dynamic MAC address validation
 */
export function isValidMACAddress(mac: string): boolean {
  if (!mac || typeof mac !== 'string')
    return false

  // MAC format: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
  const macRegex = /^(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}$/i
  return macRegex.test(mac)
}

/**
 * Extract client info from various sources dynamically
 */
export function extractClientInfo(sources: {
  urlParams?: Record<string, any>
  headers?: Record<string, string>
  localStorage?: Storage
  authStore?: any
}): { ip: string | null, mac: string | null, source: string } {
  const { urlParams = {}, headers = {}, localStorage, authStore } = sources

  // Priority 1: URL parameters (captive portal)
  const urlIP = urlParams.client_ip || urlParams.ip || urlParams['client-ip'] || urlParams['orig-ip']
  const urlMAC = urlParams.client_mac || urlParams.mac || urlParams['client-mac']

  if (urlIP || urlMAC) {
    return {
      ip: urlIP || null,
      mac: urlMAC || null,
      source: 'url_params',
    }
  }

  // Priority 2: Headers (frontend detection)
  const headerIP = headers['X-Frontend-Detected-IP'] || headers['X-Real-IP']
  const headerMAC = headers['X-Frontend-Detected-MAC']

  if (headerIP || headerMAC) {
    return {
      ip: headerIP || null,
      mac: headerMAC || null,
      source: 'headers',
    }
  }

  // Priority 3: localStorage (session persistence)
  if (localStorage) {
    const storedIP = localStorage.getItem('client_ip') || localStorage.getItem('mikrotik_client_ip')
    const storedMAC = localStorage.getItem('client_mac') || localStorage.getItem('mikrotik_client_mac')

    if (storedIP || storedMAC) {
      return {
        ip: storedIP,
        mac: storedMAC,
        source: 'localStorage',
      }
    }
  }

  // Priority 4: Auth store (application state)
  if (authStore?.clientIp || authStore?.clientMac) {
    return {
      ip: authStore.clientIp || null,
      mac: authStore.clientMac || null,
      source: 'auth_store',
    }
  }

  return { ip: null, mac: null, source: 'none' }
}

/**
 * Network configuration based on environment
 */
export function getNetworkConfig(): NetworkConfig {
  // In production, this could come from runtime config or env variables
  // For now, use sensible defaults for hotspot portal
  return {
    allowPrivateRanges: true, // Hotspot typically uses private ranges
    excludeRanges: ['127.0.0.1'], // Only exclude localhost
    includeRanges: [], // Empty means include all (except excluded)
  }
}

/**
 * Dynamic device info detection without hardcore values
 */
export function detectDeviceInfo(userAgent?: string): {
  deviceType: string
  deviceName: string
  browser: string
} {
  const ua = userAgent || (typeof navigator !== 'undefined' ? navigator.userAgent : '')

  let deviceType = 'Unknown Device'
  let deviceName = 'Unknown'
  let browser = 'Unknown Browser'

  if (ua) {
    // Device type detection
    if (/Mobile|Android|iPhone|iPad/.test(ua)) {
      deviceType = 'Mobile Device'
      if (/iPhone/.test(ua))
        deviceName = 'iPhone'
      else if (/iPad/.test(ua))
        deviceName = 'iPad'
      else if (/Android/.test(ua))
        deviceName = 'Android Device'
    }
    else if (/Windows/.test(ua)) {
      deviceType = 'Windows PC'
      deviceName = 'Windows Computer'
    }
    else if (/Mac/.test(ua)) {
      deviceType = 'Mac'
      deviceName = 'Mac Computer'
    }
    else {
      deviceType = 'Computer'
      deviceName = 'Desktop/Laptop'
    }

    // Browser detection
    if (/Chrome/.test(ua))
      browser = 'Chrome'
    else if (/Firefox/.test(ua))
      browser = 'Firefox'
    else if (/Safari/.test(ua))
      browser = 'Safari'
    else if (/Edge/.test(ua))
      browser = 'Edge'
  }

  return { deviceType, deviceName, browser }
}
