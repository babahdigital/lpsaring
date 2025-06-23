import type { SettingSchema } from '@/types/api/settings'
import { useRuntimeConfig } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
// frontend/plugins/00.load-initial-state.ts
import { useSettingsStore } from '~/store/settings'

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
      const publicSettings = await $fetch<SettingSchema[]>('settings/public', {
        baseURL: runtimeConfig.internalApiBaseUrl,
      })

      if (publicSettings) {
        settingsStore.setSettings(publicSettings)
      }
      else {
        settingsStore.setSettings([])
      }
    }
    catch (error) {
      console.error('KRITIS: Gagal memuat pengaturan awal dari server.', error)
      // Set state default jika gagal agar aplikasi tidak crash.
      settingsStore.setSettings([])
      maintenanceStore.setMaintenanceStatus(false, '')
    }
  }
})
