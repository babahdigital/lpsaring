<script setup lang="ts">
import { computed } from 'vue'
import { useApiMetricsStore } from '~/store/apiMetrics'
import { useAuthStore } from '~/store/auth'

const apiMetrics = useApiMetricsStore()
const auth = useAuthStore()

// Ringkas: circuit, failure rate, retries, status refresh terakhir
const circuitText = computed(() => apiMetrics.isCircuitOpen ? 'Circuit: Terbuka' : 'Circuit: Normal')
const failureRateText = computed(() => `Gagal: ${(apiMetrics.failureRate * 100).toFixed(0)}%`)
const retriesText = computed(() => `Retry: ${apiMetrics.state.totalRetries}`)
const lastRefreshText = computed(() => {
  const t = (auth as any).state?.lastRefreshAt as number | null
  const ok = (auth as any).state?.lastRefreshOk as boolean | null
  if (!t) return 'Refresh: —'
  const diff = Date.now() - t
  const secs = Math.round(diff / 1000)
  return `Refresh: ${ok ? 'OK' : 'Gagal'} ${secs}s lalu`
})

// Tooltips ringkas
const tipCircuit = 'Status circuit breaker API. Terbuka = sementara menahan request non‑kritis karena banyak kegagalan.'
const tipFailure = 'Persentase kegagalan request dibanding total pada sesi ini.'
const tipRetry = 'Jumlah retry otomatis akibat error sementara (mis. jaringan/5xx).'
const tipRefresh = 'Status pembaruan access token terakhir. "—" berarti belum pernah dilakukan refresh.'
</script>

<template>
  <div class="footer-compact">
    <div class="left">
      <span class="d-flex align-center text-high-emphasis">
        S O B I G I D U L &copy;
        {{ new Date().getFullYear() }}
      </span>
      <span class="d-flex align-center text-subtitle-2 font-weight-light">
        Sinkronisasi data akan dilakukan secara automatis dan berkala
      </span>
    </div>
    <div class="right" role="status">
  <VTooltip location="top"><template #activator="{ props }"><span v-bind="props">{{ circuitText }}</span></template>{{ tipCircuit }}</VTooltip>
      <span>•</span>
  <VTooltip location="top"><template #activator="{ props }"><span v-bind="props">{{ failureRateText }}</span></template>{{ tipFailure }}</VTooltip>
      <span>•</span>
  <VTooltip location="top"><template #activator="{ props }"><span v-bind="props">{{ retriesText }}</span></template>{{ tipRetry }}</VTooltip>
      <span>•</span>
  <VTooltip location="top"><template #activator="{ props }"><span v-bind="props">{{ lastRefreshText }}</span></template>{{ tipRefresh }}</VTooltip>
    </div>
  </div>
</template>

<style scoped>
.footer-compact{display:flex;align-items:center;justify-content:space-between;width:100%;padding:.35rem .75rem;font-size:12px}
.left{font-weight:600;opacity:.85}
.right{display:flex;gap:.5rem;flex-wrap:wrap;opacity:.9}
@media (max-width:640px){.footer-compact{flex-direction:column;align-items:flex-start;gap:.25rem}}
</style>
