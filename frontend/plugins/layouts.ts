import type { NuxtApp } from '#app'
import { createLayouts } from '@layouts'
import { layoutConfig } from '@themeConfig'
import '@layouts/styles/index.scss'

// Perbaikan type casting
export default defineNuxtPlugin((nuxtApp: NuxtApp) => {
  nuxtApp.vueApp.use(createLayouts(layoutConfig as unknown as Parameters<typeof createLayouts>[0]))
})
