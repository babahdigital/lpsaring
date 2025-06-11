// frontend/plugins/00.load-initial-state.ts
import { defineNuxtPlugin, useNuxtApp } from '#app'
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance'
import type { SettingSchema } from '@/types/api/settings'

// PERBAIKAN: Definisikan tipe untuk payload yang akan kita teruskan dari server ke client
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
      const publicSettings = await nuxtApp.$api<SettingSchema[]>('/api/settings/public')
      settingsStore.setSettings(publicSettings || [])
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
    // PERBAIKAN: Memberi tahu TypeScript tentang struktur payload
    nuxtApp.payload.provide = nuxtApp.payload.provide || {};
    (nuxtApp.payload.provide as Record<string, any>)['pinia-initial-state'] = state;
  }
  // Di client, ambil state dari payload untuk menghindari fetch ulang
  else if (nuxtApp.payload?.provide && (nuxtApp.payload.provide as Record<string, any>)['pinia-initial-state']) {
      // PERBAIKAN: Memberi tahu TypeScript tentang struktur payload saat membacanya
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
