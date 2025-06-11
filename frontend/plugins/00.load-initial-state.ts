import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  
  // Jika data sudah dimuat (misalnya, saat navigasi sisi klien), hentikan eksekusi.
  if (settingsStore.isLoaded) {
    return
  }

  // Bagian ini hanya berjalan satu kali di sisi server saat aplikasi pertama kali dimuat.
  if (process.server) {
    try {
      // Panggil API untuk mendapatkan pengaturan publik.
      // $fetch langsung digunakan di sini karena ini adalah metode universal Nuxt.
      const publicSettings = await $fetch<SettingSchema[]>('/api/settings/public', {
        baseURL: nuxtApp.ssrContext?.event.node.req.headers.host 
          ? `http://${nuxtApp.ssrContext.event.node.req.headers.host}`
          : 'http://localhost:8000', // Fallback untuk development
      });
      
      // Setelah data didapat, isi state di Pinia store.
      settingsStore.setSettings(publicSettings || [])
      
    } catch (error) {
      console.error('KRITIS: Gagal memuat pengaturan awal dari server.', error)
      // Tetap set state kosong agar aplikasi tidak crash.
      settingsStore.setSettings([])
    }
  }
  
  // Tandai bahwa data sudah selesai dimuat.
  settingsStore.isLoaded = true
})