<script setup lang="ts">
interface SlowResource {
  name: string
  duration: number
}

// Use our enhanced network status composable
const networkStatus = useNetworkStatus()
const isSlowConnection = ref(false)
const slowResources = ref<SlowResource[]>([])
const showIndicator = ref(false)
const hmrConnected = ref(true)

const statusIcon = computed(() => {
  if (!networkStatus.isOnline.value)
    return '🔴'
  if (!hmrConnected.value)
    return '🟠'
  if (isSlowConnection.value)
    return '🟡'

  // Enhanced status based on connection quality
  if (networkStatus.effectiveType.value === '4g')
    return '🟢'
  if (networkStatus.effectiveType.value === '3g')
    return '🟡'
  if (networkStatus.effectiveType.value === '2g')
    return '�'

  return '�🟢'
})

const statusText = computed(() => {
  if (!networkStatus.isOnline.value)
    return 'Offline'
  if (!hmrConnected.value)
    return 'HMR Disconnected'
  if (isSlowConnection.value)
    return 'Koneksi Lambat'

  // Enhanced status text with connection details
  const type = networkStatus.effectiveType.value
  const connectionInfo = type !== 'unknown' ? ` (${type.toUpperCase()})` : ''
  return `Online${connectionInfo}`
})

function getResourceName(fullPath: string) {
  return fullPath.split('/').pop() || fullPath
}

// Monitor online/offline status function
function updateOnlineStatus() {
  if (import.meta.client) {
    showIndicator.value = !networkStatus.isOnline.value || isSlowConnection.value || slowResources.value.length > 0 || !hmrConnected.value
  }
}

// Network status monitoring
if (import.meta.client) {
  // Watch for network status changes from our composable
  watch([networkStatus.isOnline, networkStatus.effectiveType], updateOnlineStatus)

  // Monitor HMR connection in development
  if (process.dev && import.meta.hot) {
    import.meta.hot.on('vite:connected', () => {
      hmrConnected.value = true
      console.log('🔥 HMR Connected')
      updateOnlineStatus()
    })

    import.meta.hot.on('vite:error', () => {
      hmrConnected.value = false
      console.warn('🔥 HMR Error')
      updateOnlineStatus()
    })
  }

  // Monitor slow resources via Performance API
  if ('PerformanceObserver' in window) {
    const observer = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        if (entry.entryType === 'resource' && entry.duration > 3000) {
          const slowResource = {
            name: entry.name,
            duration: entry.duration,
          }

          // Tambah ke list jika belum ada
          if (!slowResources.value.find(r => r.name === entry.name)) {
            slowResources.value.push(slowResource)
            isSlowConnection.value = true
            showIndicator.value = true

            // Auto hide setelah 10 detik
            setTimeout(() => {
              const index = slowResources.value.findIndex(r => r.name === entry.name)
              if (index > -1) {
                slowResources.value.splice(index, 1)
              }
              if (slowResources.value.length === 0) {
                isSlowConnection.value = false
                showIndicator.value = !networkStatus.isOnline.value || !hmrConnected.value
              }
            }, 10000)
          }
        }
      })
    })

    try {
      observer.observe({ entryTypes: ['resource'] })
    }
    catch (e) {
      console.log('Network monitoring not available:', e)
    }
  }

  // Initial status
  updateOnlineStatus()
}

onUnmounted(() => {
  // useNetworkStatus composable handles cleanup automatically
})
</script>

<template>
  <div
    v-if="showIndicator"
    class="network-status"
    :class="{
      'status-online': networkStatus.isOnline && hmrConnected,
      'status-offline': !networkStatus.isOnline,
      'status-slow': isSlowConnection,
      'status-hmr-disconnected': !hmrConnected && networkStatus.isOnline,
    }"
  >
    <div class="status-icon">
      {{ statusIcon }}
    </div>
    <div class="status-text">
      {{ statusText }}
      <!-- Show additional network info if available -->
      <div v-if="networkStatus.isOnline.value && (networkStatus.downlink.value > 0 || networkStatus.rtt.value > 0)" class="network-details">
        <span v-if="networkStatus.downlink.value > 0">{{ networkStatus.downlink.value.toFixed(1) }}Mbps</span>
        <span v-if="networkStatus.rtt.value > 0">{{ networkStatus.rtt.value }}ms RTT</span>
      </div>
    </div>
    <div v-if="slowResources.length > 0" class="slow-resources">
      <details>
        <summary>{{ slowResources.length }} resource lambat</summary>
        <ul>
          <li v-for="resource in slowResources" :key="resource.name">
            {{ getResourceName(resource.name) }} - {{ Math.round(resource.duration) }}ms
          </li>
        </ul>
      </details>
    </div>
  </div>
</template>

<style scoped>
.network-status {
  position: fixed;
  top: 20px;
  right: 20px;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  z-index: 10000;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  min-width: 200px;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.status-online {
  border-left: 4px solid #4CAF50;
}

.status-offline {
  border-left: 4px solid #f44336;
}

.status-slow {
  border-left: 4px solid #ff9800;
}

.status-hmr-disconnected {
  border-left: 4px solid #ff5722;
}

.status-icon {
  display: inline-block;
  margin-right: 8px;
  font-size: 16px;
}

.status-text {
  display: inline-block;
  font-weight: 500;
}

.network-details {
  font-size: 11px;
  color: #ccc;
  margin-top: 2px;
}

.network-details span {
  margin-right: 8px;
}

.slow-resources {
  margin-top: 8px;
  font-size: 12px;
}

.slow-resources details {
  cursor: pointer;
}

.slow-resources summary {
  color: #ff9800;
  margin-bottom: 4px;
}

.slow-resources ul {
  margin: 4px 0;
  padding-left: 16px;
  list-style: none;
}

.slow-resources li {
  margin: 2px 0;
  color: #ccc;
  font-family: monospace;
  font-size: 11px;
}

.slow-resources li::before {
  content: "⚠️ ";
  margin-right: 4px;
}
</style>
