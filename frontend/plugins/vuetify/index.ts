import type { NuxtApp } from '#app'
// --- Import Konfigurasi Aplikasi & Tema ---
import { themeConfig } from '@themeConfig'
// frontend/plugins/vuetify/index.ts (Workaround TS2322 dengan 'as any')
import { createVuetify } from 'vuetify'
// TIDAK PERLU import IconAliases lagi

import { VBtn } from 'vuetify/components/VBtn'
// --- PENTING: Import untuk Ikon MDI ---
import { mdi, aliases as mdiAliases } from 'vuetify/iconsets/mdi'
import { cookieRef } from '@/@layouts/stores/config'

// --- Import Konfigurasi Vuetify ---
import pluginDefaults from './defaults'
import { icons as iconAliases } from './icons'

import { themes } from './theme'
import '@mdi/font/css/materialdesignicons.css' // Pastikan @mdi/font terinstal!

// --- Import Styles ---
import '@core/scss/template/libs/vuetify/index.scss'
import 'vuetify/styles'

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

  // --- Gabungkan Alias Ikon Terlebih Dahulu ---
  const combinedAliases = {
    ...mdiAliases,
    ...iconAliases,
  } as any // <-- Gunakan 'as any' untuk bypass cek tipe TS yang bermasalah
  // --- Akhir Penggabungan Alias ---

  const vuetify = createVuetify({
    ssr: true,
    defaults: pluginDefaults,

    // --- Gunakan Alias yang Sudah Digabung ---
    icons: {
      defaultSet: 'mdi',
      // Karena combinedAliases sudah 'any', TS tidak akan complain di sini
      aliases: combinedAliases,
      sets: {
        mdi,
      },
    },
    // --- Akhir Konfigurasi Ikon ---

    theme: {
      defaultTheme: initialDefaultTheme,
      themes,
    },

    aliases: { // Alias komponen kustom Anda
      IconBtn: VBtn,
    },
  })

  nuxtApp.vueApp.use(vuetify)
})
