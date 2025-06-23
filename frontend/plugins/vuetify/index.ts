// frontend/plugins/vuetify/index.ts

import type { IconOptions } from 'vuetify'
import { themeConfig } from '@themeConfig'
import { createVuetify } from 'vuetify'
import { VBtn } from 'vuetify/components/VBtn'
import { mdi, aliases as mdiAliases } from 'vuetify/iconsets/mdi'
import { cookieRef } from '@/@layouts/stores/config'
import pluginDefaults from './defaults'
// --- Impor adapter Iconify yang baru dibuat ---
import IconifyVuetifyAdapter from './iconify-adapter'
import { icons as iconAliases } from './icons'
import { themes } from './theme'
import '@core/scss/template/libs/vuetify/index.scss'
import 'vuetify/styles'

import '@mdi/font/css/materialdesignicons.css'

function resolveInitialVuetifyTheme(userPreference: string | undefined | null): 'light' | 'dark' {
  const validThemes = Object.keys(themes)
  const defaultThemeFromConfig = themeConfig.app.theme
  if (userPreference != null && validThemes.includes(userPreference)) {
    return userPreference as 'light' | 'dark'
  }
  if (validThemes.includes(defaultThemeFromConfig)) {
    return defaultThemeFromConfig as 'light' | 'dark'
  }
  console.warn('Vuetify Plugin: Invalid theme configuration. Falling back to "light".')
  return 'light'
}

export default defineNuxtPlugin((nuxtApp) => {
  const userPreferredTheme = cookieRef<string>('theme', themeConfig.app.theme).value
  const initialDefaultTheme = resolveInitialVuetifyTheme(userPreferredTheme)

  const iconsConfig: IconOptions = {
    defaultSet: 'mdi', // Tetap 'tabler' atau 'mdi' sesuai preferensi Anda
    aliases: {
      ...mdiAliases,
      ...iconAliases,
    },
    sets: {
      mdi,
      // --- Gunakan adapter yang sudah dibuat ---
      tabler: IconifyVuetifyAdapter, // Gunakan objek adapter langsung
    },
  }

  const vuetify = createVuetify({
    ssr: true,
    defaults: pluginDefaults,
    icons: iconsConfig,
    theme: {
      defaultTheme: initialDefaultTheme,
      themes,
    },
    aliases: {
      IconBtn: VBtn,
    },
  })

  nuxtApp.vueApp.use(vuetify)

  return {}
})