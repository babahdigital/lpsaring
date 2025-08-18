// types/nuxt.d.ts
// Ini adalah satu-satunya file deklarasi yang Anda butuhkan untuk plugin.

import type { $Fetch } from 'ofetch'
import type { Pinia } from 'pinia'
import type { PersistedStateOptions } from 'pinia-plugin-persistedstate'
import type { RouteLocationRaw } from 'vue-router'

declare module '#app' {
  /**
   * Menambahkan tipe untuk properti yang di-inject ke instance nuxtApp.
   * Ini adalah deklarasi terpenting agar `useNuxtApp()` menjadi type-safe.
   */
  interface NuxtApp {
    $api: $Fetch
    $pinia: Pinia
  }

  /**
   * Menambahkan tipe kustom untuk properti 'meta' di dalam rute.
   */
  interface PageMeta {
    action?: string
    subject?: string
    layoutWrapperClasses?: string
    navActiveLink?: RouteLocationRaw
    unauthenticatedOnly?: boolean
    public?: boolean
  }
}

declare module '@vue/runtime-core' {
  /**
   * Menambahkan tipe untuk properti yang bisa diakses via `this.$api`
   * di dalam komponen yang menggunakan Options API.
   */
  interface ComponentCustomProperties {
    $api: $Fetch
  }
}

// [PENAMBAHAN] Blok ini memberitahu TypeScript tentang opsi 'persist'
// yang ditambahkan oleh pinia-plugin-persistedstate.
// Menempatkannya di sini menyatukan semua augmentasi tipe dalam satu file.
declare module 'pinia' {
  // eslint-disable-next-line unused-imports/no-unused-vars
  export interface DefineStoreOptions<Id, S, G, A> {
    persist?: boolean | PersistedStateOptions
  }
}

// Baris ini penting untuk memastikan file ini diperlakukan sebagai sebuah modul.
export {}
