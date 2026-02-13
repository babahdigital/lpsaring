declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>
  export default component
}

declare module 'vue-prism-component' {
  import type { ComponentOptions } from 'vue'

  const component: ComponentOptions
  export default component
}

declare module 'vue-shepherd'
declare module '@videojs-player/vue'

declare module '*.svg?raw' {
  const content: string
  export default content
}

declare module '*.svg' {
  const content: string
  export default content
}

declare module 'vuetify'
declare module 'vuetify/styles'

declare module 'vuetify/labs/VDataTable' {
  export const VDataTableServer: any
  export type VDataTableServer = any
}

declare module 'vuetify/components' {
  export const VForm: any
  export const VDataTableServer: any
  export type VDataTableServer = any
}

declare module '@casl/vue'

declare module 'vue3-apexcharts'
