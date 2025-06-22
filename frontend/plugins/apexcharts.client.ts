/**
 * Plugin sisi klien untuk mendaftarkan komponen VueApexCharts secara global.
 * Ini memungkinkan penggunaan komponen <apexchart> di seluruh aplikasi
 * tanpa perlu melakukan impor manual di setiap halaman.
 * * @see https://apexcharts.com/docs/vue-charts/
 */
import VueApexCharts from 'vue3-apexcharts'
import { defineNuxtPlugin } from '#app'

export default defineNuxtPlugin((nuxtApp) => {
  // 1. Mendaftarkan komponen 'apexchart' ke dalam aplikasi Vue.
  //    Parameter pertama adalah nama tag HTML kustom yang akan digunakan (misal, <apexchart>).
  //    Parameter kedua adalah komponen yang sebenarnya dari pustaka.
  nuxtApp.vueApp.component('apexchart', VueApexCharts)
})