import type { SettingSchema } from '@/types/api/settings'
// frontend/store/settings.ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
// Impor semua enum dari lokasi sentral `frontend/types/enums.ts`
import {
  AppContentLayoutNav,
  ContentWidth,
  Skins,
  Theme,
} from '@/types/enums'

import { useMaintenanceStore } from './maintenance'

export const useSettingsStore = defineStore('settings', () => {
  // --- STATE ---
  const appName = ref('')
  const browserTitle = ref('')
  const theme = ref<Theme>(Theme.System)
  const skin = ref<Skins>(Skins.Bordered)
  const layout = ref<AppContentLayoutNav>(AppContentLayoutNav.Horizontal)
  const contentWidth = ref<ContentWidth>(ContentWidth.Boxed)
  const isLoaded = ref(false)

  const maintenanceStore = useMaintenanceStore()

  const effectiveTheme = computed(() => {
    if (theme.value === Theme.System) {
      if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return Theme.Dark
      }
      return Theme.Light
    }
    return theme.value
  })

  // --- ACTIONS ---

  function _updateAllStates(settings: Record<string, string | null | undefined>) {
    // --- PERBAIKAN DI SINI: Mengganti || dengan ?? ---
    appName.value = settings.APP_NAME ?? 'Portal Hotspot'
    browserTitle.value = settings.APP_BROWSER_TITLE ?? 'Portal Hotspot'
    theme.value = (settings.THEME ?? Theme.System) as Theme
    skin.value = (settings.SKIN ?? Skins.Bordered) as Skins
    layout.value = (settings.LAYOUT ?? AppContentLayoutNav.Horizontal) as AppContentLayoutNav
    contentWidth.value = (settings.CONTENT_WIDTH ?? ContentWidth.Boxed) as ContentWidth

    const active = settings.MAINTENANCE_MODE_ACTIVE === 'True'
    const message = settings.MAINTENANCE_MODE_MESSAGE ?? 'Aplikasi sedang dalam perbaikan.'
    maintenanceStore.setMaintenanceStatus(active, message)
  }

  function setSettings(settings: SettingSchema[]) {
    if (!Array.isArray(settings)) {
      console.error('setSettings expect an array, but received:', settings)
      _updateAllStates({})
      isLoaded.value = true
      return
    }

    const settingsMap = settings.reduce((acc, setting) => {
      acc[setting.setting_key] = setting.setting_value
      return acc
    }, {} as Record<string, string | null>)

    _updateAllStates(settingsMap)
    isLoaded.value = true
  }

  function setSettingsFromObject(settings: Record<string, string>) {
    _updateAllStates(settings)
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
  }
})