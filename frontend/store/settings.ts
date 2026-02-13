import type { SettingSchema } from '@/types/api/settings'
import { Skins, Theme } from '@core/enums'
import { AppContentLayoutNav, ContentWidth } from '@layouts/enums'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useMaintenanceStore } from './maintenance'

export const useSettingsStore = defineStore('settings', () => {
  type ThemeValue = (typeof Theme)[keyof typeof Theme]
  type SkinsValue = (typeof Skins)[keyof typeof Skins]
  type LayoutValue = (typeof AppContentLayoutNav)[keyof typeof AppContentLayoutNav]
  type ContentWidthValue = (typeof ContentWidth)[keyof typeof ContentWidth]

  // --- STATE ---
  const appName = ref('')
  const browserTitle = ref('')
  const theme = ref<ThemeValue>(Theme.System)
  const skin = ref<SkinsValue>(Skins.Bordered)
  const layout = ref<LayoutValue>(AppContentLayoutNav.Horizontal)
  const contentWidth = ref<ContentWidthValue>(ContentWidth.Boxed)
  const isLoaded = ref(false)
  const rawSettings = ref<Record<string, string | null | undefined>>({})

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
    rawSettings.value = { ...settings }
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

  function getSetting(key: string, fallback: string | null = null) {
    const value = rawSettings.value[key]
    if (value === undefined || value === null || value === '')
      return fallback
    return value
  }

  function getSettingAsInt(key: string, fallback: number) {
    const value = getSetting(key, null)
    if (value == null)
      return fallback
    const parsed = Number.parseInt(value, 10)
    return Number.isNaN(parsed) ? fallback : parsed
  }

  function getSettingAsBool(key: string, fallback = false) {
    const value = getSetting(key, null)
    if (value == null)
      return fallback
    return value.toString().toLowerCase() === 'true'
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
    rawSettings,
    effectiveTheme,
    setSettings,
    setSettingsFromObject,
    getSetting,
    getSettingAsInt,
    getSettingAsBool,
  }
})
