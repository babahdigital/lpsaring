import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
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
  const appName = ref('');
  const browserTitle = ref('');
  const theme = ref<Theme>(Theme.System);
  const skin = ref<Skins>(Skins.Bordered);
  const layout = ref<AppContentLayoutNav>(AppContentLayoutNav.Horizontal);
  const contentWidth = ref<ContentWidth>(ContentWidth.Boxed);
  const isLoaded = ref(false);

  const maintenanceStore = useMaintenanceStore();

  // PENYEMPURNAAN: Computed property untuk mendapatkan tema yang efektif (valid untuk Vuetify)
  // Sesuai dengan analisis Anda untuk menangani tema 'system'.
  const effectiveTheme = computed(() => {
    if (theme.value === Theme.System) {
      // Cek preferensi sistem hanya di sisi klien untuk menghindari error SSR.
      if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return Theme.Dark;
      }
      return Theme.Light;
    }
    return theme.value;
  });

  // --- ACTIONS ---

  function _updateAllStates(settings: Record<string, string | null | undefined>) {
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

  function setSettings(settings: SettingSchema[]) {
    const settingsMap = settings.reduce((acc, setting) => {
      acc[setting.setting_key] = setting.setting_value;
      return acc;
    }, {} as Record<string, string | null>);
    
    _updateAllStates(settingsMap);
    isLoaded.value = true;
  }

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
    effectiveTheme,
    setSettings,
    setSettingsFromObject,
  };
});