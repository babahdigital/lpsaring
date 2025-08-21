import { computed, getCurrentInstance, onMounted, ref } from 'vue'

import { API_ENDPOINTS } from '~/constants/api-endpoints'
import { useApiMetricsStore } from '~/store/apiMetrics'
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
  circuit_breaker_active?: boolean
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
    // Check if circuit breaker is already open to determine whether to use cached data
    const apiMetricsStore = useApiMetricsStore();
    const isCircuitOpen = apiMetricsStore.isCircuitOpen;

    // Try to use cache first, especially if circuit breaker is open
    if (!headers['force-refresh'] || isCircuitOpen) {
      // Client-side cache untuk mengurangi request berulang
      const cacheKey = `client_detection_${JSON.stringify(headers)}`
      const cachedData = localStorage.getItem(cacheKey)

      if (cachedData) {
        try {
          const parsed = JSON.parse(cachedData)
          const now = Date.now()

          // Jika circuit breaker terbuka, gunakan cache bahkan jika MAC tidak terdeteksi
          if (isCircuitOpen && now - parsed.timestamp < CLIENT_SIDE_CACHE_TTL * 2) {
            console.log('🛡️ [CIRCUIT-OPEN] Using cached detection result due to open circuit');
            return parsed.data;
          }

          // Dalam kondisi normal, hanya gunakan cache jika masih fresh DAN MAC sudah terdeteksi
          if (now - parsed.timestamp < CLIENT_SIDE_CACHE_TTL && parsed.data?.summary?.mac_detected) {
            console.log('🚀 [CLIENT-CACHE] Using cached detection result with MAC');
            return parsed.data;
          }
          else if (now - parsed.timestamp < CLIENT_SIDE_CACHE_TTL) {
            console.log('⚠️ [CLIENT-CACHE] Cached result exists but MAC not detected, skipping cache');
          }
        }
        catch (e) {
          // Invalid cache, continue to API call
          console.warn('⚠️ [CLIENT-CACHE] Invalid cache:', e);
        }
      }
    }
    else {
      console.log('🚀 [CLIENT-CACHE] Forced refresh, skipping cache');
    }

    // Early return with mock data if circuit breaker is open and no cache available
    if (isCircuitOpen) {
      console.log('🛑 [CIRCUIT-OPEN] Circuit breaker is open and no cache available, returning fallback data');

      // Create a fallback response that indicates the circuit breaker is open
      const fallbackResponse: DetectionResponse = {
        status: 'LIMITED',
        summary: {
          detected_ip: headers['X-Frontend-Detected-IP'] || null,
          detected_mac: headers['X-Frontend-Detected-MAC'] || null,
          ip_detected: !!headers['X-Frontend-Detected-IP'],
          mac_detected: !!headers['X-Frontend-Detected-MAC'],
          access_mode: 'web',
          user_guidance: 'Deteksi terbatas karena server sibuk. Silakan coba lagi nanti.'
        },
        circuit_breaker_active: true
      };

      return fallbackResponse;
    }

    const cacheBust = `_t=${Date.now()}`;

    // Define endpoints to try in order (fallback mechanism)
    const endpoints = [
      {
        url: `${API_ENDPOINTS.DEVICE_DETECT}?${cacheBust}`,
        method: 'GET',
        body: null
      },
      {
        url: API_ENDPOINTS.DEVICE_AUTHORIZE,
        method: 'POST',
        body: {
          detection_only: true,
          force_refresh: !!headers['force-refresh']
        }
      }
    ];

    let lastError = null;

    // Try each endpoint in sequence until one works
    for (const endpoint of endpoints) {
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          console.log(`🌐 [CLIENT-DETECT] API call attempt ${attempt + 1}/${maxRetries + 1} to ${endpoint.url} with method ${endpoint.method}`, headers);

          const options: any = {
            headers,
            // Set retry=false to avoid extra API client retries and rely on our own retry logic
            retry: false
          };

          if (endpoint.method !== 'GET') {
            options.method = endpoint.method;
            if (endpoint.body) {
              options.body = endpoint.body;
            }
          }

          const result = await $api<DetectionResponse>(endpoint.url, options);

          // PERBAIKAN: Jika MAC tidak terdeteksi, dan ini bukan attempt terakhir, coba lagi dengan delay
          // Ini memungkinkan backend untuk memperbarui ARP table dengan ping
          if (!result.summary?.mac_detected && attempt < maxRetries) {
            const delay = 1000; // 1 detik delay untuk retry
            console.log(`⚠️ [CLIENT-DETECT] MAC tidak terdeteksi pada attempt ${attempt + 1}, retry dalam ${delay}ms...`);
            await new Promise(resolve => setTimeout(resolve, delay));

            // Pastikan refresh pada attempt berikutnya
            headers['force-refresh'] = 'true';
            if (endpoint.body) {
              endpoint.body.force_refresh = true;
            }
            continue;
          }

          // Cache hasil hanya jika berhasil dan MAC terdeteksi
          if (result.summary?.mac_detected || attempt >= maxRetries) {
            try {
              const cacheKey = `client_detection_${JSON.stringify(headers)}`;
              localStorage.setItem(cacheKey, JSON.stringify({
                data: result,
                timestamp: Date.now(),
              }));
              console.log(`💾 [CLIENT-CACHE] Saved detection result to cache (MAC detected: ${!!result.summary?.mac_detected})`);
            }
            catch (e) {
              // localStorage full, ignore
              console.warn('⚠️ [CLIENT-CACHE] Failed to save to cache:', e);
            }
          }

          return result;
        }
        catch (error: any) {
          lastError = error;

          // Check for circuit breaker error and use the first endpoint detection data if available
          if (error?.message?.includes('CIRCUIT_OPEN')) {
            console.log('🛑 [CIRCUIT-OPEN] Circuit breaker triggered during detection');

            // Return a fallback response with the IP from headers
            return {
              status: 'LIMITED',
              summary: {
                detected_ip: headers['X-Frontend-Detected-IP'] || null,
                detected_mac: headers['X-Frontend-Detected-MAC'] || null,
                ip_detected: !!headers['X-Frontend-Detected-IP'],
                mac_detected: !!headers['X-Frontend-Detected-MAC'],
                access_mode: 'web',
                user_guidance: 'Deteksi terbatas karena server sibuk. Silakan coba lagi nanti.'
              },
              circuit_breaker_active: true
            };
          }

          // If we get a 404, break out of the retry loop for this endpoint and try the next one
          if (error?.status === 404 || error?.response?.status === 404) {
            console.warn(`⚠️ Endpoint ${endpoint.url} not found (404), will try next endpoint...`);
            break;
          }

          if (error?.response?.status === 429 && attempt < maxRetries) {
            const delay = Math.min(1000 * 2 ** attempt, 5000);
            console.warn(`⏱️ Rate limited (429), mencoba lagi dalam ${delay}ms...`);
            await new Promise(resolve => setTimeout(resolve, delay));
            continue;
          }

          if (attempt < maxRetries) {
            const delay = Math.min(1000 * 2 ** attempt, 3000);
            console.warn(`⚠️ API error, mencoba lagi dalam ${delay}ms...`, error);
            await new Promise(resolve => setTimeout(resolve, delay));
            continue;
          }

          // If this is the last endpoint and last attempt, throw the error
          if (endpoint === endpoints[endpoints.length - 1]) {
            throw error;
          }
        }
      }
    }

    // If we get here, all endpoints failed
    if (lastError) {
      throw lastError;
    }
    throw new Error('Semua percobaan ulang dan endpoint gagal');
  }

  const clearAllCache = async () => {
    // ✅ PERBAIKAN: Periksa status otorisasi terlebih dahulu
    const authStore = useAuthStore()

    if (authStore.isAuthorizing) {
      console.warn('🛡️ [CLIENT-DETECT] Cache clear dibatalkan karena proses otorisasi perangkat sedang berlangsung')
      return
    }

    console.log('🧹 Clearing all IP/MAC cache...')

    // Get current detected information
    const currentLocalIP = await detectLocalIP()
    const currentIP = currentLocalIP?.ip || null
    console.log(`Current detected IP: ${currentIP || 'none'}`)

    try {
      // Clear backend cache via API with detected IP information
      const { $api } = useNuxtApp()
      // Call the backend API to clear cache using endpoint constant
      const result = await $api(API_ENDPOINTS.CLEAR_CACHE, {
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

      // The new callBackendWithRetry will try multiple endpoints with fallbacks
      const data = await callBackendWithRetry(headers);

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
    catch (err: any) {
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
    // ✅ PERBAIKAN UTAMA: Periksa status otorisasi terlebih dahulu
    const authStore = useAuthStore()

    // Jangan lakukan deteksi jika sedang dalam proses otorisasi perangkat
    if (authStore.isAuthorizing) {
      console.warn('🛡️ [CLIENT-DETECT] Deteksi dihentikan karena proses otorisasi perangkat sedang berlangsung')
      return null
    }

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
    // ✅ PERBAIKAN: Periksa status otorisasi terlebih dahulu
    const authStore = useAuthStore()

    if (authStore.isAuthorizing) {
      console.warn('🛡️ [CLIENT-DETECT] Force deteksi dihentikan karena proses otorisasi perangkat sedang berlangsung')
      return null
    }

    console.log('🚀 Memaksa deteksi baru: membersihkan cache dan mendeteksi ulang...')
    return await detectClientInfo(true)
  }

  // --- Lifecycle Hook ---
  // Only add the onMounted hook if we're in a component context
  if (getCurrentInstance()) {
    onMounted(async () => {
      // OPTIMASI: Implementasi lebih cerdas untuk deteksi otomatis pada komponen mount

      // Jika ada deteksi yang sedang berjalan atau MAC sudah terdeteksi, lewati
      if (singleton.getGlobalDetectionPromise() ||
        globalState.clientInfo.value.isDetected ||
        (detectionResult.value?.summary?.detected_mac)) {
        console.log('🛡️ [onMounted] Melewati deteksi otomatis karena sudah berjalan atau sudah terdeteksi.')
        return
      }

      // Jika halaman adalah login atau captive, lewati karena mereka akan melakukan forceDetection sendiri
      if (typeof window !== 'undefined' &&
        (window.location.pathname.includes('login') || window.location.pathname.includes('captive'))) {
        console.log('🛡️ [onMounted] Melewati deteksi otomatis pada halaman login/captive yang akan melakukan deteksi sendiri.')
        return
      }

      // Jika pengguna baru login (dalam 60 detik terakhir), asumsikan datanya fresh
      const lastLoginTime = Number(sessionStorage.getItem('last_login_timestamp') || '0')
      const now = Date.now()
      if (now - lastLoginTime < 60000 && authStore.clientIp) {
        console.log('🛡️ [onMounted] Melewati deteksi otomatis karena pengguna baru saja login.')
        return
      }

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
