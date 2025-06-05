import type { NuxtApp } from '#app'
// frontend/plugins/apexcharts.client.ts
import VueApexCharts from 'vue3-apexcharts'

export default defineNuxtPlugin((nuxtApp: NuxtApp) => {
  nuxtApp.vueApp.component('apexchart', VueApexCharts)
})
