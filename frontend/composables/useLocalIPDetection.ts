// composables/useLocalIPDetection.ts
import { computed, readonly, ref } from 'vue'

// Types
export interface LocalIPResult {
  ip: string | null
  method: string
  confidence: number
  timestamp?: number
}

// Constants
const CACHE_KEY = 'detected_local_ip'
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

export function useLocalIPDetection() {
  // State
  const detectedIP = ref<string | null>(null)
  const detectionMethod = ref<string>('none')
  const confidence = ref(0)
  const isDetecting = ref(false)
  const error = ref<string | null>(null)

  // Helper: Check if IP is private/local
  const isPrivateIP = (ip: string): boolean => {
    return (
      ip.startsWith('192.168.')
      || ip.startsWith('10.')
      || ip.startsWith('172.16.')
      || ip.startsWith('172.17.')
      || ip.startsWith('172.18.')
      || ip.startsWith('172.19.')
      || ip.startsWith('172.20.')
      || ip.startsWith('172.21.')
      || ip.startsWith('172.22.')
      || ip.startsWith('172.23.')
      || ip.startsWith('172.24.')
      || ip.startsWith('172.25.')
      || ip.startsWith('172.26.')
      || ip.startsWith('172.27.')
      || ip.startsWith('172.28.')
      || ip.startsWith('172.29.')
      || ip.startsWith('172.30.')
      || ip.startsWith('172.31.')
    )
  }

  // Computed
  const isLocalNetwork = computed(() => {
    if (!detectedIP.value)
      return false
    return isPrivateIP(detectedIP.value)
  })

  // Helper: Validate IP format
  const isValidIP = (ip: string): boolean => {
    const ipRegex = /^(?:(?:25[0-5]|2[0-4]\d|[01]?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d{1,2})$/
    return ipRegex.test(ip)
  }

  // Cache Management
  const getFromCache = (): LocalIPResult | null => {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (!cached)
        return null

      const parsed = JSON.parse(cached)
      const age = Date.now() - (parsed.timestamp || 0)

      if (age < CACHE_TTL) {
        return {
          ...parsed,
          method: `${parsed.method}-cached`,
          confidence: Math.max(0, parsed.confidence - 0.1),
        }
      }
    }
    catch (err) {
      console.warn('Cache read error:', err)
    }
    return null
  }

  const saveToCache = (result: LocalIPResult): void => {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(result))
    }
    catch (err) {
      console.warn('Cache save error:', err)
    }
  }

  const clearCache = (): void => {
    try {
      localStorage.removeItem(CACHE_KEY)
    }
    catch (err) {
      console.warn('Cache clear error:', err)
    }
  }

  // Detection Method 1: WebRTC
  const detectViaWebRTC = (): Promise<LocalIPResult> => {
    return new Promise((resolve) => {
      if (typeof window === 'undefined') {
        resolve({ ip: null, method: 'webrtc', confidence: 0 })
        return
      }

      try {
        const RTCPeerConnection = window.RTCPeerConnection
          || (window as any).webkitRTCPeerConnection
          || (window as any).mozRTCPeerConnection

        if (!RTCPeerConnection) {
          resolve({ ip: null, method: 'webrtc', confidence: 0 })
          return
        }

        const pc = new RTCPeerConnection({
          iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
        })

        let foundIP = false
        const timeout = setTimeout(() => {
          if (!foundIP) {
            pc.close()
            resolve({ ip: null, method: 'webrtc', confidence: 0 })
          }
        }, 3000)

        pc.onicecandidate = (event) => {
          if (!event.candidate || foundIP)
            return

          const candidate = event.candidate.candidate
          const ipMatch = candidate.match(/(\d+\.\d+\.\d+\.\d+)/)

          if (ipMatch && ipMatch[1]) {
            const ip = ipMatch[1]

            // Only accept private IPs for local network detection
            if (isPrivateIP(ip) && isValidIP(ip)) {
              foundIP = true
              clearTimeout(timeout)
              pc.close()
              resolve({
                ip,
                method: 'webrtc',
                confidence: 0.95,
                timestamp: Date.now(),
              })
            }
          }
        }

        pc.createDataChannel('test')
        pc.createOffer()
          .then(offer => pc.setLocalDescription(offer))
          .catch(() => {
            clearTimeout(timeout)
            pc.close()
            resolve({ ip: null, method: 'webrtc', confidence: 0 })
          })
      }
      catch (err) {
        console.error('WebRTC error:', err)
        resolve({ ip: null, method: 'webrtc', confidence: 0 })
      }
    })
  }

  // Detection Method 2: Backend API
  const detectViaBackend = async (): Promise<LocalIPResult> => {
    try {
      const { $api } = useNuxtApp()
      // Call the backend API for client detection
      const data = await $api('/auth/detect-client-info', {
        headers: {
          'X-Frontend-Request': '1',
        },
      })

      if (data.status === 'SUCCESS' && data.summary?.detected_ip) {
        return {
          ip: data.summary.detected_ip,
          method: 'backend-api',
          confidence: 0.8,
          timestamp: Date.now(),
        }
      }

      return { ip: null, method: 'backend-api', confidence: 0 }
    }
    catch (err) {
      console.warn('Backend detection failed:', err)
      return { ip: null, method: 'backend-api', confidence: 0 }
    }
  }

  // Detection Method 3: External API Services
  const detectViaExternalAPI = async (): Promise<LocalIPResult> => {
    const services = [
      { url: 'https://api.ipify.org?format=json', key: 'ip' },
      { url: 'https://api.myip.com', key: 'ip' },
    ]

    for (const service of services) {
      try {
        const response = await fetch(service.url)
        if (response.ok) {
          const data = await response.json()
          const ip = data[service.key]

          if (ip && isValidIP(ip)) {
            return {
              ip,
              method: 'external-api',
              confidence: 0.6,
              timestamp: Date.now(),
            }
          }
        }
      }
      catch {
        // Try next service
      }
    }

    return { ip: null, method: 'external-api', confidence: 0 }
  }

  // Main Detection Function
  const detectLocalIP = async (): Promise<LocalIPResult | null> => {
    if (isDetecting.value) {
      console.log('Detection already in progress')
      return null
    }

    isDetecting.value = true
    error.value = null

    try {
      // Check cache first
      const cached = getFromCache()
      if (cached && cached.ip) {
        detectedIP.value = cached.ip
        detectionMethod.value = cached.method
        confidence.value = cached.confidence
        console.log('📦 Using cached IP:', cached)
        return cached
      }

      console.log('🔍 Starting IP detection...')

      // Try detection methods in parallel
      const results = await Promise.allSettled([
        detectViaWebRTC(),
        detectViaBackend(),
        detectViaExternalAPI(),
      ])

      // Filter successful results with valid IPs
      const validResults: LocalIPResult[] = []
      results.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value.ip) {
          console.log(`✅ Method ${index} succeeded:`, result.value)
          validResults.push(result.value)
        }
      })

      if (validResults.length === 0) {
        console.warn('⚠️ No IP detected')
        detectedIP.value = null
        detectionMethod.value = 'none'
        confidence.value = 0
        return null
      }

      // Select best result (highest confidence)
      const bestResult = validResults.reduce((best, current) => {
        // Prefer local IPs detected via WebRTC
        if (current.method === 'webrtc' && isPrivateIP(current.ip!)) {
          return current
        }
        return current.confidence > best.confidence ? current : best
      })

      // Update state
      detectedIP.value = bestResult.ip
      detectionMethod.value = bestResult.method
      confidence.value = bestResult.confidence

      // Save to cache
      saveToCache(bestResult)

      console.log('🎯 Best detection result:', bestResult)
      return bestResult
    }
    catch (err) {
      console.error('❌ Detection error:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      detectedIP.value = null
      detectionMethod.value = 'error'
      confidence.value = 0
      return null
    }
    finally {
      isDetecting.value = false
    }
  }

  // Refresh detection (clear cache and re-detect)
  const refreshDetection = async (): Promise<LocalIPResult | null> => {
    clearCache()
    detectedIP.value = null
    detectionMethod.value = 'none'
    confidence.value = 0
    return await detectLocalIP()
  }

  return {
    // State
    detectedIP: readonly(detectedIP),
    detectionMethod: readonly(detectionMethod),
    confidence: readonly(confidence),
    isDetecting: readonly(isDetecting),
    error: readonly(error),
    isLocalNetwork,

    // Methods
    detectLocalIP,
    refreshDetection,

    // Cache utilities
    getFromCache,
    saveToCache,
    clearCache,
  }
}
