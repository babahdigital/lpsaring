import type { NuxtApp } from '#app'

import type { IconOptions } from 'vuetify'
import { themeConfig } from '@themeConfig'
// --- Import Konfigurasi Vuetify & Komponen ---
// Import 'IconOptions' untuk memberikan tipe eksplisit pada konfigurasi ikon
import { createVuetify } from 'vuetify'

import { VBtn } from 'vuetify/components/VBtn'

// --- Import untuk Ikon MDI ---
import { mdi, aliases as mdiAliases } from 'vuetify/iconsets/mdi'
// --- Import Konfigurasi Aplikasi & Tema ---
import { cookieRef } from '@/@layouts/stores/config'

// --- Import Konfigurasi Lokal ---
import pluginDefaults from './defaults'
import { icons as iconAliases } from './icons'
import { themes } from './theme'

// --- Import Styles ---
import '@core/scss/template/libs/vuetify/index.scss'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css' // Pastikan @mdi/font terinstal

// --- Fungsi Helper Tema (Tidak diubah) ---
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

// --- Plugin Nuxt ---
export default defineNuxtPlugin((nuxtApp: NuxtApp) => {
  const userPreferredTheme = cookieRef<string>('theme', themeConfig.app.theme).value
  const initialDefaultTheme = resolveInitialVuetifyTheme(userPreferredTheme)

  // Definisikan konfigurasi ikon dengan tipe 'IconOptions' yang eksplisit.
  // Pendekatan ini lebih aman daripada 'as any' dan membantu TypeScript memvalidasi struktur.
  const iconsConfig: IconOptions = {
    defaultSet: 'mdi',
    aliases: {
      ...mdiAliases,
      ...iconAliases, // Gabungkan alias MDI bawaan dengan alias kustom Anda
    },
    sets: {
      mdi,
    },
  }

  const vuetify = createVuetify({
    ssr: true,
    defaults: pluginDefaults,

    // Gunakan konfigurasi ikon yang sudah didefinisikan dengan tipe yang benar
    icons: iconsConfig,

    theme: {
      defaultTheme: initialDefaultTheme,
      themes,
    },

    // Alias untuk komponen Vuetify, bukan untuk ikon
    aliases: {
      IconBtn: VBtn,
    },
  })

  nuxtApp.vueApp.use(vuetify)
})
