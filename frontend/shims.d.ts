declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  // Perbaikan: ganti {} dengan object atau Record<string, unknown>
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
