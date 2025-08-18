// composables/useClientGlobalState.ts
import { readonly, ref } from 'vue'

// Definisikan tipe data untuk informasi klien
export interface ClientInfo {
  ip: string | null
  mac: string | null
  isDetected: boolean
  detectionMethod: string
  lastUpdated?: number
}

// Buat state global
const clientInfo = ref<ClientInfo>({
  ip: null,
  mac: null,
  isDetected: false,
  detectionMethod: 'unknown',
  lastUpdated: 0,
})
const isLoading = ref<boolean>(false)
const error = ref<string | null>(null)
const detectionPromise = ref<Promise<any> | null>(null)

// Export a function to use the global state
export function useClientGlobalState() {
  return {
    clientInfo: readonly(clientInfo),
    isLoading: readonly(isLoading),
    error: readonly(error),

    // Setter functions
    setClientInfo(info: Partial<ClientInfo>) {
      clientInfo.value = {
        ...clientInfo.value,
        ...info,
        lastUpdated: Date.now(),
        isDetected: !!(info.ip || info.mac || clientInfo.value.isDetected),
      }
    },

    setLoading(loading: boolean) {
      isLoading.value = loading
    },

    setError(errorMsg: string | null) {
      error.value = errorMsg
    },

    // Access the current detection promise
    getDetectionPromise() {
      return detectionPromise.value
    },

    // Set the current detection promise
    setDetectionPromise(promise: Promise<any> | null) {
      detectionPromise.value = promise
    },

    // Clear state
    clearState() {
      clientInfo.value = {
        ip: null,
        mac: null,
        isDetected: false,
        detectionMethod: 'unknown',
        lastUpdated: 0,
      }
      error.value = null
      detectionPromise.value = null
    },
  }
}
