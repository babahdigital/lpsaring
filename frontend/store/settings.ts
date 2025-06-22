// frontend/store/settings.ts
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

  const effectiveTheme = computed(() => {
    if (theme.value === Theme.System) {
      if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return Theme.Dark;
      }
      return Theme.Light;
    }
    return theme.value;
  });

  // --- ACTIONS ---

  function _updateAllStates(settings: Record<string, string | null | undefined>) {
    appName.value = settings.APP_NAME || 'Portal Hotspot';
    browserTitle.value = settings.APP_BROWSER_TITLE || 'Portal Hotspot';
    theme.value = (settings.THEME as Theme) || Theme.System;
    skin.value = (settings.SKIN as Skins) || Skins.Bordered;
    layout.value = (settings.LAYOUT as AppContentLayoutNav) || AppContentLayoutNav.Horizontal;
    contentWidth.value = (settings.CONTENT_WIDTH as ContentWidth) || ContentWidth.Boxed;

    const active = settings.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = settings.MAINTENANCE_MODE_MESSAGE || 'Aplikasi sedang dalam perbaikan.';
    maintenanceStore.setMaintenanceStatus(active, message);
  }

  function setSettings(settings: SettingSchema[]) {
    // --- PERBAIKAN DI SINI ---
    // Tambahkan pengecekan untuk memastikan 'settings' adalah sebuah array.
    // Ini membuat fungsi lebih aman dan mencegah error '.reduce is not a function'.
    if (!Array.isArray(settings)) {
      console.error('setSettings expect an array, but received:', settings);
      // Atur state default jika data tidak valid untuk mencegah crash.
      _updateAllStates({});
      isLoaded.value = true;
      return;
    }

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