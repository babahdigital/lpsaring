// frontend/store/settings.ts
import { defineStore } from 'pinia';
import type { SettingSchema } from '@/types/api/settings';
import { useMaintenanceStore } from './maintenance'; // Impor store maintenance

// Impor semua enum dari lokasi sentral `frontend/types/enums.ts`
import {
  AppContentLayoutNav,
  ContentWidth,
  Skins,
  Theme,
} from '@/types/enums';

export const useSettingsStore = defineStore('settings', () => {
  const appName = ref('Portal Hotspot');
  const browserTitle = ref('Portal Hotspot');
  const theme = ref<Theme>(Theme.System);
  const skin = ref<Skins>(Skins.Bordered);
  const layout = ref<AppContentLayoutNav>(AppContentLayoutNav.Horizontal);
  const contentWidth = ref<ContentWidth>(ContentWidth.Boxed);

  const maintenanceStore = useMaintenanceStore(); // Akses store maintenance

  /**
   * Action untuk mengisi seluruh state pada store dari data API (array SettingSchema)
   * Juga akan memperbarui maintenanceStore
   */
  function setSettings(settings: SettingSchema[]) {
    const settingsMap = settings.reduce((acc, setting) => {
      if (setting.setting_value) {
        acc[setting.setting_key] = setting.setting_value;
      }
      return acc;
    }, {} as Record<string, string>);

    appName.value = settingsMap.APP_NAME || 'Portal Hotspot';
    browserTitle.value = settingsMap.APP_BROWSER_TITLE || 'Portal Hotspot';
    theme.value = (settingsMap.THEME as Theme) || Theme.System;
    skin.value = (settingsMap.SKIN as Skins) || Skins.Bordered;
    layout.value = (settingsMap.LAYOUT as AppContentLayoutNav) || AppContentLayoutNav.Horizontal;
    contentWidth.value = (settingsMap.CONTENT_WIDTH as ContentWidth) || ContentWidth.Boxed;

    // --- PENTING: Perbarui maintenanceStore dari data settings ---
    const active = settingsMap.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = settingsMap.MAINTENANCE_MODE_MESSAGE || 'Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.';
    maintenanceStore.setMaintenanceStatus(active, message);
    // -------------------------------------------------------------
  }

  /**
   * Fungsi untuk update dari object (Record<string, string>)
   * Juga akan memperbarui maintenanceStore
   */
  function setSettingsFromObject(settings: Record<string, string>) {
    appName.value = settings.APP_NAME || 'Portal Hotspot';
    browserTitle.value = settings.APP_BROWSER_TITLE || 'Portal Hotspot';
    theme.value = (settings.THEME as Theme) || Theme.System;
    skin.value = (settings.SKIN as Skins) || Skins.Bordered;
    layout.value = (settings.LAYOUT as AppContentLayoutNav) || AppContentLayoutNav.Horizontal;
    contentWidth.value = (settings.CONTENT_WIDTH as ContentWidth) || ContentWidth.Boxed;

    // --- PENTING: Perbarui maintenanceStore dari data settings ---
    const active = settings.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = settings.MAINTENANCE_MODE_MESSAGE || 'Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.';
    maintenanceStore.setMaintenanceStatus(active, message);
    // -------------------------------------------------------------
  }

  return {
    appName,
    browserTitle,
    theme,
    skin,
    layout,
    contentWidth,
    setSettings,
    setSettingsFromObject,
  };
});