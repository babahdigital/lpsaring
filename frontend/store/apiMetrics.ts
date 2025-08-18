// store/apiMetrics.ts
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

interface EndpointStats {
  count: number
  failures: number
  retries: number
  lastStatus: number | null
  lastError?: string
  lastAt?: number
}

interface CircuitState {
  open: boolean
  openedAt: number | null
  consecutiveFailures: number
}

interface ApiMetricsState {
  totalRequests: number
  totalFailures: number
  totalRetries: number
  endpoints: Record<string, EndpointStats>
  circuit: CircuitState
  rateLimitHits: number
}

export const useApiMetricsStore = defineStore('apiMetrics', () => {
  // Load persisted state if any
  const persisted = (typeof window !== 'undefined') ? localStorage.getItem('api_metrics_state_v1') : null
  const initial: ApiMetricsState = persisted ? (() => {
    try { return JSON.parse(persisted) as ApiMetricsState } catch { return null as any }
  })() : null as any

  const state = ref<ApiMetricsState>(initial || {
    totalRequests: 0,
    totalFailures: 0,
    totalRetries: 0,
    endpoints: {},
    circuit: { open: false, openedAt: null, consecutiveFailures: 0 },
    rateLimitHits: 0,
  })

  // Persist on change (throttled via microtask; good enough for SPA)
  if (typeof window !== 'undefined') {
    watch(state, (val) => {
      try { localStorage.setItem('api_metrics_state_v1', JSON.stringify(val)) } catch { }
    }, { deep: true })
  }

  const isCircuitOpen = computed(() => state.value.circuit.open)
  const failureRate = computed(() => state.value.totalRequests === 0 ? 0 : state.value.totalFailures / state.value.totalRequests)

  function ensure(ep: string) {
    if (!state.value.endpoints[ep]) {
      state.value.endpoints[ep] = { count: 0, failures: 0, retries: 0, lastStatus: null }
    }
    return state.value.endpoints[ep]
  }

  function recordRequest(ep: string) {
    state.value.totalRequests++
    const s = ensure(ep)
    s.count++
    s.lastAt = Date.now()
  }

  function recordSuccess(ep: string, status: number) {
    const s = ensure(ep)
    s.lastStatus = status
    state.value.circuit.consecutiveFailures = 0
  }

  function recordFailure(ep: string, status: number | null, errMsg?: string) {
    state.value.totalFailures++
    const s = ensure(ep)
    s.failures++
    s.lastStatus = status
    s.lastError = errMsg?.slice(0, 160)
    state.value.circuit.consecutiveFailures++
    if (status === 429)
      state.value.rateLimitHits++
  }

  function recordRetry(ep: string) {
    state.value.totalRetries++
    const s = ensure(ep)
    s.retries++
  }

  function openCircuit() {
    if (!state.value.circuit.open) {
      state.value.circuit.open = true
      state.value.circuit.openedAt = Date.now()
      console.warn('[API-METRICS] Circuit breaker OPENED')
    }
  }

  function closeCircuit() {
    if (state.value.circuit.open) {
      state.value.circuit.open = false
      state.value.circuit.openedAt = null
      state.value.circuit.consecutiveFailures = 0
      console.warn('[API-METRICS] Circuit breaker CLOSED')
    }
  }

  return {
    state,
    isCircuitOpen,
    failureRate,
    rateLimitHits: computed(() => state.value.rateLimitHits),
    diagnostics: computed(() => ({ total: state.value.totalRequests, fail: state.value.totalFailures, retries: state.value.totalRetries, open: state.value.circuit.open })),
    recordRequest,
    recordSuccess,
    recordFailure,
    recordRetry,
    openCircuit,
    closeCircuit,
  }
})
