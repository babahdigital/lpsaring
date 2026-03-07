import type { SettingSchema } from '@/types/api/settings'
import { useRuntimeConfig } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
// frontend/plugins/00.load-initial-state.ts
import { useSettingsStore } from '~/store/settings'

const TRANSIENT_STARTUP_ERROR_CODES = new Set([
  'EAI_AGAIN',
  'ECONNREFUSED',
  'ECONNRESET',
  'ENOTFOUND',
  'ETIMEDOUT',
])

function getErrorCode(error: unknown): string | null {
  if (!error || typeof error !== 'object')
    return null

  const maybeCode = (error as { code?: unknown }).code
  if (typeof maybeCode === 'string' && maybeCode.trim().length > 0)
    return maybeCode.trim().toUpperCase()

  const maybeCause = (error as { cause?: unknown }).cause
  if (!maybeCause || typeof maybeCause !== 'object')
    return null

  const causeCode = (maybeCause as { code?: unknown }).code
  if (typeof causeCode === 'string' && causeCode.trim().length > 0)
    return causeCode.trim().toUpperCase()

  return null
}

function getErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object')
    return null

  const fromStatusCode = (error as { statusCode?: unknown }).statusCode
  if (typeof fromStatusCode === 'number' && Number.isFinite(fromStatusCode))
    return Math.trunc(fromStatusCode)

  const fromStatus = (error as { status?: unknown }).status
  if (typeof fromStatus === 'number' && Number.isFinite(fromStatus))
    return Math.trunc(fromStatus)

  return null
}

function isTransientStartupError(error: unknown): boolean {
  const code = getErrorCode(error)
  if (code && TRANSIENT_STARTUP_ERROR_CODES.has(code))
    return true

  const status = getErrorStatus(error)
  return status !== null && status >= 500
}

async function waitMs(ms: number) {
  await new Promise(resolve => setTimeout(resolve, ms))
}

async function fetchPublicSettingsWithRetry(baseURL: string): Promise<SettingSchema[]> {
  const delays = [0, 250, 750, 1500, 2500, 4000]
  let lastError: unknown = null

  for (const [index, delay] of delays.entries()) {
    if (delay > 0)
      await waitMs(delay)

    try {
      const payload = await $fetch<SettingSchema[]>('settings/public', { baseURL })
      return Array.isArray(payload) ? payload : []
    }
    catch (error) {
      lastError = error

      const status = getErrorStatus(error)
      const isClientSideHttpError = status !== null && status >= 400 && status < 500
      if (isClientSideHttpError)
        throw error

      const hasNextAttempt = index < delays.length - 1
      if (!hasNextAttempt || !isTransientStartupError(error))
        continue
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Gagal memuat settings/public setelah retry')
}

export default defineNuxtPlugin(async (_nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()

  // PERBAIKAN UTAMA: Paksa plugin ini untuk hanya berjalan di sisi server.
  // Nuxt akan secara otomatis menangani transfer state (hidrasi) ke klien.
  // Ini adalah cara paling andal untuk menghindari race condition di klien.
  if (import.meta.server) {
    try {
      const runtimeConfig = useRuntimeConfig()

      // Ambil data pengaturan publik HANYA di server menggunakan URL internal lengkap.
      const publicSettings = await fetchPublicSettingsWithRetry(runtimeConfig.internalApiBaseUrl)

      // Periksa secara eksplisit apakah data yang diterima adalah array yang valid dan memiliki isi.
      // Ini memperbaiki error `ts/strict-boolean-expressions` dan membuat logika lebih aman.
      if (Array.isArray(publicSettings) && publicSettings.length > 0) {
        settingsStore.setSettings(publicSettings)
      }
      else {
        // Jika data tidak ada, kosong, atau bukan array, set state dengan array kosong.
        settingsStore.setSettings([])
      }
    }
    catch (error) {
      const errorCode = getErrorCode(error)
      const codeSuffix = errorCode ? ` code=${errorCode}` : ''

      if (isTransientStartupError(error))
        console.warn(`[startup] Pengaturan awal belum tersedia, pakai default sementara.${codeSuffix}`)
      else
        console.error(`[startup] Gagal memuat pengaturan awal dari server.${codeSuffix}`, error)

      // Set state default jika gagal agar aplikasi tidak crash.
      settingsStore.setSettings([])
      maintenanceStore.setMaintenanceStatus(false, '')
    }
  }
})
