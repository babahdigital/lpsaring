declare module 'vue3-apexcharts' {
  import type { DefineComponent } from 'vue'

  interface ApexChartsProps {
    type?: string
    series?: any[]
    options?: any
    width?: string | number
    height?: string | number
  }

  const VueApexCharts: DefineComponent<ApexChartsProps>
  export default VueApexCharts
}
