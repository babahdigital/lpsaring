/**
 * @file composables/useChartContainerReady.ts
 * @description Composable untuk menangani logika inisialisasi chart yang kompleks.
 * Memastikan kontainer DOM siap sebelum chart di-render untuk menghindari error.
 * Juga menangani state error dan pesan untuk mode pengembangan.
 */
import { onBeforeUnmount, ref, nextTick as vueNextTick } from 'vue'

// Placeholder untuk integrasi dengan layanan error tracking seperti Sentry
function captureException(err: Error, context?: any) {
  console.warn(`[CaptureException Placeholder] Error: ${err.message}`, context)
}

export function useChartContainerReady() {
  const chartContainerRef = ref<any>(null) // Bisa VCardText atau HTMLElement
  const isChartReadyToRender = ref(false)
  const chartContainerFailedOverall = ref(false)
  const monthlyChartKey = ref(0)
  const devErrorMessage = ref<string | null>(null)

  const observer = ref<ResizeObserver | null>(null)
  let fallbackTimeoutId: ReturnType<typeof setTimeout> | null = null

  function handleChartError(err: Error, contextMessage: string) {
    if (import.meta.env.DEV) {
      devErrorMessage.value = `[DEV] ${contextMessage}: ${err.message}${err.stack ? `\nStack: ${err.stack}` : ''}`
    }
    else {
      captureException(err, { extra: { context: 'MonthlyUsageChart', message: contextMessage } })
      devErrorMessage.value = 'Terjadi kesalahan teknis saat memuat chart.' // Pesan generik untuk production
    }

    chartContainerFailedOverall.value = true
    isChartReadyToRender.value = false
    monthlyChartKey.value++ // Force re-render
  }

  async function attemptSetReady() {
    devErrorMessage.value = null
    if (chartContainerFailedOverall.value)
      return

    await vueNextTick()
    // Mendapatkan elemen DOM dari ref Vuetify
    const containerElement = chartContainerRef.value?.$el || (chartContainerRef.value instanceof Element ? chartContainerRef.value : null)

    if (!(containerElement instanceof Element)) {
      handleChartError(new Error('Referensi kontainer chart (VCardText) tidak tersedia atau bukan elemen DOM.'), 'Inisiasi ResizeObserver')
      return
    }

    // Hentikan observer lama jika ada
    if (observer.value)
      observer.value.disconnect()

    if (fallbackTimeoutId)
      clearTimeout(fallbackTimeoutId)

    isChartReadyToRender.value = false
    try {
      observer.value = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect
          // Pastikan kontainer memiliki dimensi yang cukup untuk dirender
          if (width > 50 && height > 50) {
            if (!isChartReadyToRender.value) {
              isChartReadyToRender.value = true
              chartContainerFailedOverall.value = false
              monthlyChartKey.value++
            }
            // Hentikan observasi setelah berhasil
            observer.value?.disconnect()
            if (fallbackTimeoutId)
              clearTimeout(fallbackTimeoutId)
            return
          }
        }
      })
      observer.value.observe(containerElement)

      // Fallback jika ResizeObserver tidak ter-trigger (misal: elemen tersembunyi)
      fallbackTimeoutId = setTimeout(() => {
        if (!isChartReadyToRender.value) {
          handleChartError(new Error('Timeout (3s) menunggu kontainer chart siap.'), 'Fallback Timeout ResizeObserver')
          observer.value?.disconnect()
        }
      }, 3000)
    }
    catch (err) {
      handleChartError(err as Error, 'Eksepsi saat inisiasi ResizeObserver')
    }
  }

  function retryChartInit() {
    chartContainerFailedOverall.value = false
    isChartReadyToRender.value = false
    devErrorMessage.value = null
    monthlyChartKey.value++
    vueNextTick(attemptSetReady)
  }

  onBeforeUnmount(() => {
    if (fallbackTimeoutId)
      clearTimeout(fallbackTimeoutId)
    if (observer.value)
      observer.value.disconnect()
  })

  return {
    chartContainerRef,
    isChartReadyToRender,
    chartContainerFailedOverall,
    monthlyChartKey,
    devErrorMessage,
    attemptSetReady,
    retryChartInit,
  }
}
