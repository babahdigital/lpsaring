// frontend/store/maintenance.ts
import { defineStore } from 'pinia'

export const useMaintenanceStore = defineStore('maintenance', () => {
  const isActive = ref(false)
  const message = ref('Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.')

  function setMaintenanceStatus(active: boolean, customMessage?: string) {
    isActive.value = active
    if (customMessage) {
      message.value = customMessage
    }
  }

  return {
    isActive,
    message,
    setMaintenanceStatus
  }
})