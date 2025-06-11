// frontend/middleware/00.maintenance.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useMaintenanceStore } from '~/store/maintenance'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import type { SettingSchema } from '@/types/api/settings'

export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  const maintenanceStore = useMaintenanceStore();
  const authStore = useAuthStore();
  const settingsStore = useSettingsStore();
  const nuxtApp = useNuxtApp();

  // --- PENTING: Pastikan settings sudah dimuat sebelum mengecek maintenance ---
  // Jika appName dari settingsStore belum ada (indikasi store belum terisi dari API),
  // maka coba muat pengaturan lagi. Ini berlaku untuk SSR dan Client-side load.
  // Pastikan ini tidak menyebabkan loop jika API selalu gagal.
  if (!settingsStore.appName) { // Cek apakah settingsStore sudah terisi data awal
    try {
      const publicSettings = await nuxtApp.$api<SettingSchema[]>('/api/settings/public'); // SettingSchema digunakan di sini
      if (publicSettings) {
        settingsStore.setSettings(publicSettings); // Ini akan mengisi settingsStore DAN maintenanceStore
      }
    } catch (e) {
      console.error('Gagal memuat pengaturan di middleware maintenance:', e);
      // Jika fetching gagal, set default agar maintenance tidak aktif
      settingsStore.setSettings([]); // Pastikan maintenanceStore.isActive menjadi false
    }
  }

  const isMaintenanceActive = maintenanceStore.isActive;
  const isAdminPath = to.path.startsWith('/admin');
  const isMaintenancePage = to.path === '/maintenance';

  // Jika mode maintenance aktif
  if (isMaintenanceActive) {
    // Izinkan admin mengakses area admin
    if (isAdminPath && authStore.isAdmin) {
      return;
    }

    // Selalu izinkan akses ke halaman maintenance itu sendiri
    if (isMaintenancePage) {
      return;
    }

    // Redirect semua non-admin atau non-admin-path ke halaman maintenance
    return navigateTo('/maintenance', { replace: true });
  }
  // Jika mode maintenance TIDAK aktif
  else {
    // Jika sedang di halaman maintenance dan mode sudah tidak aktif, redirect ke home/dashboard
    if (isMaintenancePage) {
      return navigateTo('/', { replace: true });
    }
  }
});