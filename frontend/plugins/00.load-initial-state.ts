import { defineNuxtPlugin, useNuxtApp } from '#app'
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

// Definisikan tipe untuk payload yang akan kita teruskan dari server ke client
interface PiniaInitialState {
  settings: ReturnType<typeof useSettingsStore>['$state'];
  maintenance: ReturnType<typeof useMaintenanceStore>['$state'];
}

/**
 * Plugin ini berjalan sebelum aplikasi diinisialisasi untuk memuat pengaturan penting
 * dari backend dan menyimpannya di Pinia store.
 */
export default defineNuxtPlugin(async () => {
  const nuxtApp = useNuxtApp()
  const settingsStore = useSettingsStore()
  const maintenanceStore = useMaintenanceStore()

  // Hanya jalankan fetch jika state belum terisi.
  if (settingsStore.isLoaded) {
    return
  }

  // Bagian ini hanya berjalan di server untuk fetch data awal
  if (process.server) {
    try {
      // PERBAIKAN: Panggil endpoint yang benar sesuai dengan backend
      const publicSettings = await nuxtApp.$api<SettingSchema[]>('/settings/public')
      
      // Mengisi settings store utama
      settingsStore.setSettings(publicSettings || [])
      
      // PERBAIKAN: Update maintenance store secara langsung setelah fetch
      // Ini memastikan maintenance store memiliki data terbaru saat inisialisasi.
      const maintenanceActive = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_ACTIVE')?.setting_value === 'True';
      const maintenanceMessage = publicSettings.find(s => s.setting_key === 'MAINTENANCE_MODE_MESSAGE')?.setting_value || '';
      maintenanceStore.setMaintenanceStatus(maintenanceActive, maintenanceMessage);
      
    } catch (error) {
      console.error('Kritis: Gagal memuat pengaturan awal dari server.', error)
      settingsStore.setSettings([])
    }
  }

  // Di server, kirim state ke client melalui payload
  if (process.server) {
    const state: PiniaInitialState = {
        settings: settingsStore.$state,
        maintenance: maintenanceStore.$state,
    };
    nuxtApp.payload.provide = nuxtApp.payload.provide || {};
    (nuxtApp.payload.provide as Record<string, any>)['pinia-initial-state'] = state;
  }
  // Di client, ambil state dari payload untuk menghindari fetch ulang
  else if (nuxtApp.payload?.provide && (nuxtApp.payload.provide as Record<string, any>)['pinia-initial-state']) {
      const initialState = (nuxtApp.payload.provide as Record<string, any>)['pinia-initial-state'] as PiniaInitialState;

      if (initialState.settings) {
          settingsStore.$patch(initialState.settings);
      }
      if (initialState.maintenance) {
          maintenanceStore.$patch(initialState.maintenance);
      }
      // Pastikan flag isLoaded juga di-set di client setelah patching
      settingsStore.isLoaded = true;
  }
})