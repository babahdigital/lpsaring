<script setup lang="ts">
import { computed } from 'vue'
import { useNetworkStatus } from '~/composables/useNetworkStatus'

const net = useNetworkStatus()

const netLabel = computed(() => {
  if (!net.isOnline.value) return 'Offline'
  const type = net.effectiveType.value?.toUpperCase?.() || 'UNKNOWN'
  return type
})

const mbpsText = computed(() => {
  const dl = Number(net.downlink.value || 0)
  return dl > 0 ? `${dl.toFixed(1)}Mbps` : '—'
})

const rttText = computed(() => {
  const r = Number(net.rtt.value || 0)
  return r > 0 ? `${r}ms RTT` : '—'
})

const colorClass = computed(() => {
  if (!net.isOnline.value) return 'bad'
  const r = Number(net.rtt.value || 0)
  if (r > 1000) return 'bad'
  if (r > 300) return 'warn'
  return 'good'
})
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
      <span class="badge" :class="colorClass">{{ netLabel }}</span>
      <span>•</span>
      <span class="metric">{{ mbpsText }}</span>
      <span>•</span>
      <span class="metric">{{ rttText }}</span>
    </div>
  </div>
</template>

<style scoped>
.footer-compact{display:flex;align-items:center;justify-content:space-between;width:100%;padding:.35rem .75rem;font-size:12px}
.left{font-weight:600;opacity:.85}
.right{display:flex;gap:.5rem;flex-wrap:wrap;opacity:.9}
.badge{padding:.1rem .4rem;border-radius:.5rem;font-weight:600}
.badge.good{background:rgba(76,175,80,.15);color:#2e7d32}
.badge.warn{background:rgba(255,152,0,.15);color:#ef6c00}
.badge.bad{background:rgba(244,67,54,.15);color:#c62828}
.metric{opacity:.95}
@media (max-width:640px){.footer-compact{flex-direction:column;align-items:flex-start;gap:.25rem}}
</style>
