// Plugin untuk mengatasi HMR connection issues
export default defineNuxtPlugin({
  name: 'hmr-optimization',
  parallel: false,
  setup() {
    if (import.meta.client && process.dev) {
      // Check if we're in a mixed content scenario
      const isHttpsPage = window.location.protocol === 'https:'
      const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

      // If we're on HTTPS but trying to connect to local development
      if (isHttpsPage && !isLocalHost) {
        console.debug('🔧 HTTPS page detected, optimizing HMR connection...')

        // Override WebSocket constructor tetapi hanya modifikasi koneksi HMR Vite.
        // Kriteria HMR: URL mengandung '/_nuxt/' atau port HMR (24678) atau query 'vite' typical.
        const originalWebSocket = window.WebSocket
        window.WebSocket = class extends originalWebSocket {
          constructor(url: string | URL, protocols?: string | string[]) {
            const raw = url.toString()
            // Non-capturing group agar lint tidak menandai unused capturing group
            const isHmr = /_nuxt|vite|24678/.test(raw)
            if (!isHmr) {
              // Pass through tanpa modifikasi
              super(url, protocols)
              return
            }
            let wsUrl = raw
            const originalUrl = wsUrl
            if (wsUrl.startsWith('ws://') && isHttpsPage) {
              wsUrl = wsUrl.replace('ws://', 'wss://')
              if (wsUrl.includes('dev.sobigidul.com:4000'))
                wsUrl = wsUrl.replace(':4000', ':443')
              if (wsUrl.includes('localhost:4000'))
                wsUrl = wsUrl.replace('localhost:4000', 'dev.sobigidul.com:443')
              console.log('🔧 HMR WS URL rewrite:', { original: originalUrl, converted: wsUrl })
            }
            super(wsUrl, protocols)
          }
        }

        // Also patch any existing Vite WebSocket attempts
        // @ts-expect-error - Patching Vite internals
        if (window.__vite_plugin_react_preamble_installed__ || window.import?.meta?.hot) {
          console.log('🔧 Patching existing Vite WebSocket connections...')
        }
      }

      // Add comprehensive error handling for HMR connections
      let hmrRetryCount = 0
      const maxHmrRetries = 3

      const handleHmrError = (error: any) => {
        console.warn('🔧 HMR connection error:', error)
        hmrRetryCount++

        if (hmrRetryCount <= maxHmrRetries) {
          console.warn(`🔄 HMR connection failed, retrying ${hmrRetryCount}/${maxHmrRetries}...`)

          // Wait a bit before retry with exponential backoff
          setTimeout(() => {
            // Try to reconnect if Vite client is available
            // @ts-expect-error - Accessing Vite internals for HMR reconnection
            if (window.__vite__ && typeof window.__vite__.ws?.connect === 'function') {
              try {
                // @ts-expect-error - Vite internal API
                window.__vite__.ws.connect()
              }
              catch (reconnectError) {
                console.warn('🔧 Manual HMR reconnect failed:', reconnectError)
              }
            }
          }, 1000 * hmrRetryCount)
        }
        else {
          console.warn('🚫 HMR connection failed permanently. Falling back to manual refresh.')
          // Show user-friendly message
          const notification = document.createElement('div')
          notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #ff6b6b;
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            font-family: system-ui, sans-serif;
            font-size: 14px;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          `
          notification.innerHTML = `
            <div style="margin-bottom: 8px;">⚠️ Hot reload disconnected</div>
            <div style="font-size: 12px; opacity: 0.9;">Manual refresh required for changes</div>
          `
          document.body.appendChild(notification)

          // Auto-remove notification after 5 seconds
          setTimeout(() => {
            if (notification.parentNode) {
              notification.parentNode.removeChild(notification)
            }
          }, 5000)
        }
      }

      // Listen for WebSocket errors
      window.addEventListener('error', (event) => {
        if (event.message && event.message.includes('WebSocket')) {
          handleHmrError(event)
        }
      })

      // Listen for unhandled promise rejections (WebSocket connection failures)
      window.addEventListener('unhandledrejection', (event) => {
        if (event.reason && event.reason.message && event.reason.message.includes('WebSocket')) {
          handleHmrError(event.reason)
          event.preventDefault() // Prevent console spam
        }
      })

      // Listen for Vite HMR events if available
      if (import.meta.hot) {
        import.meta.hot.on('vite:error', (data) => {
          console.error('🔥 Vite HMR Error:', data)
          handleHmrError(data)
        })
      }
    }
  },
})
