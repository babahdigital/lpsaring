// plugins/01.vue-router-error-handler.client.ts

export default defineNuxtPlugin({
  name: 'vue-router-error-handler',
  setup() {
    // Global error handler untuk Vue Router errors
    const router = useRouter()

    // Handle router errors
    router.onError((error) => {
      console.error('[ROUTER-ERROR-HANDLER] Vue Router error caught:', error)

      // Check if this is a captive browser
      const isCaptiveBrowser = (window as any).__IS_CAPTIVE_BROWSER__ || false

      if (isCaptiveBrowser) {
        console.log('[ROUTER-ERROR-HANDLER] Handling router error in captive browser')

        // Get current URL and try to navigate using window.location
        const currentPath = window.location.pathname
        const currentSearch = window.location.search

        // If we're not on captive page, go there
        if (!currentPath.startsWith('/captive')) {
          console.log('[ROUTER-ERROR-HANDLER] Redirecting to captive portal due to router error')
          window.location.href = `/captive${currentSearch}`
        }
        else {
          // If already on captive page, just reload
          console.log('[ROUTER-ERROR-HANDLER] Reloading current captive page due to router error')
          window.location.reload()
        }
      }
    })

    // Global window error handler untuk menangkap vue-router.mjs errors
    window.addEventListener('error', (event) => {
      const error = event.error
      const message = event.message || ''
      const filename = event.filename || ''

      // Check if this is a vue-router error
      if (filename.includes('vue-router') || message.includes('router')) {
        console.error('[ROUTER-ERROR-HANDLER] Vue Router script error caught:', {
          message,
          filename,
          lineno: event.lineno,
          colno: event.colno,
          error,
        })

        // Check if this is a captive browser
        const isCaptiveBrowser = (window as any).__IS_CAPTIVE_BROWSER__ || false

        if (isCaptiveBrowser) {
          console.log('[ROUTER-ERROR-HANDLER] Handling vue-router script error in captive browser')

          // Prevent default error handling
          event.preventDefault()

          // Use fallback navigation
          const currentPath = window.location.pathname
          const currentSearch = window.location.search

          if (!currentPath.startsWith('/captive')) {
            console.log('[ROUTER-ERROR-HANDLER] Fallback navigation to captive portal')
            setTimeout(() => {
              window.location.href = `/captive${currentSearch}`
            }, 100)
          }
          else {
            console.log('[ROUTER-ERROR-HANDLER] Already on captive page, continuing...')
          }

          return false // Prevent error propagation
        }
      }
    })

    // Handle unhandled promise rejections from router
    window.addEventListener('unhandledrejection', (event) => {
      const reason = event.reason

      // Check if this is a router-related promise rejection
      if (reason && (
        reason.message?.includes('router')
        || reason.stack?.includes('vue-router')
        || reason.name?.includes('NavigationFailure')
      )) {
        console.error('[ROUTER-ERROR-HANDLER] Router promise rejection caught:', reason)

        const isCaptiveBrowser = (window as any).__IS_CAPTIVE_BROWSER__ || false

        if (isCaptiveBrowser) {
          console.log('[ROUTER-ERROR-HANDLER] Handling router promise rejection in captive browser')

          // Prevent unhandled rejection
          event.preventDefault()

          // Use fallback navigation if needed
          const currentPath = window.location.pathname
          const currentSearch = window.location.search

          if (!currentPath.startsWith('/captive')) {
            console.log('[ROUTER-ERROR-HANDLER] Fallback navigation due to promise rejection')
            setTimeout(() => {
              window.location.href = `/captive${currentSearch}`
            }, 100)
          }
        }
      }
    })

    console.log('[ROUTER-ERROR-HANDLER] Vue Router error handlers initialized')
  },
})
