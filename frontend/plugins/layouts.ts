// frontend/plugins/layouts.ts
import { createLayouts } from '@layouts'
import { layoutConfig } from '@themeConfig'
import '@layouts/styles/index.scss'

// Dijalankan terakhir untuk memastikan semua properti nuxtApp sudah ada
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(createLayouts(layoutConfig as any))
})
