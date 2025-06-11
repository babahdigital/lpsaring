// frontend/plugins/00.load-initial-state.ts
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()
  
  // Jika data sudah dimuat, hentikan eksekusi.
  if (settingsStore.isLoaded) {
    return
  }

  // Gunakan import.meta.server untuk kode sisi server.
  if (import.meta.server) {
    try {
      // 1. Ambil runtimeConfig yang sudah Anda definisikan di nuxt.config.ts
      const runtimeConfig = useRuntimeConfig()
      
      // 2. PERBAIKAN: Gunakan variabel yang benar dari runtimeConfig.
      // Variabel ini berisi 'http://backend:5010/api' dari .env Anda.
      const baseURL = runtimeConfig.internalApiBaseUrl;
      
      // 3. PERBAIKAN: Panggil endpoint relatif terhadap baseURL.
      // Karena baseURL sudah mengandung '/api', kita hanya perlu menambahkan 'settings/public'.
      // Hasil akhirnya akan menjadi http://backend:5010/api/settings/public
      const publicSettings = await $fetch<SettingSchema[]>('settings/public', { baseURL });
      
      // Setelah data didapat, isi state di Pinia store.
      settingsStore.setSettings(publicSettings || [])
      
      // Isi state maintenance store dari data yang sama.
      const maintenanceActive = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_ACTIVE')?.setting_value === 'True';
      const maintenanceMessage = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_MESSAGE')?.setting_value || '';
      maintenanceStore.setMaintenanceStatus(maintenanceActive, maintenanceMessage);
      
    } catch (error) {
      // Log error dengan lebih detail untuk debugging.
      console.error('KRITIS: Gagal memuat pengaturan awal dari server.', { 
        message: (error as Error).message,
        cause: (error as any).cause,
      })
      // Tetap set state kosong agar aplikasi tidak crash.
      settingsStore.setSettings([])
    }
  }
  
  // Tandai bahwa data sudah selesai dimuat.
  settingsStore.isLoaded = true
})