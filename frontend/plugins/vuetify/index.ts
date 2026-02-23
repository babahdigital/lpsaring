import { deepMerge } from '@antfu/utils'
import { resolveVuetifyTheme } from '@core/utils/vuetify'
import { cookieRef } from '@layouts/stores/config'
import { themeConfig } from '@themeConfig'
import { createVuetify } from 'vuetify'
import { VBtn } from 'vuetify/components/VBtn'
import defaults from './defaults'
import { icons } from './icons'
import { staticPrimaryColor, staticPrimaryDarkenColor, themes } from './theme'
import '@core/scss/template/libs/vuetify/index.scss'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

export default defineNuxtPlugin((nuxtApp) => {
  const cookieThemeValues = {
    defaultTheme: resolveVuetifyTheme(themeConfig.app.theme),
    themes: {
      light: {
        colors: {
          'primary': cookieRef('lightThemePrimaryColor', staticPrimaryColor).value,
          'primary-darken-1': cookieRef('lightThemePrimaryDarkenColor', staticPrimaryDarkenColor).value,
        },
      },
      dark: {
        colors: {
          'primary': cookieRef('darkThemePrimaryColor', staticPrimaryColor).value,
          'primary-darken-1': cookieRef('darkThemePrimaryDarkenColor', staticPrimaryDarkenColor).value,
        },
      },
    },
  }

  const optionTheme = deepMerge({ themes }, cookieThemeValues)

  const vuetify = createVuetify({
    aliases: {
      IconBtn: VBtn,
    },
    defaults,
    icons,
    theme: optionTheme,
  })

  nuxtApp.vueApp.use(vuetify)
})
