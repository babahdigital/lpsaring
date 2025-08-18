// @core/stores/config.ts - VERSI SEMPURNA DENGAN IMPOR YANG BENAR

import { cookieRef, useLayoutConfigStore } from '@layouts/stores/config'
import { themeConfig } from '@themeConfig'
import { usePreferredColorScheme } from '@vueuse/core'
// [PERBAIKAN KUNCI] Menambahkan semua impor yang diperlukan dari Pinia, Vue, dan VueUse
import { defineStore, storeToRefs } from 'pinia'
import { onMounted, watch } from 'vue'
import { useTheme } from 'vuetify'

// SECTION Store
export const useConfigStore = defineStore('config', () => {
  // 👉 Theme
  const userPreferredColorScheme = usePreferredColorScheme()
  const cookieColorScheme = cookieRef<'light' | 'dark'>('color-scheme', 'light')

  watch(
    userPreferredColorScheme,
    (val) => {
      if (val !== 'no-preference')
        cookieColorScheme.value = val
    },
    { immediate: true },
  )

  const theme = cookieRef('theme', themeConfig.app.theme)

  // 👉 isVerticalNavSemiDark
  const isVerticalNavSemiDark = cookieRef('isVerticalNavSemiDark', themeConfig.verticalNav.isVerticalNavSemiDark)

  // 👉 skin
  const skin = cookieRef('skin', themeConfig.app.skin)

  // ℹ️ Kita perlu menggunakan `storeToRefs` untuk meneruskan state
  const {
    isLessThanOverlayNavBreakpoint,
    appContentWidth,
    navbarType,
    isNavbarBlurEnabled,
    appContentLayoutNav,
    isVerticalNavCollapsed,
    footerType,
    isAppRTL,
  } = storeToRefs(useLayoutConfigStore())

  return {
    theme,
    isVerticalNavSemiDark,
    skin,

    // @layouts exports
    isLessThanOverlayNavBreakpoint,
    appContentWidth,
    navbarType,
    isNavbarBlurEnabled,
    appContentLayoutNav,
    isVerticalNavCollapsed,
    footerType,
    isAppRTL,
  }
})
// !SECTION

// SECTION Init
// Fungsi ini dirancang untuk dipanggil dari dalam konteks setup komponen (misal: app.vue)
export function initConfigStore() {
  const userPreferredColorScheme = usePreferredColorScheme()
  const vuetifyTheme = useTheme()
  const configStore = useConfigStore()

  watch(
    [() => configStore.theme, userPreferredColorScheme],
    () => {
      vuetifyTheme.global.name.value = configStore.theme === 'dark'
        ? userPreferredColorScheme.value === 'dark'
          ? 'dark'
          : 'light'
        : configStore.theme
    },
  )

  onMounted(() => {
    if (configStore.theme === 'dark')
      vuetifyTheme.global.name.value = userPreferredColorScheme.value
  })
}
// !SECTION
