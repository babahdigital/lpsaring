// utils/url-params.ts

/**
 * Decode URL parameters yang mungkin di-encode oleh MikroTik atau browser
 * Menangani multiple encoding yang sering terjadi pada MikroTik
 */
export function decodeUrlParameter(param: string | string[] | undefined): string | null {
  if (!param)
    return null

  // Handle array parameter (take first value)
  const value = Array.isArray(param) ? param[0] : param
  if (!value)
    return null

  try {
    let decoded = value
    const maxAttempts = 3 // Prevent infinite loops
    const originalValue = value

    // Iteratively decode until no more changes occur
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const newDecoded = decodeURIComponent(decoded)

        // If no change occurred, we're done
        if (newDecoded === decoded) {
          break
        }

        decoded = newDecoded
        console.log(`[URL-DECODE] Attempt ${attempt + 1}:`, {
          original: originalValue,
          current: decoded,
        })
      }
      catch (error) {
        console.warn(`[URL-DECODE] Decode failed at attempt ${attempt + 1}:`, error)
        break
      }
    }

    // Additional cleanup for common encoding issues
    if (decoded.includes('%3A') || decoded.includes('%3a')) {
      decoded = decoded.replace(/%3A/gi, ':')
      console.log('[URL-DECODE] Cleaned remaining encoded colons:', decoded)
    }

    // Log final result if any decoding occurred
    if (decoded !== originalValue) {
      console.log('[URL-DECODE] Final result:', {
        original: originalValue,
        decoded,
        attempts: 'multiple',
      })
    }

    return decoded
  }
  catch (error) {
    console.warn('[URL-DECODE] Failed to decode parameter:', value, error)
    return value // Return original if decode fails
  }
}

/**
 * Extract dan decode client IP and MAC dari route query
 */
export function extractClientParams(query: Record<string, any>) {
  console.log('[CLIENT-PARAMS] Raw query params:', query)

  const clientIp = decodeUrlParameter(query.client_ip || query.ip)
  const clientMac = decodeUrlParameter(query.client_mac || query.mac)

  console.log('[CLIENT-PARAMS] Extracted and decoded:', {
    ip: {
      raw: query.client_ip || query.ip,
      decoded: clientIp,
      isValid: isValidIpAddress(clientIp),
    },
    mac: {
      raw: query.client_mac || query.mac,
      decoded: clientMac,
      isValid: isValidMacAddress(clientMac),
    },
  })

  return { clientIp, clientMac }
}

/**
 * Validate MAC address format dengan normalisasi otomatis
 */
export function isValidMacAddress(mac: string | null): boolean {
  if (!mac)
    return false

  // Normalize MAC address: replace various separators with ':'
  const normalizedMac = mac.replace(/[-.]/g, ':').toUpperCase()

  // MAC address pattern: XX:XX:XX:XX:XX:XX (hex digits)
  const macPattern = /^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/
  const isValid = macPattern.test(normalizedMac)

  if (!isValid) {
    console.warn('[MAC-VALIDATION] Invalid MAC format:', {
      original: mac,
      normalized: normalizedMac,
      expected: 'XX:XX:XX:XX:XX:XX',
    })
  }
  else {
    console.log('[MAC-VALIDATION] Valid MAC:', {
      original: mac,
      normalized: normalizedMac,
    })
  }

  return isValid
}

/**
 * Validate IP address format
 */
export function isValidIpAddress(ip: string | null): boolean {
  if (!ip)
    return false

  // Basic IPv4 pattern
  const ipPattern = /^(?:\d{1,3}\.){3}\d{1,3}$/
  if (!ipPattern.test(ip))
    return false

  // Check each octet is 0-255
  const octets = ip.split('.')
  return octets.every((octet) => {
    const num = parseInt(octet, 10)
    return num >= 0 && num <= 255
  })
}
