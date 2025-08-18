// plugins/02.error-handler.client.ts

export default defineNuxtPlugin({
  name: 'error-handler',
  setup() {
    // Global error handler untuk debugging
    const router = useRouter()

    // Handle unhandled errors
    window.addEventListener('error', (event) => {
      // Ignore common browser-related errors that don't affect functionality
      const ignoredErrors = [
        'ResizeObserver loop completed with undelivered notifications',
        'ResizeObserver loop completed',
        'The resource https://dev.sobigidul.com/favicon.png was preloaded',
        'favicon.png was preloaded using link preload but not used',
        'Non-Error promise rejection captured',
        'Loading CSS chunk',
        'Failed to fetch dynamically imported module',
      ]

      const shouldIgnore = ignoredErrors.some(ignoredError =>
        event.message?.includes(ignoredError),
      )

      if (shouldIgnore) {
        return // Don't log these harmless errors
      }

      console.error('[GLOBAL-ERROR]', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        error: event.error,
        stack: event.error?.stack,
      })

      // Check if this is a URL decoding error
      if (event.message?.includes('URI') || event.message?.includes('decode')) {
        console.error('[URL-DECODE-ERROR] Possible URL parameter issue')

        // Try to get current URL parameters
        try {
          const url = new URL(window.location.href)
          console.error('[URL-PARAMS]', {
            search: url.search,
            searchParams: Object.fromEntries(url.searchParams),
            pathname: url.pathname,
          })
        }
        catch (urlError) {
          console.error('[URL-ANALYSIS-ERROR]', urlError)
        }
      }
    })

    // Handle unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      // Ignore ResizeObserver and other harmless promise rejections
      const rejection = event.reason

      if (rejection && (typeof rejection === 'string' || rejection.message)) {
        const rejectionMsg = typeof rejection === 'string' ? rejection : rejection.message
        const ignoredRejections = [
          'ResizeObserver loop completed',
          'The resource https://dev.sobigidul.com/favicon.png was preloaded',
          'favicon.png was preloaded using link preload but not used',
        ]

        const shouldIgnore = ignoredRejections.some(ignored =>
          rejectionMsg.includes(ignored),
        )

        if (shouldIgnore) {
          event.preventDefault() // Prevent default logging
          return
        }
      }

      console.error('[PROMISE-REJECTION]', {
        reason: event.reason,
        promise: event.promise,
      })

      // Check if this is related to navigation or routing
      if (event.reason?.toString().includes('navigation')
        || event.reason?.toString().includes('router')) {
        console.error('[NAVIGATION-ERROR] Router or navigation issue detected')
      }
    })

    // Vue error handler for debugging
    if (import.meta.client) {
      const nuxtApp = useNuxtApp()

      nuxtApp.hook('vue:error', (error, context) => {
        console.error('[VUE-ERROR]', {
          error,
          context,
          stack: error instanceof Error ? error.stack : undefined,
        })
      })

      // Route error handling
      router.onError((error) => {
        console.error('[ROUTER-ERROR]', {
          error,
          currentRoute: router.currentRoute.value,
          stack: error instanceof Error ? error.stack : 'No stack trace',
        })
      })
    }

    console.log('[ERROR-HANDLER] Global error handlers initialized')
  },
})
