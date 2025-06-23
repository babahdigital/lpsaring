// frontend/store/maintenance.ts
import { defineStore } from 'pinia'

export const useMaintenanceStore = defineStore('maintenance', () => {
  const isActive = ref(false)
  const message = ref('Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.')

  function setMaintenanceStatus(active: boolean, customMessage?: string) {
    isActive.value = active

    // Periksa secara eksplisit apakah customMessage adalah string yang valid dan tidak kosong.
    // Ini untuk memenuhi aturan linter `strict-boolean-expressions`.
    if (typeof customMessage === 'string' && customMessage.length > 0) {
      message.value = customMessage
    }
  }

  return {
    isActive,
    message,
    setMaintenanceStatus,
  }
})
