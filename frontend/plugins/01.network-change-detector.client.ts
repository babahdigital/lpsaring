// plugins/01.network-change-detector.client.ts
// Plugin untuk mendeteksi perubahan jaringan di mobile dan trigger cache clear
// Enhanced version that also detects IP changes and forces synchronization

import { useAuthStore } from '~/store/auth'
import { useClientDetection } from '~/composables/useClientDetection'

export default defineNuxtPlugin((nuxtApp) => {
  if (import.meta.server)
    return

  // Network change detection
  let previousConnection = ''
  let ipCheckIntervalId: NodeJS.Timeout | null = null

  const checkNetworkChange = () => {
    // Check connection type if available (mobile browsers)
    const connection = (navigator as any).connection
      || (navigator as any).mozConnection
      || (navigator as any).webkitConnection

    if (connection) {
      const currentConnection = `${connection.effectiveType || 'unknown'}-${connection.type || 'unknown'}`

      if (previousConnection && previousConnection !== currentConnection) {
        console.log(`🌐 [NETWORK-CHANGE] Network changed: ${previousConnection} → ${currentConnection}`)

        // Network changed - notify other parts of app immediately
        try { window.dispatchEvent(new CustomEvent('app:network-changed')) }
        catch { }

        // Then clear backend cache via API (best-effort)
        const { $api } = useNuxtApp()
        try {
          $api('/auth/clear-cache', {
            method: 'POST',
            body: {},
          }).then(() => {
            console.log('✅ Backend cache cleared due to network change')
          }).then(() => {
            // After clearing backend cache, perform a one-time hard refresh to defeat stale caches
            try {
              if (!sessionStorage.getItem('did_hard_refresh')) {
                sessionStorage.setItem('did_hard_refresh', '1')
                setTimeout(() => {
                  // Use location.reload() to force resource revalidation
                  window.location.reload()
                }, 250)
              }
            }
            catch { /* ignore */ }
          }).catch((error: unknown) => {
            console.warn('⚠️ Failed to clear backend cache:', error)
          })
        }
        catch (error: unknown) {
          console.warn('⚠️ API not available for cache clear:', error)
        }

        // Set flag untuk network change
        sessionStorage.setItem('network_changed', 'true')

        // Clear network-sensitive cache
        const networkCacheKeys = [
          'captive_ip',
          'captive_mac',
          'client_detection_cache',
          'detected_local_ip',
          'local_ip_cache',
          'mikrotik_session_cache',
          'auth_client_info',
          // Remove throttling so sync runs immediately after network changes
          'last_device_sync',
        ]

        networkCacheKeys.forEach((key) => {
          try {
            localStorage.removeItem(key)
            console.log(`🌐 [NETWORK-CHANGE] Cleared cache: ${key}`)
          }
          catch (_e) {
            // Silent fail
          }
        })
      }

      previousConnection = currentConnection
    }
  }

  // Store detection functions/state at module scope but initialize later
  let clientDetectionAPI: ReturnType<typeof useClientDetection> | null = null

  // Initialize client detection properly when the app is ready
  nuxtApp.hooks.hook('app:created', () => {
    // Initialize inside the hook when Vue components are ready
    clientDetectionAPI = useClientDetection()
    console.log('🔍 Client detection initialized in network change plugin')

    // OPTIMASI: Gunakan triggerDetection() saat startup, bukan forceDetection()
    // Ini akan menggunakan cache jika tersedia dan valid, membuat pemuatan awal lebih cepat
    // Hanya lakukan triggerDetection jika kita tidak berada di halaman login (yang sudah melakukan forceDetection)
    if (!window.location.pathname.includes('login') && !window.location.pathname.includes('captive')) {
      setTimeout(() => {
        if (clientDetectionAPI) {
          console.log('🔍 [OPTIMIZE] Triggering standard detection during initialization (non-forced)')
          clientDetectionAPI.triggerDetection()
        }
      }, 1000) // Slight delay to ensure other components are initialized
    } else {
      console.log('🔍 [OPTIMIZE] Skipping initialization detection on login/captive page (will be handled by page)')
    }
  })

  // IP address change detection for logged-in users
  const startProactiveIpCheck = () => {
    if (ipCheckIntervalId) {
      clearInterval(ipCheckIntervalId)
    }

    ipCheckIntervalId = setInterval(async () => {
      const authStore = useAuthStore()

      // Only run if the user is logged in and not on login/captive pages
      if (authStore.isLoggedIn && !window.location.pathname.includes('login') && !window.location.pathname.includes('captive')) {
        try {
          // Skip if client detection API isn't initialized yet
          if (!clientDetectionAPI) {
            console.log('🔍 Client detection API not initialized yet, skipping IP check')
            return
          }

          // OPTIMASI: Jangan picu deteksi baru jika user baru saja login
          // dan kita sudah memiliki IP yang valid dari proses login
          const lastLoginTime = Number(sessionStorage.getItem('last_login_timestamp') || '0')
          const now = Date.now()
          const loginRecent = (now - lastLoginTime) < 60000 // 1 minute

          if (loginRecent && authStore.clientIp) {
            console.log('🛡️ [OPTIMIZE] Login baru terdeteksi, melewati deteksi IP otomatis')
            return
          }

          // Silently trigger a new detection using the API
          await clientDetectionAPI.triggerDetection()

          const currentDetectedIp = clientDetectionAPI.detectionResult.value?.summary?.detected_ip
          const storedIp = authStore.clientIp

          // If IP is detected and different from stored
          if (currentDetectedIp && storedIp && currentDetectedIp !== storedIp) {
            console.warn(`🌐 [IP-CHANGE] IP mismatch detected. Stored: ${storedIp}, Detected: ${currentDetectedIp}. Forcing sync.`)

            // Clear old state to force aggressive resync
            // Use internal state mutation to update read-only properties
            localStorage.removeItem('auth_client_ip')
            localStorage.removeItem('auth_client_mac')

            // Force refresh detection via localStorage clear
            localStorage.removeItem('client_detection_cache')

            // Call sync-device. If sync-device returns that the device is not registered
            // (because MAC is also new), authStore will automatically redirect to the authorization page.
            await authStore.syncDevice()

            // After sync, dispatch custom event to notify app of IP change
            window.dispatchEvent(new CustomEvent('app:ip-changed', {
              detail: { oldIp: storedIp, newIp: currentDetectedIp }
            }))
          }
        } catch (error) {
          console.error('[IP-CHANGE] Error during IP check:', error)
        }
      }
    }, 15000) // Check every 15 seconds
  }

  // Stop IP checking interval
  const stopProactiveIpCheck = () => {
    if (ipCheckIntervalId) {
      clearInterval(ipCheckIntervalId)
      ipCheckIntervalId = null
    }
  }

  // Initial network check
  checkNetworkChange()

  // Start IP checking when plugin loads
  startProactiveIpCheck()

  // Setup cleanup when app unmounts - use app:created as hook
  nuxtApp.hook('app:created', () => {
    // When app is created, set up the cleanup for when window unloads
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', stopProactiveIpCheck)
    }
  })

  // Monitor network changes
  if ('connection' in navigator) {
    const connection = (navigator as any).connection
    if (connection && 'addEventListener' in connection) {
      connection.addEventListener('change', checkNetworkChange)
    }
  }

  // Listen for online/offline events (mobile browsers)
  window.addEventListener('online', () => {
    console.log('🌐 [NETWORK-CHANGE] Device came online')
    sessionStorage.setItem('network_came_online', 'true')

    // When device comes back online, immediately check for IP changes
    startProactiveIpCheck()
    checkNetworkChange()
  })

  window.addEventListener('offline', () => {
    console.log('🌐 [NETWORK-CHANGE] Device went offline')
    sessionStorage.setItem('network_went_offline', 'true')
  })

  // Extend global refresh detection to include network changes
  if (typeof window !== 'undefined') {
    const originalIsPageRefresh = (window as any).__isPageRefresh

      ; (window as any).__isPageRefresh = () => {
        // Check original function first
        if (originalIsPageRefresh && originalIsPageRefresh()) {
          return true
        }

        // Network change indicators
        return sessionStorage.getItem('network_changed') === 'true'
          || sessionStorage.getItem('network_came_online') === 'true'
      }

    const originalClearFlag = (window as any).__clearRefreshFlag

      ; (window as any).__clearRefreshFlag = () => {
        // Call original function
        if (originalClearFlag) {
          originalClearFlag()
        }

        // Clear network change flags
        sessionStorage.removeItem('network_changed')
        sessionStorage.removeItem('network_came_online')
        sessionStorage.removeItem('network_went_offline')
      }
  }
})
