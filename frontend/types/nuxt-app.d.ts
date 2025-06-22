// frontend/types/nuxt-app.d.ts
import type { $Fetch, NitroFetchRequest } from 'nitropack'

declare module '#app' {
  interface NuxtApp {
    $api: $Fetch<unknown, NitroFetchRequest>
  }
}

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $api: $Fetch<unknown, NitroFetchRequest>
  }
}

export {}