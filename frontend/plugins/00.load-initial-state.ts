// frontend/plugins/00.load-initial-state.ts
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()

  // PERBAIKAN UTAMA:
  // Di sisi klien, jika state 'isLoaded' sudah true (karena ditransfer dari server),
  // hentikan eksekusi untuk menghindari pengambilan data ganda dan reset state.
  if (import.meta.client && settingsStore.isLoaded) {
    return
  }

  // Kode ini akan berjalan di server, atau di klien jika ini adalah navigasi sisi klien pertama kali.
  try {
    // Gunakan $fetch universal yang tersedia di Nuxt 3. Ia akan otomatis menggunakan
    // internal URL di server dan public URL di klien.
    const publicSettings = await $fetch<SettingSchema[]>('/api/settings/public');
    
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