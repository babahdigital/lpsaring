import type { IconOptions } from 'vuetify'
import { themeConfig } from '@themeConfig'
import { createVuetify } from 'vuetify'
import { VBtn } from 'vuetify/components/VBtn'
import { mdi, aliases as mdiAliases } from 'vuetify/iconsets/mdi'
import { cookieRef } from '@/@layouts/stores/config'
import pluginDefaults from './defaults'
import { icons as iconAliases } from './icons'
import { themes } from './theme'
import '@core/scss/template/libs/vuetify/index.scss'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

function resolveInitialVuetifyTheme(userPreference: string | undefined | null): 'light' | 'dark' {
  const validThemes = Object.keys(themes)
  const defaultThemeFromConfig = themeConfig.app.theme
  if (userPreference && validThemes.includes(userPreference)) {
    return userPreference as 'light' | 'dark'
  }
  if (validThemes.includes(defaultThemeFromConfig)) {
    return defaultThemeFromConfig as 'light' | 'dark'
  }
  console.warn('Vuetify Plugin: Invalid theme configuration. Falling back to "light".')
  return 'light'
}

// Solusi utama: 
// 1. Hapus impor tipe NuxtApp yang menyebabkan circular dependency
// 2. Gunakan inferensi tipe dari defineNuxtPlugin
export default defineNuxtPlugin((nuxtApp) => {
  const userPreferredTheme = cookieRef<string>('theme', themeConfig.app.theme).value
  const initialDefaultTheme = resolveInitialVuetifyTheme(userPreferredTheme)

  const iconsConfig: IconOptions = {
    defaultSet: 'mdi',
    aliases: {
      ...mdiAliases,
      ...iconAliases,
    },
    sets: {
      mdi,
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
  
  // Return kosong untuk menghindari implicit any
  return {}
})