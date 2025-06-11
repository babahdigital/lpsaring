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

  // PERBAIKAN: Gunakan import.meta.server sebagai pengganti process.server
  // Ini adalah sintaks modern yang direkomendasikan di Nuxt 3.
  if (import.meta.server) {
    try {
      // Panggil API untuk mendapatkan pengaturan publik.
      const publicSettings = await $fetch<SettingSchema[]>('/api/settings/public', {
        baseURL: nuxtApp.ssrContext?.event.node.req.headers.host 
          ? `http://${nuxtApp.ssrContext.event.node.req.headers.host}`
          : 'http://localhost:3010', // Fallback untuk development
      });
      
      // Setelah data didapat, isi state di Pinia store.
      settingsStore.setSettings(publicSettings || [])
      
      // Isi state maintenance store dari data yang sama.
      const maintenanceActive = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_ACTIVE')?.setting_value === 'True';
      const maintenanceMessage = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_MESSAGE')?.setting_value || '';
      maintenanceStore.setMaintenanceStatus(maintenanceActive, maintenanceMessage);
      
    } catch (error) {
      console.error('KRITIS: Gagal memuat pengaturan awal dari server.', error)
      // Tetap set state kosong agar aplikasi tidak crash.
      settingsStore.setSettings([])
    }
  }
  
  // Tandai bahwa data sudah selesai dimuat.
  settingsStore.isLoaded = true
})