import { defineNuxtPlugin } from '#app'
import { defineAsyncComponent, h } from 'vue'

/**
 * Plugin sisi klien untuk mendaftarkan komponen VueApexCharts secara global.
 * Ini memungkinkan penggunaan komponen <apexchart> di seluruh aplikasi
 * tanpa perlu melakukan impor manual di setiap halaman.
 * @see https://apexcharts.com/docs/vue-charts/
 */
const AsyncApexChart = defineAsyncComponent(() =>
  import('vue3-apexcharts')
    .then(mod => mod.default)
    .catch((err) => {
      console.warn(`Gagal memuat VueApexCharts. Error: ${err.message}`)
      return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
    }),
)

export default defineNuxtPlugin((nuxtApp) => {
  // 1. Mendaftarkan komponen 'apexchart' ke dalam aplikasi Vue.
  //    Parameter pertama adalah nama tag HTML kustom yang akan digunakan (misal, <apexchart>).
  //    Parameter kedua adalah komponen async untuk memuat chart saat dibutuhkan.
  nuxtApp.vueApp.component('apexchart', AsyncApexChart)
})
