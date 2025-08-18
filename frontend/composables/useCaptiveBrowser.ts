// composables/useCaptiveBrowser.ts

export interface CaptiveBrowserInfo {
  isCaptiveBrowser: boolean
  browserType: string | null
  userAgent: string
  hasLimitedFeatures: boolean
}

export function useCaptiveBrowser() {
  const isCaptiveBrowser = ref(false)
  const browserInfo = ref<CaptiveBrowserInfo>({
    isCaptiveBrowser: false,
    browserType: null,
    userAgent: '',
    hasLimitedFeatures: false,
  })

  const disableAnimations = () => {
    const style = document.createElement('style')
    style.id = 'captive-browser-optimizations'
    style.innerHTML = '*, *::before, *::after { animation-duration: 0.01ms !important; }'
    document.head.appendChild(style)
  }

  const setShortTimeouts = () => {
    if (window.fetch) {
      const originalFetch = window.fetch
      window.fetch = function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
        const controller = new AbortController()
        setTimeout(() => controller.abort(), 10000)
        return originalFetch(input, { ...init, signal: controller.signal })
      }
    }
  }

  const preloadCriticalResources = () => {
    const endpoints = ['/api/auth/request-otp', '/api/auth/verify-otp']
    endpoints.forEach((endpoint) => {
      const link = document.createElement('link')
      link.rel = 'dns-prefetch'
      link.href = endpoint
      document.head.appendChild(link)
    })
  }

  const simplifyNavigation = () => {
    if (window.history) {
      ; (window.history as any).__IS_CAPTIVE_BROWSER__ = true
    }
  }

  const applyCaptiveOptimizations = () => {
    if (!import.meta.client)
      return
    disableAnimations()
    setShortTimeouts()
    preloadCriticalResources()
    simplifyNavigation()
  }

  const detectCaptiveBrowser = (): CaptiveBrowserInfo => {
    if (import.meta.server) {
      return { isCaptiveBrowser: false, browserType: null, userAgent: '', hasLimitedFeatures: false }
    }

    const userAgent = navigator.userAgent
    const patterns = [
      { pattern: /CaptiveNetworkSupport/i, type: 'iOS Captive Portal' },
      { pattern: /dalvik/i, type: 'Android Dalvik' },
    ]

    for (const { pattern, type } of patterns) {
      if (pattern.test(userAgent)) {
        return { isCaptiveBrowser: true, browserType: type, userAgent, hasLimitedFeatures: true }
      }
    }

    return { isCaptiveBrowser: false, browserType: null, userAgent, hasLimitedFeatures: false }
  }

  const initializeCaptiveDetection = () => {
    if (import.meta.client) {
      const detected = detectCaptiveBrowser()
      browserInfo.value = detected
      isCaptiveBrowser.value = detected.isCaptiveBrowser

      if (detected.isCaptiveBrowser) {
        ; (window as any).__IS_CAPTIVE_BROWSER__ = true
        applyCaptiveOptimizations()
      }
    }
  }

  const checkIsCaptiveBrowser = () => isCaptiveBrowser.value
  const getCaptiveBrowserInfo = () => browserInfo.value

  const handleCaptiveNavigation = async (to?: string) => {
    if (isCaptiveBrowser.value) {
      try {
        await navigateTo(to || '/', { replace: true })
        return true
      }
      catch {
        return false
      }
    }
    return false
  }

  return {
    isCaptiveBrowser: readonly(isCaptiveBrowser),
    browserInfo: readonly(browserInfo),
    initializeCaptiveDetection,
    checkIsCaptiveBrowser,
    getCaptiveBrowserInfo,
    handleCaptiveNavigation,
    applyCaptiveOptimizations,
  }
}

if (import.meta.client) {
  const { initializeCaptiveDetection } = useCaptiveBrowser()
  initializeCaptiveDetection()
}

declare global {
  interface Window {
    __IS_CAPTIVE_BROWSER__?: boolean
    __CAPTIVE_BROWSER_INFO__?: CaptiveBrowserInfo
  }
}
