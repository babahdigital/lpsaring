// store/maintenance.ts
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import { useSettingsStore } from './settings'

export const useMaintenanceStore = defineStore('maintenance', () => {
  const isActive = ref(false)
  const message = ref('Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.')

  function setMaintenanceStatus(active: boolean, customMessage?: string) {
    isActive.value = active
    if (typeof customMessage === 'string' && customMessage.length > 0) {
      message.value = customMessage
    }
  }

  // PERBAIKAN: Panggil `useSettingsStore` di dalam watcher.
  // Ini menunda akses ke settingsStore sampai Pinia benar-benar siap.
  watch(() => {
    // Panggil store di sini agar berada dalam konteks yang aman
    const settingsStore = useSettingsStore()
    return settingsStore.settings
  }, (newSettings) => {
    const active = (newSettings as any).MAINTENANCE_MODE_ACTIVE === 'True'
    const msg = (newSettings as any).MAINTENANCE_MODE_MESSAGE ?? 'Aplikasi sedang dalam perbaikan.'
    setMaintenanceStatus(active, msg)
  }, { deep: true, immediate: true })

  return {
    isActive,
    message,
    setMaintenanceStatus,
  }
})
