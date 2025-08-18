import { computed, getCurrentInstance, onMounted, ref } from 'vue'

import { useAuthStore } from '~/store/auth'
import { extractClientParams } from '~/utils/url-params'

// Import ClientInfo from its source - do not re-export
import type { ClientInfo } from './useClientGlobalState'
import type { LocalIPResult } from './useLocalIPDetection'

import { useClientDetectionSingleton } from './useClientDetectionSingleton'
import { useClientGlobalState } from './useClientGlobalState'
import { useLocalIPDetection } from './useLocalIPDetection'

// Constants
const DETECTION_COOLDOWN = 30000 // Increased to 30 seconds to avoid rate limiting
const MAC_DETECTION_COOLDOWN = 15000 // 15 seconds cooldown for MAC detection
const CLIENT_SIDE_CACHE_TTL = 60000 // 1 minute cache in client side
const _RETRY_DELAY_BASE = 2000 // Base delay for exponential backoff
const _MAX_RETRY_DELAY = 10000 // Maximum delay between retries

// Types
interface DetectionSummary {
  detected_ip: string | null
  detected_mac: string | null
  ip_detected: boolean
  mac_detected: boolean
  access_mode?: string
  user_guidance?: string | null
}

interface DetectionResponse {
  status: string
  summary?: DetectionSummary
  mikrotik_lookup?: {
    success: boolean
    found_mac: string | null
    message: string
  } | null
}

interface DetectionResult {
  summary: DetectionSummary
  detection_sources?: {
    url_params?: any
    local_ip?: any
    backend_result?: DetectionResponse
  }
  status: string
}
export type { DetectionResult }

export function useClientDetection() {
  // Nuxt composables
  const { $api } = useNuxtApp()
  const route = useRoute()
  const authStore = useAuthStore()

  // Use global state
  const globalState = useClientGlobalState()

  // Use detection singleton
  const singleton = useClientDetectionSingleton()

  // Local state (just for this component instance)
  const isLoading = ref(false)
  const lastDetectionTime = ref<number>(0)
  const detectionResult = ref<DetectionResult | null>(null)
  const error = ref<string | null>(null)

  // Use the local IP detection composable
  const { detectLocalIP, clearCache: clearLocalIPCache } = useLocalIPDetection()

  // --- Computed Properties ---
  const clientInfo = computed<ClientInfo>(() => {
    // Prioritize data from global state
    if (globalState.clientInfo.value.isDetected) {
      return globalState.clientInfo.value
    }

    // Fallback to local state
    const summary = detectionResult.value?.summary
    return {
      ip: summary?.detected_ip || null,
      mac: summary?.detected_mac || null,
      isDetected: !!(summary?.detected_ip || summary?.detected_mac),
      detectionMethod: summary?.access_mode || 'unknown',
    }
  })

  const isClientInCaptivePortal = computed(() => {
    const urlParams = extractClientParams(route.query)
    return !!(urlParams.clientIp || urlParams.clientMac) || detectionResult.value?.summary?.access_mode === 'captive'
  })

  const needsManualDetection = computed(() => {
    return !clientInfo.value.isDetected && !isLoading.value && !globalState.isLoading.value
  })

  // --- Core Detection Logic ---

  const callBackendWithRetry = async (headers: Record<string, string>, maxRetries: number = 2): Promise<DetectionResponse> => {
    // Jika forced refresh, skip cache
    if (!headers['force-refresh']) {
      // Client-side cache untuk mengurangi request berulang
      const cacheKey = `client_detection_${JSON.stringify(headers)}`
      const cachedData = localStorage.getItem(cacheKey)

      if (cachedData) {
        try {
          const parsed = JSON.parse(cachedData)
          const now = Date.now()
          // Gunakan cache hanya jika masih fresh DAN MAC sudah terdeteksi
          // PERBAIKAN: Jangan gunakan cache jika MAC belum terdeteksi!
          if (now - parsed.timestamp < CLIENT_SIDE_CACHE_TTL
            && parsed.data?.summary?.mac_detected) {
            console.log('🚀 [CLIENT-CACHE] Using cached detection result with MAC')
            return parsed.data
          }
          else if (now - parsed.timestamp < CLIENT_SIDE_CACHE_TTL) {
            console.log('⚠️ [CLIENT-CACHE] Cached result exists but MAC not detected, skipping cache')
          }
        }
        catch (e) {
          // Invalid cache, continue to API call
          console.warn('⚠️ [CLIENT-CACHE] Invalid cache:', e)
        }
      }
    }
    else {
      console.log('🚀 [CLIENT-CACHE] Forced refresh, skipping cache')
    }

    const cacheBust = `_t=${Date.now()}`
    const endpoint = `/auth/detect-client-info?${cacheBust}`

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        console.log(`🌐 [CLIENT-DETECT] API call attempt ${attempt + 1}/${maxRetries + 1} with headers:`, headers)
        const result = await $api<DetectionResponse>(endpoint, { headers })

        // PERBAIKAN: Jika MAC tidak terdeteksi, dan ini bukan attempt terakhir, coba lagi dengan delay
        // Ini memungkinkan backend untuk memperbarui ARP table dengan ping
        if (!result.summary?.mac_detected && attempt < maxRetries) {
          const delay = 1000 // 1 detik delay untuk retry
          console.log(`⚠️ [CLIENT-DETECT] MAC tidak terdeteksi pada attempt ${attempt + 1}, retry dalam ${delay}ms...`)
          await new Promise(resolve => setTimeout(resolve, delay))

          // Pastikan refresh pada attempt berikutnya
          headers['force-refresh'] = 'true'
          continue
        }

        // Cache hasil hanya jika berhasil dan MAC terdeteksi
        if (result.summary?.mac_detected || attempt >= maxRetries) {
          try {
            const cacheKey = `client_detection_${JSON.stringify(headers)}`
            localStorage.setItem(cacheKey, JSON.stringify({
              data: result,
              timestamp: Date.now(),
            }))
            console.log(`💾 [CLIENT-CACHE] Saved detection result to cache (MAC detected: ${!!result.summary?.mac_detected})`)
          }
          catch (e) {
            // localStorage full, ignore
            console.warn('⚠️ [CLIENT-CACHE] Failed to save to cache:', e)
          }
        }

        return result
      }
      catch (error: any) {
        if (error?.response?.status === 429 && attempt < maxRetries) {
          const delay = Math.min(1000 * 2 ** attempt, 5000)
          console.warn(`⏱️ Rate limited (429), mencoba lagi dalam ${delay}ms...`)
          await new Promise(resolve => setTimeout(resolve, delay))
          continue
        }

        if (attempt < maxRetries) {
          const delay = Math.min(1000 * 2 ** attempt, 3000)
          console.warn(`⚠️ API error, mencoba lagi dalam ${delay}ms...`, error)
          await new Promise(resolve => setTimeout(resolve, delay))
          continue
        }

        throw error
      }
    }
    throw new Error('Semua percobaan ulang gagal')
  }

  const clearAllCache = async () => {
    console.log('🧹 Clearing all IP/MAC cache...')

    // Get current detected information
    const currentLocalIP = await detectLocalIP()
    const currentIP = currentLocalIP?.ip || null
    console.log(`Current detected IP: ${currentIP || 'none'}`)

    try {
      // Clear backend cache via API with detected IP information
      const { $api } = useNuxtApp()
      const result = await $api('/auth/clear-cache', {
        method: 'POST',
        body: {
          ip: currentIP,
          force_refresh: true,
        },
      })
      console.log('✅ Backend cache cleared', result)

      // Check if backend detected MAC address
      if (result.fresh_detection?.detected_mac) {
        console.log(`✅ Backend found MAC: ${result.fresh_detection.detected_mac} via ${result.fresh_detection.lookup_method}`)
      }
    }
    catch (error) {
      console.warn('⚠️ Failed to clear backend cache:', error)
    }

    // Clear frontend cache
    authStore.clearClientInfo()
    clearLocalIPCache()
    singleton.clearGlobalState()
    detectionResult.value = null

    // Clear localStorage cache more thoroughly
    try {
      // Clear all detection related keys
      const keys = Object.keys(localStorage)
      keys.forEach((key) => {
        if (key.includes('detection')
          || key.includes('client')
          || key.includes('ip')
          || key.includes('mac')
          || key.includes('cache')) {
          localStorage.removeItem(key)
          console.log(`🧹 Cleared cache: ${key}`)
        }
      })
      console.log('✅ Frontend cache cleared')
    }
    catch (e) {
      console.warn('⚠️ LocalStorage cache clear failed:', e)
    }
  }

  const performDetection = async (forceRefresh: boolean): Promise<DetectionResult | null> => {
    isLoading.value = true
    singleton.setGlobalLoading(true)
    lastDetectionTime.value = Date.now()
    error.value = null

    if (forceRefresh) {
      console.log('🧹🚀 Force refresh: Membersihkan semua cache IP/MAC...')
      await clearAllCache()
    }

    try {
      const urlParams = extractClientParams(route.query)
      let localIpResult: LocalIPResult | null = null
      try {
        localIpResult = await detectLocalIP()
        if (localIpResult?.ip) {
          console.log(`✅ IP lokal terdeteksi: ${localIpResult.ip} via ${localIpResult.method}`)
        }
      }
      catch (err) {
        console.warn('⚠️ Deteksi IP lokal gagal:', err)
      }

      const ipToSend = urlParams.clientIp || localIpResult?.ip || null
      let macToSend = urlParams.clientMac || null

      if (macToSend) {
        try {
          let decodedMac = macToSend
          for (let attempt = 0; attempt < 3; attempt++) {
            const newDecoded = decodeURIComponent(decodedMac)
            if (newDecoded === decodedMac)
              break
            decodedMac = newDecoded
          }
          decodedMac = decodedMac.replace(/%3A/gi, ':').replace(/[-.]/g, ':').toUpperCase()
          macToSend = decodedMac
        }
        catch (e) {
          console.warn('⚠️ Gagal decode MAC:', e)
        }
      }

      const headers: Record<string, string> = {}
      if (ipToSend)
        headers['X-Frontend-Detected-IP'] = ipToSend
      if (macToSend)
        headers['X-Frontend-Detected-MAC'] = macToSend
      if (forceRefresh)
        headers['force-refresh'] = 'true'

      authStore.setClientInfo(ipToSend, macToSend)

      const data = await callBackendWithRetry(headers)

      const result: DetectionResult = {
        summary: {
          detected_ip: data.summary?.detected_ip || ipToSend || null,
          detected_mac: data.summary?.detected_mac || macToSend || null,
          ip_detected: !!(data.summary?.detected_ip || ipToSend),
          mac_detected: !!(data.summary?.detected_mac || macToSend),
          access_mode: data.summary?.access_mode || (urlParams.clientIp || urlParams.clientMac ? 'captive' : 'web'),
          user_guidance: data.summary?.user_guidance || null,
        },
        detection_sources: { url_params: urlParams, local_ip: localIpResult || undefined, backend_result: data },
        status: data.status || 'SUCCESS',
      }

      singleton.setGlobalDetectionResult(result)
      detectionResult.value = result
      authStore.setClientInfo(result.summary.detected_ip, result.summary.detected_mac)

      return result
    }
    catch (err) {
      console.error('❌ Deteksi klien gagal:', err)
      const errorMessage = err instanceof Error ? err.message : 'Deteksi gagal'
      singleton.setGlobalError(errorMessage)
      error.value = errorMessage
      throw err
    }
    finally {
      singleton.setGlobalLoading(false)
      singleton.setGlobalDetectionPromise(null)
      isLoading.value = false
    }
  }

  const detectClientInfo = async (forceRefresh: boolean = false): Promise<DetectionResult | null> => {
    // Cek apakah MAC telah terdeteksi dari hasil sebelumnya
    const macAlreadyDetected = !!singleton.detectionResult.value?.summary?.detected_mac
      || !!detectionResult.value?.summary?.detected_mac

    if (!forceRefresh && !singleton.shouldDetect(forceRefresh)) {
      // Jika tidak force refresh, tidak perlu detect, DAN MAC sudah ada - gunakan cache
      if (macAlreadyDetected) {
        console.log('🔄 Menggunakan data deteksi dari cache singleton (MAC terdeteksi).')
        return singleton.detectionResult.value
      }
      else {
        console.log('⚠️ MAC belum terdeteksi di cache singleton, lanjutkan deteksi.')
      }
    }

    // Track global request count even if we're using an existing promise
    singleton.trackApiRequest()

    const existingPromise = singleton.getGlobalDetectionPromise()
    if (existingPromise && !forceRefresh) {
      console.log('🔄 Menggunakan promise deteksi yang sudah ada dari singleton.')
      return await existingPromise
    }

    if (isLoading.value && !forceRefresh) {
      console.log('🛡️ Deteksi klien sedang berjalan di instance ini, lewati.')
      return detectionResult.value
    }

    const now = Date.now()

    // PERBAIKAN: Gunakan cooldown yang berbeda tergantung pada status deteksi MAC
    // Jika MAC belum terdeteksi, gunakan cooldown yang lebih agresif
    const effectiveCooldown = macAlreadyDetected ? DETECTION_COOLDOWN : MAC_DETECTION_COOLDOWN

    if (!forceRefresh && lastDetectionTime.value && (now - lastDetectionTime.value) < effectiveCooldown) {
      // Masih dalam cooldown period
      if (macAlreadyDetected) {
        console.log('🛡️ Panggilan deteksi diblokir karena cooldown (MAC sudah terdeteksi).')
        return detectionResult.value
      }
      else {
        console.log(`⏱️ Dalam cooldown period (${(now - lastDetectionTime.value) / 1000}s), tapi MAC belum terdeteksi.`)
        // Untuk kasus dimana MAC belum terdeteksi dan dalam cooldown lebih pendek, lanjutkan deteksi
        if ((now - lastDetectionTime.value) < MAC_DETECTION_COOLDOWN) {
          return detectionResult.value
        }
        console.log('🚀 Mengesampingkan cooldown karena MAC belum terdeteksi.')
      }
    }

    console.log(`🔍 Memulai deteksi klien... ${forceRefresh ? '(Force Refresh)' : ''}`)

    // Clear client-side cache jika force refresh
    if (forceRefresh) {
      try {
        const keys = Object.keys(localStorage)
        keys.forEach((key) => {
          if (key.startsWith('client_detection_')) {
            localStorage.removeItem(key)
            console.log(`🧹 [CACHE-CLEAR] Cleared cache: ${key}`)
          }
        })
      }
      catch (_e) {
        // Ignore localStorage errors
      }
    }

    const detectionPromise = performDetection(forceRefresh)
    singleton.setGlobalDetectionPromise(detectionPromise)

    try {
      return await detectionPromise
    }
    finally {
      singleton.setGlobalDetectionPromise(null)
    }
  }

  // --- Public Methods ---
  const triggerDetection = async (): Promise<DetectionResult | null> => {
    console.log('🔄 Deteksi manual dipicu.')
    return await detectClientInfo()
  }

  const forceDetection = async (): Promise<DetectionResult | null> => {
    console.log('🚀 Memaksa deteksi baru: membersihkan cache dan mendeteksi ulang...')
    return await detectClientInfo(true)
  }

  // --- Lifecycle Hook ---
  // Only add the onMounted hook if we're in a component context
  if (getCurrentInstance()) {
    onMounted(async () => {
      // Saat komponen dimuat, panggil detectClientInfo.
      // Fungsi ini sudah memiliki semua mekanisme pelindung (singleton, cooldown)
      // untuk mencegah panggilan yang tidak perlu.
      console.log('🔍 Komponen ter-mount, memeriksa kebutuhan deteksi...')
      await detectClientInfo()
    })
  }

  // --- Return Public API ---
  return {
    isLoading: readonly(isLoading),
    clientInfo: readonly(clientInfo),
    detectionResult: readonly(detectionResult),
    error: readonly(error),
    detectClientInfo,
    triggerDetection,
    forceDetection,
    needsManualDetection,
    isClientInCaptivePortal,
  }
}
