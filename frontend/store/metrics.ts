import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import type { MetricsBrief } from '~/types/backend-models'

import { useMetrics } from '~/composables/useMetrics'

// Konfigurasi persistence
const LS_KEY = 'metrics_snapshot_v1'

interface SnapshotV1 {
  ts: number
  data: MetricsBrief
}

export const useMetricsStore = defineStore('metrics', () => {
  // Toggle global (set window.__DISABLE_METRICS__=true sebelum init untuk mematikan)
  const disabled = typeof window !== 'undefined' && (window as any).__DISABLE_METRICS__ === true
  // Gunakan composable dengan auto=false agar kita kontrol backoff sendiri
  const { metrics, failureSeverity, refresh, lastFetched, loading, error, rateLimitedUntil, currentInterval } = useMetrics({ auto: false, intervalMs: 0 })

  // Delta lookup & failure tracking
  const deltaLookups = ref<number | null>(null)
  const _lastTotal = ref<number | null>(null)
  const consecutiveFailures = ref(0)
  const nextPlannedDelayMs = ref(15000)
  let timer: any = null

  function _scheduleNext(base?: number) {
    if (timer)
      clearTimeout(timer)
    // Jika sedang rate limited, schedule tepat ketika window berakhir (+ sedikit jitter)
    if (rateLimitedUntil.value && Date.now() < rateLimitedUntil.value) {
      const wait = rateLimitedUntil.value - Date.now()
      const jitter = Math.random() * 500
      nextPlannedDelayMs.value = wait + jitter
      timer = setTimeout(() => _tick(), wait + jitter)
      return
    }
    // Adaptive: jika gagal berturut-turut, backoff (min 5s, max 120s) + jitter agar multi-tab tidak sinkron
    const failCount = consecutiveFailures.value
    const baseDelay = (base ?? currentInterval.value) || 15000
    const factor = failCount === 0 ? 1 : Math.min(1.8 ** failCount, 8)
    const rawDelay = Math.min(Math.max(5000, baseDelay * factor), 120000)
    const jitter = rawDelay * 0.1 * Math.random() // up to 10%
    const delay = rawDelay + jitter
    nextPlannedDelayMs.value = delay
    timer = setTimeout(() => _tick(), delay)
  }

  async function _tick(force = false) {
    if (disabled)
      return // no-op jika dimatikan
    const before = Date.now()
    try {
      await refresh(force)
      if (error.value) {
        consecutiveFailures.value += 1
      }
      else {
        consecutiveFailures.value = 0
      }
    }
    catch {
      consecutiveFailures.value += 1
    }
    finally {
      // Re-schedule berdasarkan hasil
      _scheduleNext()
      // Catat durasi hanya jika perlu di masa depan
      const _elapsed = Date.now() - before
      void _elapsed
    }
  }

  function manualRefresh(force = true) {
    _tick(force)
  }

  // Hydrate dari localStorage (persisted snapshot) sebelum scheduling pertama
  if (typeof window !== 'undefined') {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (raw) {
        const snap: SnapshotV1 = JSON.parse(raw)
        // Jika snapshot < 10 menit masih relevan
        if (snap?.data && Date.now() - snap.ts < 10 * 60 * 1000) {
          ; (metrics as any).value = snap.data
          lastFetched.value = snap.ts
          _lastTotal.value = snap.data.mac_lookup_total
        }
      }
    }
    catch { /* ignore */ }
  }

  // Watch untuk delta dan persistence
  watch(metrics, (val: MetricsBrief | null) => {
    if (!val)
      return
    if (_lastTotal.value != null) {
      deltaLookups.value = val.mac_lookup_total - _lastTotal.value
    }
    _lastTotal.value = val.mac_lookup_total
    if (typeof window !== 'undefined') {
      try {
        const snapshot: SnapshotV1 = { ts: lastFetched.value || Date.now(), data: val }
        localStorage.setItem(LS_KEY, JSON.stringify(snapshot))
      }
      catch { /* ignore */ }
    }
  }, { deep: true })

  // Mulai loop adaptive jika tidak disabled
  if (!disabled) {
    _tick(true)
  }

  return {
    metrics,
    failureSeverity,
    lastFetched,
    loading,
    error,
    rateLimitedUntil,
    refresh: manualRefresh,
    deltaLookups,
    consecutiveFailures,
    nextPlannedDelayMs,
    disabled,
  }
})
