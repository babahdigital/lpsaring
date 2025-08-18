// plugins/00.captive-browser-optimization.client.ts

export default defineNuxtPlugin({
  name: 'captive-browser-optimization',
  setup() {
    // Deteksi captive browser
    const isCaptiveBrowser = detectCaptiveBrowser()

    if (isCaptiveBrowser) {
      console.log('[CAPTIVE-OPT] Applying captive browser optimizations')

      // Set flag global
      ; (window as any).__IS_CAPTIVE_BROWSER__ = true

      // Optimasi untuk captive browser
      applyCaptiveBrowserOptimizations()

      // Disable HMR/WebSocket untuk captive browser
      disableHotReload()

      // Optimasi routing - dengan delay untuk memastikan router ready
      setTimeout(() => {
        optimizeRoutingForCaptive()
      }, 500)

      // Optimasi timeout
      setCaptiveBrowserTimeouts()
    }
  },
})

/**
 * Deteksi captive browser berdasarkan user agent dan karakteristik lainnya
 */
function detectCaptiveBrowser(): boolean {
  if (import.meta.server)
    return false

  const userAgent = navigator.userAgent
  const captivePatterns = [
    /CaptiveNetworkSupport/i,
    /Apple-captive/i,
    /iOS.*CaptiveNetworkSupport/i,
    /Android.*CaptivePortalLogin/i,
    /dalvik/i,
    /Microsoft-CryptoAPI/i,
    /Microsoft NCSI/i,
    /wispr/i,
    /CaptivePortal/i,
    /ConnectivityCheck/i,
    /NetworkProbe/i,
  ]

  // Check user agent
  const userAgentMatch = captivePatterns.some(pattern => pattern.test(userAgent))

  // Check untuk karakteristik captive browser lainnya
  const hasLimitedFeatures = !window.localStorage || !window.sessionStorage
  const hasLimitedHistory = window.history.length <= 1

  // Force captive mode for testing blocked users
  // Check if URL contains captive route and force captive mode
  const isCaptiveRoute = window.location.pathname.includes('/captive')
  const hasTestParam = window.location.search.includes('force_captive=true')

  return userAgentMatch || (hasLimitedFeatures && hasLimitedHistory) || isCaptiveRoute || hasTestParam
}

/**
 * Terapkan optimasi khusus untuk captive browser
 */
function applyCaptiveBrowserOptimizations() {
  // Disable Vue DevTools
  const globalWindow = window as any
  if (globalWindow.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
    globalWindow.__VUE_DEVTOOLS_GLOBAL_HOOK__.enabled = false
  }

  // Disable console.log di production untuk performa
  if (import.meta.env.PROD) {
    console.log = () => { }
    console.debug = () => { }
    console.info = () => { }
  }

  // Set aggressive garbage collection
  if (typeof globalWindow.gc === 'function') {
    setInterval(() => {
      try {
        globalWindow.gc()
      }
      catch {
        // Ignore errors
      }
    }, 30000)
  }
}

/**
 * Disable hot reload dan WebSocket connections untuk captive browser
 */
function disableHotReload() {
  // Override WebSocket untuk mencegah HMR connections
  const OriginalWebSocket = window.WebSocket
  window.WebSocket = class extends OriginalWebSocket {
    constructor(url: string | URL, protocols?: string | string[]) {
      // Blokir koneksi HMR/DevTools
      const urlString = url.toString()
      if (urlString.includes('_nuxt')
        || urlString.includes('__vite_hmr')
        || urlString.includes('ws://')
        || urlString.includes('devtools')) {
        console.log('[CAPTIVE-OPT] Blocking WebSocket connection:', urlString)
        // Return dummy WebSocket that immediately closes
        super('ws://invalid')
        this.close()
        return this
      }

      super(url, protocols)
    }
  }

  // Disable EventSource (Server-Sent Events)
  if (window.EventSource) {
    window.EventSource = class {
      constructor() {
        // Dummy EventSource
      }

      close() { }
      addEventListener() { }
      removeEventListener() { }
    } as any
  }
}

/**
 * Optimasi routing untuk captive browser
 */
function optimizeRoutingForCaptive() {
  // Wait for router to be available
  try {
    const nuxtApp = useNuxtApp()
    const router = nuxtApp.$router

    if (!router) {
      console.warn('[CAPTIVE-OPT] Router not available yet')
      return
    }

    // Add beforeEach guard untuk mencegah infinite redirect
    router.beforeEach((to, from, next) => {
      // Skip jika navigasi ke route yang sama
      if (to.path === from.path
        && JSON.stringify(to.query) === JSON.stringify(from.query)
        && JSON.stringify(to.params) === JSON.stringify(from.params)) {
        console.log('[CAPTIVE-OPT] Preventing same route navigation')
        return next(false)
      }

      next()
    })

    // Override router methods untuk captive browser dengan error handling
    const originalPush = router.push
    const originalReplace = router.replace
    const originalGo = router.go

    // Override push method dengan better error handling
    router.push = async function (to: any) {
      try {
        console.log('[CAPTIVE-OPT] Router.push intercepted:', to)

        // Cek jika sudah di route yang sama
        const currentRoute = router.currentRoute.value
        const targetPath = typeof to === 'string' ? to : (to.path || '/')

        if (currentRoute.path === targetPath) {
          console.log('[CAPTIVE-OPT] Already on target route, skipping navigation')
          return Promise.resolve()
        }

        // Untuk captive browser dengan error yang persisten, gunakan fallback
        const maxRetries = 3
        let retries = 0

        while (retries < maxRetries) {
          try {
            return await originalPush.call(this, to)
          }
          catch (error: any) {
            retries++
            console.warn(`[CAPTIVE-OPT] Router.push attempt ${retries} failed:`, error)

            if (retries >= maxRetries || error.message?.includes('Infinite redirect')) {
              console.error('[CAPTIVE-OPT] Max retries reached, using location fallback')
              const url = typeof to === 'string' ? to : (to.path || '/')
              window.location.href = url
              return Promise.resolve()
            }

            // Wait before retry
            await new Promise(resolve => setTimeout(resolve, 100))
          }
        }
      }
      catch (error) {
        console.error('[CAPTIVE-OPT] Router.push critical error:', error)
        return Promise.resolve()
      }
    }

    // Override replace method dengan error handling
    router.replace = async function (to: any) {
      try {
        console.log('[CAPTIVE-OPT] Router.replace intercepted:', to)

        // Cek jika sudah di route yang sama
        const currentRoute = router.currentRoute.value
        const targetPath = typeof to === 'string' ? to : (to.path || '/')

        if (currentRoute.path === targetPath) {
          console.log('[CAPTIVE-OPT] Already on target route, skipping replace')
          return Promise.resolve()
        }

        return await originalReplace.call(this, to)
      }
      catch (error) {
        console.error('[CAPTIVE-OPT] Router.replace error:', error)
        const url = typeof to === 'string' ? to : (to.path || '/')
        window.location.replace(url)
        return Promise.resolve()
      }
    }

    // Override go method dengan error handling
    router.go = function (delta: number) {
      try {
        console.log('[CAPTIVE-OPT] Router.go intercepted:', delta)

        // Untuk captive browser, gunakan window.history sebagai fallback
        if ((window as any).__IS_CAPTIVE_BROWSER__) {
          console.log('[CAPTIVE-OPT] Using window.history fallback')
          window.history.go(delta)
          return
        }

        return originalGo.call(this, delta)
      }
      catch (error) {
        console.error('[CAPTIVE-OPT] Router.go error, using fallback:', error)
        window.history.go(delta)
      }
    }

    // Disable transition animations untuk performa
    if (router.options) {
      router.options.scrollBehavior = () => ({ left: 0, top: 0 })
    }

    console.log('[CAPTIVE-OPT] Router methods overridden with infinite redirect protection')
  }
  catch (error) {
    console.error('[CAPTIVE-OPT] Error setting up router optimization:', error)
  }
}

/**
 * Set timeout yang lebih pendek untuk captive browser
 */
function setCaptiveBrowserTimeouts() {
  // Override fetch dengan timeout yang lebih pendek
  const originalFetch = window.fetch
  window.fetch = function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
    }, 15000) // 15 detik timeout untuk captive browser

    const modifiedInit = {
      ...init,
      signal: controller.signal,
    }

    return originalFetch(input, modifiedInit).finally(() => {
      clearTimeout(timeoutId)
    })
  }

  // Set XMLHttpRequest timeout
  const originalOpen = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function (method: string, url: string | URL, async?: boolean, username?: string | null, password?: string | null) {
    originalOpen.call(this, method, url, async ?? true, username, password)
    this.timeout = 15000 // 15 detik timeout
  }
}

// Global type declaration
declare global {
  interface Window {
    __IS_CAPTIVE_BROWSER__?: boolean
    gc?: () => void
  }
}
