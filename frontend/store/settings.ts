// store/settings.ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface AppSettings {
  // Backend keys without VUEXY_ prefix (based on console log)
  SKIN?: 'default' | 'bordered'
  APP_CONTENT_LAYOUT_NAV?: 'vertical' | 'horizontal'
  APP_CONTENT_WIDTH?: 'full' | 'boxed'
  THEME?: 'light' | 'dark' | 'system'
  FOOTER_TYPE?: 'sticky' | 'static' | 'hidden'
  NAVBAR_TYPE?: 'sticky' | 'static' | 'hidden'

  // Also support prefixed versions for compatibility
  VUEXY_SKIN?: 'default' | 'bordered'
  VUEXY_APP_CONTENT_LAYOUT_NAV?: 'vertical' | 'horizontal'
  VUEXY_APP_CONTENT_WIDTH?: 'full' | 'boxed'
  VUEXY_THEME?: 'light' | 'dark' | 'system'
  VUEXY_FOOTER_TYPE?: 'sticky' | 'static' | 'hidden'
  VUEXY_NAVBAR_TYPE?: 'sticky' | 'static' | 'hidden'

  // Other settings
  APP_NAME?: string
  MAX_FAILED_LOGIN_ATTEMPTS?: string
  LOGIN_LOCKOUT_DURATION?: string
  MAINTENANCE_MODE_ACTIVE?: string

  // Add other settings as needed
  [key: string]: any
}

const ssrSafeLocalStorage = {
  getItem: (key: string): string | null => {
    if (typeof window === 'undefined') {
      return null
    }
    try {
      return window.localStorage.getItem(key)
    }
    catch (error) {
      console.warn(`Failed to read "${key}" from localStorage:`, error)
      return null
    }
  },
  setItem: (key: string, value: string): void => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.setItem(key, value)
    }
    catch (error) {
      console.warn(`Failed to write "${key}" to localStorage:`, error)
    }
  },
  removeItem: (key: string): void => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.removeItem(key)
    }
    catch (error) {
      console.warn(`Failed to remove "${key}" from localStorage:`, error)
    }
  },
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>({})
  const isLoaded = ref(false)

  const hasSettings = computed(() => isLoaded.value && Object.keys(settings.value).length > 0)

  /**
   * [PERBAIKAN] Fungsi ini sekarang menjadi satu-satunya cara untuk memuat pengaturan.
   * Fungsi ini mengatur data dan juga menandai bahwa proses pemuatan telah selesai.
   */
  function setSettings(newSettings: Partial<AppSettings>) {
    if (typeof newSettings === 'object' && newSettings !== null) {
      // Respect backend settings, just log them for debugging
      settings.value = { ...settings.value, ...newSettings }
      console.log('🎨 Settings loaded from backend:', newSettings)
    }
    else {
      console.error('setSettings expects an object, but received:', newSettings)
      settings.value = {} // Fallback ke objek kosong jika data tidak valid
    }

    // Tandai bahwa store telah dimuat setelah data berhasil diatur.
    isLoaded.value = true
  }

  return {
    settings,
    isLoaded,
    hasSettings,
    setSettings,
  }
}, {
  persist: {
    storage: ssrSafeLocalStorage,
  },
})
