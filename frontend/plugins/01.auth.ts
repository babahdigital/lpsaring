// frontend/plugins/01.auth.ts
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { useNuxtApp } from '#app'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtPlugin(async (nuxtApp) => {
  const authStore = useAuthStore()
  const settingsStore = useSettingsStore()

  // 1. Inisialisasi auth
  await authStore.initializeAuth()

  // 2. Muat pengaturan aplikasi (termasuk status maintenance) dari endpoint PUBLIK
  // Dilakukan di client-side untuk menghindari fetching ganda di SSR dan memastikan store terisi
  // jika ada refresh halaman atau navigasi langsung
  if (import.meta.client) { // Pastikan hanya dijalankan di client-side
    try {
      const { $api } = useNuxtApp()
      // Mengambil pengaturan dari endpoint publik yang tidak memerlukan otentikasi
      const publicSettings = await $api<SettingSchema[]>('/api/settings/public');

      if (publicSettings) {
        // setSettings akan memproses data dan juga memperbarui maintenanceStore
        settingsStore.setSettings(publicSettings);
      }
    } catch (error) {
      console.warn("Gagal memuat pengaturan awal aplikasi (publik):", error);
      // Jika gagal memuat pengaturan publik, berikan nilai default untuk memastikan aplikasi bisa berjalan.
      // Ini penting agar maintenance mode tidak aktif secara tidak sengaja jika API gagal diakses.
      settingsStore.setSettings([]);
    }
  }
})