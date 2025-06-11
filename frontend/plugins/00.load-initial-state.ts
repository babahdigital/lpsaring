import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore() // <-- Panggil store maintenance
  
  // Jika data sudah dimuat, hentikan eksekusi.
  if (settingsStore.isLoaded) {
    return
  }

  // Bagian ini hanya berjalan satu kali di sisi server saat aplikasi pertama kali dimuat.
  if (process.server) {
    try {
      // Panggil API untuk mendapatkan pengaturan publik.
      const publicSettings = await $fetch<SettingSchema[]>('/api/settings/public', {
        baseURL: nuxtApp.ssrContext?.event.node.req.headers.host 
          ? `http://${nuxtApp.ssrContext.event.node.req.headers.host}`
          : 'http://localhost:3010', // Fallback untuk development
      });
      
      // Setelah data didapat, isi state di Pinia store.
      settingsStore.setSettings(publicSettings || [])
      
      // PERBAIKAN: Isi state maintenance store dari data yang sama.
      // Ini akan membuat `useMaintenanceStore` digunakan dan memperbaiki error.
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
