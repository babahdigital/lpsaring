// plugins/01.vuetify.client.ts
import { useCookie } from '#app'
import { computed, watch } from 'vue'
import { createVuetify } from 'vuetify'
import { VBtn } from 'vuetify/components/VBtn'

import pluginDefaults from '~/plugins/vuetify/defaults'
import IconifyVuetifyAdapter from '~/plugins/vuetify/iconify-adapter'
import { icons as iconAliases } from '~/plugins/vuetify/icons'
import { themes } from '~/plugins/vuetify/theme'
import { Theme } from '~/types/enums'
import '@core/scss/template/libs/vuetify/index.scss'
import 'vuetify/styles'

export default defineNuxtPlugin((nuxtApp) => {
  const themeCookie = useCookie<Theme>('app-theme', {
    default: () => Theme.System,
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const effectiveTheme = computed(() => {
    if (themeCookie.value !== Theme.System)
      return themeCookie.value

    if (import.meta.client) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
        ? Theme.Dark
        : Theme.Light
    }
    return Theme.Dark
  })

  const vuetify = createVuetify({
    ssr: true,
    defaults: pluginDefaults,
    icons: {
      defaultSet: 'iconify',
      aliases: { ...iconAliases },
      sets: { iconify: IconifyVuetifyAdapter },
    },
    theme: {
      defaultTheme: effectiveTheme.value,
      themes,
    },
    aliases: {
      IconBtn: VBtn,
    },
  })

  nuxtApp.vueApp.use(vuetify)

  watch(
    effectiveTheme,
    (newTheme) => {
      if (vuetify.theme)
        vuetify.theme.global.name.value = newTheme
    },
  )
})
