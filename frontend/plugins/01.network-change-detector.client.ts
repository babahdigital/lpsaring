// plugins/01.network-change-detector.client.ts
// Plugin untuk mendeteksi perubahan jaringan di mobile dan trigger cache clear

export default defineNuxtPlugin(() => {
  if (import.meta.server)
    return

  // Network change detection
  let previousConnection = ''

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
        try { window.dispatchEvent(new CustomEvent('app:network-changed')) } catch { }

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

  // Initial network check
  checkNetworkChange()

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
