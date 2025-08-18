import { computed, ref } from 'vue'

import type { DetectionResult } from './useClientDetection'

// ✅ GLOBAL SINGLETON STATE - Shared across all components
const globalDetectionState = ref<DetectionResult | null>(null)
const globalIsLoading = ref(false)
const globalError = ref<string | null>(null)
const globalLastDetectionTime = ref<number>(0)
const globalRequestCount = ref<number>(0)
const globalRequestCountTimestamp = ref<number>(0)

// ✅ GLOBAL DETECTION PROMISE - Prevent duplicate API calls
let globalDetectionPromise: Promise<DetectionResult | null> | null = null

// ✅ GLOBAL REQUEST THROTTLING
// This timestamp is used to track when we last reset the counter
const MAX_REQUESTS_PER_MINUTE = 15 // Maximum allowed requests per minute across all components

export function useClientDetectionSingleton() {
  // Computed properties for global state
  const clientInfo = computed(() => {
    const summary = globalDetectionState.value?.summary
    return {
      ip: summary?.detected_ip || null,
      mac: summary?.detected_mac || null,
      isDetected: !!(summary?.detected_ip || summary?.detected_mac),
      detectionMethod: summary?.access_mode || 'unknown',
    }
  })

  const isClientInCaptivePortal = computed(() => {
    // Check URL params for captive portal indicators
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search)
      if (urlParams.get('client_ip') || urlParams.get('client_mac')) {
        return true
      }
    }
    return globalDetectionState.value?.summary?.access_mode === 'captive'
  })

  const needsManualDetection = computed(() => {
    return !clientInfo.value.isDetected && !globalIsLoading.value
  })

  // Check if detection is needed and respect rate limits
  const shouldDetect = (forceRefresh = false) => {
    const now = Date.now()
    const timeSinceLastDetection = now - globalLastDetectionTime.value
    const hasValidData = globalDetectionState.value?.summary?.detected_ip || globalDetectionState.value?.summary?.detected_mac
    const hasMac = globalDetectionState.value?.summary?.detected_mac

    // === THROTTLING LOGIC ===
    // Reset counter if it's been more than a minute since we last reset it
    if (now - globalRequestCountTimestamp.value > 60000) {
      globalRequestCount.value = 0
      globalRequestCountTimestamp.value = now
    }

    // If we've made too many requests in the last minute, block this one
    // Allow more aggressive detection only when we don't have a MAC yet
    const requestLimit = hasMac ? MAX_REQUESTS_PER_MINUTE : MAX_REQUESTS_PER_MINUTE * 2
    if (globalRequestCount.value >= requestLimit && !forceRefresh) {
      console.warn(`🛑 [THROTTLE] Global rate limit reached (${globalRequestCount.value}/${requestLimit} requests in the last minute)`)
      return false
    }

    // Skip if we have valid data and it's recent (within 30 seconds)
    // Always allow refresh for MAC detection if we don't have a MAC yet
    if (hasValidData && timeSinceLastDetection < 30000 && (hasMac || !forceRefresh)) {
      console.log('🔄 Using cached detection data from singleton')
      return false
    }

    return true
  }

  // Track API request to avoid rate limiting
  const trackApiRequest = () => {
    const now = Date.now()
    // Reset counter if it's been more than a minute
    if (now - globalRequestCountTimestamp.value > 60000) {
      globalRequestCount.value = 1
      globalRequestCountTimestamp.value = now
      console.log('🔄 [THROTTLE] Request counter reset')
    }
    else {
      globalRequestCount.value++
      console.log(`🔢 [THROTTLE] Request count: ${globalRequestCount.value} in the last minute`)
    }
  }

  // Set global detection result
  const setGlobalDetectionResult = (result: DetectionResult | null) => {
    globalDetectionState.value = result
    globalLastDetectionTime.value = Date.now()
    globalIsLoading.value = false
    globalError.value = null
  }

  // Set global error
  const setGlobalError = (error: string) => {
    globalError.value = error
    globalIsLoading.value = false
  }

  // Set global loading state
  const setGlobalLoading = (loading: boolean) => {
    globalIsLoading.value = loading
    if (loading) {
      // Track API request only when starting a new detection
      if (loading) {
        trackApiRequest()
      }
      globalError.value = null
    }
  }

  // Get or set global detection promise
  const getGlobalDetectionPromise = () => globalDetectionPromise
  const setGlobalDetectionPromise = (promise: Promise<DetectionResult | null> | null) => {
    globalDetectionPromise = promise
  }

  // Clear global state
  const clearGlobalState = () => {
    globalDetectionState.value = null
    globalIsLoading.value = false
    globalError.value = null
    globalLastDetectionTime.value = 0
    globalDetectionPromise = null
    console.log('🗑️ Global detection state cleared')
  }

  return {
    // State
    detectionResult: globalDetectionState,
    isLoading: globalIsLoading,
    error: globalError,
    lastDetectionTime: globalLastDetectionTime,
    requestCount: globalRequestCount,
    requestCountTimestamp: globalRequestCountTimestamp,

    // Computed
    clientInfo,
    isClientInCaptivePortal,
    needsManualDetection,

    // Methods
    shouldDetect,
    trackApiRequest,
    setGlobalDetectionResult,
    setGlobalError,
    setGlobalLoading,
    getGlobalDetectionPromise,
    setGlobalDetectionPromise,
    clearGlobalState,
  }
}
