// frontend/store/settings.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
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
  // PERBAIKAN: Ubah nilai default menjadi string kosong atau null
  // untuk mencegah flash of incorrect content saat hidrasi.
  const appName = ref('');
  const browserTitle = ref('');
  const theme = ref<Theme>(Theme.System);
  const skin = ref<Skins>(Skins.Bordered);
  const layout = ref<AppContentLayoutNav>(AppContentLayoutNav.Horizontal);
  const contentWidth = ref<ContentWidth>(ContentWidth.Boxed);
  const isLoaded = ref(false);

  const maintenanceStore = useMaintenanceStore();

  // --- ACTIONS ---

  /**
   * Fungsi internal untuk memetakan data dan memperbarui state.
   */
  function _updateAllStates(settings: Record<string, string | null | undefined>) {
    // Gunakan fallback ke string kosong jika nilai tidak ada
    appName.value = settings.APP_NAME || '';
    browserTitle.value = settings.APP_BROWSER_TITLE || '';
    theme.value = (settings.THEME as Theme) || Theme.System;
    skin.value = (settings.SKIN as Skins) || Skins.Bordered;
    layout.value = (settings.LAYOUT as AppContentLayoutNav) || AppContentLayoutNav.Horizontal;
    contentWidth.value = (settings.CONTENT_WIDTH as ContentWidth) || ContentWidth.Boxed;

    const active = settings.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = settings.MAINTENANCE_MODE_MESSAGE || '';
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
    isLoaded.value = true;
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
    isLoaded,
    setSettings,
    setSettingsFromObject,
  };
});