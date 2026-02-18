declare module 'vite-plugin-vuetify' {
  import type { Plugin } from 'vite'
  import type { Options } from '@vuetify/loader-shared'

  function vuetifyPlugin(options?: Options): Plugin[]

  namespace vuetifyPlugin {
    const transformAssetUrls: Record<string, string[]>
  }

  export = vuetifyPlugin
  export default vuetifyPlugin
}
