// frontend/types/nuxt-app.d.ts
import type { $Fetch } from 'ofetch'

declare module '#app' {
  interface NuxtApp {
    /**
     * Instance $fetch kustom dengan interceptor dan baseURL terkonfigurasi.
     */
    $api: $Fetch
  }
}

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    /**
     * Instance $fetch kustom dengan interceptor dan baseURL terkonfigurasi.
     */
    $api: $Fetch
  }
}

export {} // Pastikan file ini diperlakukan sebagai module.
