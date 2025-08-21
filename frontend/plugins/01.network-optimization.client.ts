// Plugin untuk optimasi network di local hotspot environment
export default defineNuxtPlugin({
  name: 'network-optimization',
  parallel: false,
  setup() {
    if (!import.meta.client)
      return

    // 1. Dynamic import helper (light retry only for transient network issues)
    const originalImport = window.__import__ || ((specifier: string) => import(/* @vite-ignore */ specifier))
    window.__import__ = async (specifier: string) => {
      try {
        return await originalImport(specifier)
      }
      catch (e) {
        // Single short retry (500ms) only; avoid noisy exponential loop
        await new Promise(r => setTimeout(r, 500))
        return originalImport(specifier)
      }
    }

    // 2. (Removed) Global fetch override – caused every 429 log to reference this plugin.
    //    We rely on per-request logic (useMetrics composable) for adaptive backoff.

    // 3. Lightweight performance observer (only warn on very slow resources; no UI popups)
    try {
      const perfObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'navigation' && entry.duration > 3000)
            console.log(`📊 Navigasi lambat: ${Math.round(entry.duration)}ms`)
          if (entry.entryType === 'resource') {
            if (entry.duration > 5000) {
              // Console-only warning; UI notification removed to avoid user distraction
              console.warn(`🐢 Resource lambat: ${entry.name} (${Math.round(entry.duration)}ms)`)
            }
          }
        }
      })
      perfObserver.observe({ entryTypes: ['navigation', 'resource'] })
    }
    catch { /* ignore unsupported */ }
  },
})

// Extend window type
declare global {
  interface Window {
    __import__?: (specifier: string) => Promise<any>
  }
}
