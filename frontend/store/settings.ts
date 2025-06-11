// frontend/store/settings.ts
import { defineStore } from 'pinia';
import { ref } from 'vue'; // Pastikan 'ref' diimpor
import type { SettingSchema } from '@/types/api/settings';
import { useMaintenanceStore } from './maintenance';

// Impor semua enum dari lokasi sentral `frontend/types/enums.ts`
import {
  AppContentLayoutNav,
  ContentWidth,
  Skins,
  Theme,
} from '@/types/enums';

export const useSettingsStore = defineStore('settings', () => {
  // --- STATE ---
  const appName = ref('Portal Hotspot');
  const browserTitle = ref('Portal Hotspot');
  const theme = ref<Theme>(Theme.System);
  const skin = ref<Skins>(Skins.Bordered);
  const layout = ref<AppContentLayoutNav>(AppContentLayoutNav.Horizontal);
  const contentWidth = ref<ContentWidth>(ContentWidth.Boxed);
  
  // --- PERBAIKAN: Definisikan isLoaded sebagai ref ---
  const isLoaded = ref(false);

  const maintenanceStore = useMaintenanceStore();

  // --- ACTIONS ---

  /**
   * Fungsi internal untuk memetakan data dan memperbarui state.
   * Digunakan untuk menghindari duplikasi kode.
   */
  function _updateAllStates(settings: Record<string, string | null | undefined>) {
    appName.value = settings.APP_NAME || 'Portal Hotspot';
    browserTitle.value = settings.APP_BROWSER_TITLE || 'Portal Hotspot';
    theme.value = (settings.THEME as Theme) || Theme.System;
    skin.value = (settings.SKIN as Skins) || Skins.Bordered;
    layout.value = (settings.LAYOUT as AppContentLayoutNav) || AppContentLayoutNav.Horizontal;
    contentWidth.value = (settings.CONTENT_WIDTH as ContentWidth) || ContentWidth.Boxed;

    // Perbarui maintenanceStore dari data settings
    const active = settings.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = settings.MAINTENANCE_MODE_MESSAGE || 'Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.';
    maintenanceStore.setMaintenanceStatus(active, message);
  }

  /**
   * Action untuk mengisi seluruh state pada store dari data API (array SettingSchema)
   */
  function setSettings(settings: SettingSchema[]) {
    const settingsMap = settings.reduce((acc, setting) => {
      acc[setting.setting_key] = setting.setting_value;
      return acc;
    }, {} as Record<string, string | null>);
    
    _updateAllStates(settingsMap);
    isLoaded.value = true; // Tandai bahwa data telah dimuat
  }

  /**
   * Fungsi untuk update dari object (Record<string, string>)
   */
  function setSettingsFromObject(settings: Record<string, string>) {
     _updateAllStates(settings);
  }

  // --- RETURN ---
  return {
    appName,
    browserTitle,
    theme,
    skin,
    layout,
    contentWidth,
    isLoaded, // <-- Pastikan isLoaded di-return agar bisa diakses dari luar
    setSettings,
    setSettingsFromObject,
  };
});