// frontend/plugins/00.load-initial-state.ts
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'
import { useRuntimeConfig } from '#app'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()

  // Di sisi klien, jika state 'isLoaded' sudah true (karena ditransfer dari server),
  // hentikan eksekusi untuk menghindari pengambilan data ganda dan reset state.
  if (import.meta.client && settingsStore.isLoaded) {
    return
  }

  // Kode ini akan berjalan di server, atau di klien jika ini adalah navigasi sisi klien pertama kali.
  try {
    // PERBAIKAN: Secara eksplisit tentukan baseURL untuk panggilan di sisi server.
    const runtimeConfig = useRuntimeConfig()
    const fetchOptions: any = {}

    // Saat di server, kita HARUS menyediakan baseURL lengkap dari runtimeConfig.
    if (import.meta.server) {
      fetchOptions.baseURL = runtimeConfig.internalApiBaseUrl
    }
    // Saat di klien, proxy akan menangani path relatif, jadi tidak perlu baseURL.

    const publicSettings = await $fetch<SettingSchema[]>('settings/public', fetchOptions);
    
    // Setelah data didapat, isi state di Pinia store.
    if (publicSettings) {
        settingsStore.setSettings(publicSettings);
    } else {
        settingsStore.setSettings([]); // Pastikan tetap array kosong jika data null
    }
    
  } catch (error) {
    console.error('KRITIS: Gagal memuat pengaturan awal dari server.', error);
    // Tetap set state kosong agar aplikasi tidak crash dan maintenance tidak aktif secara salah.
    settingsStore.setSettings([])
    maintenanceStore.setMaintenanceStatus(false, '');
  }
})