// middleware/02-infinite-redirect-guard.global.ts

/**
 * Global middleware untuk mencegah infinite redirect loops
 * Harus dijalankan sebelum middleware lain (order by filename)
 */

const MAX_REDIRECTS = 3
const REDIRECT_TIMEOUT = 5000 // 5 seconds

// Track redirects in browser session
const redirectTracker = {
  count: 0,
  lastPath: '',
  timestamp: 0,

  reset() {
    this.count = 0
    this.lastPath = ''
    this.timestamp = 0
  },

  track(path: string) {
    const now = Date.now()

    // Reset counter if enough time has passed
    if (now - this.timestamp > REDIRECT_TIMEOUT) {
      this.reset()
    }

    // If same path being redirected multiple times, increment
    if (path === this.lastPath) {
      this.count++
    }
    else {
      this.count = 1
      this.lastPath = path
    }

    this.timestamp = now
    return this.count
  },

  shouldBlock(path: string) {
    const count = this.track(path)
    return count > MAX_REDIRECTS
  },
}

export default defineNuxtRouteMiddleware((to) => {
  // Skip untuk server-side rendering
  if (import.meta.server) {
    return
  }

  // Skip untuk static assets dan API routes
  if (to.path.startsWith('/_nuxt') || to.path.startsWith('/api') || to.path.startsWith('/__')) {
    return
  }

  // Check for infinite redirect
  if (redirectTracker.shouldBlock(to.path)) {
    console.error('[REDIRECT-GUARD] Infinite redirect detected for path:', to.path)
    console.error('[REDIRECT-GUARD] Blocking further redirects')

    // For captive portal, try to break the loop by going to a safe state
    if (to.path.startsWith('/captive')) {
      console.log('[REDIRECT-GUARD] Breaking captive portal loop, redirecting to login')
      // Clear any sync throttling that might be causing the loop
      localStorage.removeItem('last_device_sync')
      window.location.href = '/captive'
    }

    // Stop navigation without altering location to avoid router loops
    return
  }

  console.log('[REDIRECT-GUARD] Navigation to:', to.path, 'Redirect count:', redirectTracker.count)
})
