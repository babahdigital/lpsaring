import type { AppSettings } from '~/store/settings'

import { useMaintenanceStore } from '~/store/maintenance'
// plugins/04.settings.client.ts
import { useSettingsStore } from '~/store/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()

  // Guard tetap penting untuk mencegah fetch berulang kali saat navigasi.
  if (settingsStore.isLoaded)
    return

  try {
    const api = nuxtApp.$api as typeof $fetch
    const data = await api<AppSettings>('public', { method: 'GET' })
    console.log('[DEBUG] Raw API response:', data)
    // Memanggil setSettings akan mengisi data dan mengatur isLoaded = true
    settingsStore.setSettings(data)
  }
  catch (error: any) {
    console.error('[SETTINGS PLUGIN] Gagal memuat data settings dari API:', error)
    if (error.response?.status === 503) {
      maintenanceStore.setMaintenanceStatus(true, 'Aplikasi sedang dalam perbaikan.')
    }
    // Penting: Panggil setSettings bahkan saat gagal agar isLoaded menjadi true.
    // Ini akan mencegah aplikasi terjebak dalam state loading selamanya.
    settingsStore.setSettings({})
  }
})
