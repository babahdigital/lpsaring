// utils/network-config.ts
// DYNAMIC Network Configuration - No Hardcore Values

interface NetworkConfigOptions {
  proxyIPs: string[]
  privateRanges: string[]
  excludedIPs: string[]
  allowLocalhost: boolean
}

/**
 * Get network configuration from environment or runtime config
 * This allows dynamic configuration without rebuilding
 */
export function getNetworkConfiguration(): NetworkConfigOptions {
  // Default configuration that works for most hotspot setups
  const defaults: NetworkConfigOptions = {
    proxyIPs: [], // Will be populated from runtime config
    privateRanges: ['10.', '172.16.', '172.17.', '172.18.', '192.168.'],
    excludedIPs: ['127.0.0.1'], // Only localhost by default
    allowLocalhost: false,
  }

  // In production, these could come from:
  // 1. Runtime config (nuxt.config.ts)
  // 2. Environment variables
  // 3. API endpoint
  // 4. localStorage settings

  if (typeof window !== 'undefined') {
    // Try to get config from window object (set by server)
    const runtimeConfig = (window as any).__NETWORK_CONFIG__
    if (runtimeConfig) {
      return { ...defaults, ...runtimeConfig }
    }

    // Try to get from localStorage (admin settings)
    try {
      const savedConfig = localStorage.getItem('network_config')
      if (savedConfig) {
        const parsed = JSON.parse(savedConfig)
        return { ...defaults, ...parsed }
      }
    }
    catch (error) {
      console.debug('Failed to parse network config from localStorage:', error)
    }
  }

  // Fallback to defaults
  return defaults
}

/**
 * Dynamic proxy IP detection
 */
export function isProxyIP(ip: string): boolean {
  if (!ip)
    return false

  const config = getNetworkConfiguration()

  // Check against configured proxy IPs
  if (config.proxyIPs.includes(ip)) {
    return true
  }

  // Auto-detect common proxy patterns (can be overridden by config)
  const commonProxyIPs = [
    '10.0.0.1', // Common laptop gateway
    '172.17.0.1', // Docker default
    '172.18.0.1', // Docker custom
  ]

  return commonProxyIPs.includes(ip)
}

/**
 * Dynamic private IP detection
 */
export function isPrivateIP(ip: string): boolean {
  if (!ip)
    return false

  const config = getNetworkConfiguration()
  const parts = ip.split('.')

  if (parts.length !== 4)
    return false

  const [a, b] = parts.map(Number)

  // Check against configured ranges
  for (const range of config.privateRanges) {
    if (ip.startsWith(range)) {
      return true
    }
  }

  // Standard private ranges (can be extended by config)
  return (
    a === 10
    || (a === 172 && b !== undefined && b >= 16 && b <= 31)
    || (a === 192 && b === 168)
    || a === 127
    || (a === 169 && b !== undefined && b === 254)
  )
}

/**
 * Dynamic client IP validation
 */
export function isValidClientIP(ip: string, context: 'captive' | 'web' | 'testing' = 'captive'): boolean {
  if (!ip || typeof ip !== 'string')
    return false

  // Basic IP format validation
  const ipRegex = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/
  if (!ipRegex.test(ip))
    return false

  const parts = ip.split('.').map(Number)
  if (parts.some(part => part < 0 || part > 255))
    return false

  const config = getNetworkConfiguration()

  // Check excluded IPs
  if (config.excludedIPs.includes(ip)) {
    console.debug('[NETWORK] IP excluded by config:', ip)
    return false
  }

  // Check proxy IPs (never valid as client IP)
  if (isProxyIP(ip)) {
    console.debug('[NETWORK] Rejecting proxy IP as client IP:', ip)
    return false
  }

  // Handle localhost based on context and config
  if (ip === '127.0.0.1') {
    return context === 'testing' && config.allowLocalhost
  }

  // All other valid IPs are acceptable as client IPs
  return true
}

/**
 * Set network configuration (for admin interface)
 */
export function setNetworkConfiguration(config: Partial<NetworkConfigOptions>): void {
  if (typeof window === 'undefined')
    return

  try {
    const currentConfig = getNetworkConfiguration()
    const newConfig = { ...currentConfig, ...config }

    localStorage.setItem('network_config', JSON.stringify(newConfig))

    // Also set on window for immediate use
    ; (window as any).__NETWORK_CONFIG__ = newConfig

    console.log('[NETWORK-CONFIG] Updated:', newConfig)
  }
  catch (error) {
    console.error('Failed to save network configuration:', error)
  }
}

/**
 * Detect current network environment and suggest configuration
 */
export function detectNetworkEnvironment(): {
  suggestedProxyIPs: string[]
  detectedGateway: string | null
  recommendations: string[]
} {
  const recommendations: string[] = []
  const suggestedProxyIPs: string[] = []
  const detectedGateway: string | null = null

  // This could be enhanced to actually detect the network
  // For now, provide sensible defaults based on common setups

  if (typeof window !== 'undefined') {
    const userAgent = navigator.userAgent

    if (/Windows/.test(userAgent)) {
      recommendations.push('Detected Windows - common proxy IP might be 10.0.0.1')
      suggestedProxyIPs.push('10.0.0.1')
    }

    if (/Mac/.test(userAgent)) {
      recommendations.push('Detected Mac - check your network preferences for gateway IP')
      suggestedProxyIPs.push('192.168.1.1', '10.0.0.1')
    }
  }

  return {
    suggestedProxyIPs,
    detectedGateway,
    recommendations,
  }
}
