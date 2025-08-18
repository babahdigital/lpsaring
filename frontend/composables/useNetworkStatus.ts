// composables/useNetworkStatus.ts

import { onMounted, onUnmounted, ref } from 'vue'

export function useNetworkStatus() {
  const isOnline = ref(true)
  const connectionType = ref('unknown')
  const effectiveType = ref('unknown')
  const downlink = ref(0)
  const rtt = ref(0)

  let intervalId: NodeJS.Timeout | null = null

  const updateNetworkInfo = () => {
    isOnline.value = navigator.onLine

    // Get connection info if available
    const connection = (navigator as any).connection
      || (navigator as any).mozConnection
      || (navigator as any).webkitConnection

    if (connection) {
      connectionType.value = connection.type || 'unknown'
      effectiveType.value = connection.effectiveType || 'unknown'
      downlink.value = connection.downlink || 0
      rtt.value = connection.rtt || 0
    }
  }

  const handleOnline = () => {
    console.log('🌐 Network: ONLINE')
    updateNetworkInfo()
  }

  const handleOffline = () => {
    console.log('🌐 Network: OFFLINE')
    updateNetworkInfo()
  }

  const handleConnectionChange = () => {
    console.log('🌐 Connection changed')
    updateNetworkInfo()
  }

  onMounted(() => {
    if (import.meta.client) {
      // Initial update
      updateNetworkInfo()

      // Event listeners
      window.addEventListener('online', handleOnline)
      window.addEventListener('offline', handleOffline)

      // Connection change listener
      const connection = (navigator as any).connection
      if (connection) {
        connection.addEventListener('change', handleConnectionChange)
      }

      // Periodic check for mobile devices
      intervalId = setInterval(updateNetworkInfo, 5000)
    }
  })

  onUnmounted(() => {
    if (import.meta.client) {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)

      const connection = (navigator as any).connection
      if (connection) {
        connection.removeEventListener('change', handleConnectionChange)
      }

      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  })

  return {
    isOnline: readonly(isOnline),
    connectionType: readonly(connectionType),
    effectiveType: readonly(effectiveType),
    downlink: readonly(downlink),
    rtt: readonly(rtt),
    refresh: updateNetworkInfo,
  }
}
