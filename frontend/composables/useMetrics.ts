import { useNuxtApp } from '#app'
import { computed, ref } from 'vue'

import type { MetricsBrief } from '~/types/backend-models'

const metricsState = ref<MetricsBrief | null>(null)
const lastFetched = ref<number | null>(null)
let inFlight: Promise<void> | null = null
const loading = ref(false)
const error = ref<string | null>(null)
const rateLimitedUntil = ref<number | null>(null)
let dynamicInterval = 15000 // default, will adapt

export function useMetrics(options: { auto?: boolean, intervalMs?: number } = {}) {
  const { auto = true, intervalMs = 15000 } = options
  // Jika caller kirim 0 (akan diatur manual oleh store), tetap pertahankan baseline 15000 untuk perhitungan backoff 429.
  if (intervalMs > 0) {
    dynamicInterval = intervalMs
  }
  else if (!dynamicInterval || dynamicInterval <= 0) {
    dynamicInterval = 15000
  }

  async function refresh(force = false) {
    if (inFlight)
      return inFlight
    // SWR: if data fresh (< interval/2) and not forced, skip
    // Jika sedang kena rate limit, jangan fetch sampai waktunya lewat
    if (rateLimitedUntil.value && Date.now() < rateLimitedUntil.value) {
      return
    }
    if (!force && lastFetched.value && Date.now() - lastFetched.value < dynamicInterval / 2) {
      return
    }
    inFlight = (async () => {
      loading.value = true
      error.value = null
      try {
        // Gunakan $api langsung untuk menghindari warning "Component is already mounted, gunakan $fetch".
        const { $api } = useNuxtApp()
        const res = await $api<MetricsBrief | any>('/metrics/brief', { method: 'GET' })
        // Reset backoff jika sukses setelah rate limit
        if (rateLimitedUntil.value)
          rateLimitedUntil.value = null
        if (intervalMs > 0) {
          dynamicInterval = intervalMs // restore baseline eksplisit hanya jika disediakan
        }
        else if (!dynamicInterval || dynamicInterval < 5000) {
          dynamicInterval = 15000
        }
        metricsState.value = res as MetricsBrief
        lastFetched.value = Date.now()
      }
      catch (e: any) {
        // Deteksi 429 (Too Many Requests)
        const status = e?.statusCode || e?.response?.status
        if (status === 429) {
          error.value = 'rate limited'
          // Coba baca Retry-After (detik) jika ada
          let retryAfterSec: number | null = null
          try { retryAfterSec = parseInt(e?.response?._data?.retry_after || e?.response?.headers?.['retry-after']) }
          catch { /* ignore */ }
          const baseForBackoff = dynamicInterval || 15000
          const waitMs = retryAfterSec && !Number.isNaN(retryAfterSec)
            ? retryAfterSec * 1000
            : Math.min(baseForBackoff * 2, 120000)
          rateLimitedUntil.value = Date.now() + waitMs
          dynamicInterval = Math.min((dynamicInterval || 15000) * 2, 120000) // exponential up to 2m
        }
        else {
          error.value = e?.message || 'metrics fetch failed'
          // Sedikit tingkatkan interval bila sering gagal (bukan 2xx) untuk mengurangi tekanan
          dynamicInterval = Math.min((dynamicInterval || 15000) * 1.5, 60000)
        }
      }
      finally {
        loading.value = false
        inFlight = null
      }
    })()
    return inFlight
  }

  if (auto) {
    // Initial fetch (serve stale if any existing state then revalidate)
    refresh(true)
    if (intervalMs > 0) {
      // Gunakan loop adaptif ketimbang setInterval tetap
      const schedule = () => {
        const delay = rateLimitedUntil.value && Date.now() < rateLimitedUntil.value
          ? Math.max(rateLimitedUntil.value - Date.now(), 1000)
          : dynamicInterval
        setTimeout(async () => {
          await refresh()
          schedule()
        }, delay)
      }
      schedule()
      if (import.meta.hot) {
        import.meta.hot.accept(() => { /* noop re-schedule already manages itself */ })
        import.meta.hot.dispose(() => { /* nothing persistent to clear */ })
      }
    }
  }

  const failureSeverity = computed<'ok' | 'warn' | 'danger'>(() => {
    const r = metricsState.value?.failure_ratio ?? 0
    if (r > 0.4)
      return 'danger'
    if (r > 0.2)
      return 'warn'
    return 'ok'
  })

  return {
    metrics: metricsState,
    lastFetched,
    loading,
    error,
    rateLimitedUntil,
    currentInterval: computed(() => dynamicInterval),
    refresh: (force?: boolean) => refresh(force),
    failureSeverity,
  }
}
