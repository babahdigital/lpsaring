// frontend/types/nuxt-app.d.ts
import type { $Fetch, NitroFetchRequest } from 'nitropack'

declare module '#app' {
  interface NuxtApp {
    $api: $Fetch<unknown, NitroFetchRequest>
  }

  export function useNuxtApp(): NuxtApp
  export function useCookie<T = any>(name: string): { value: T }
  export function navigateTo(path: string, options?: { replace?: boolean }): Promise<void> | void
  export function defineNuxtRouteMiddleware(middleware: any): any
}

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $api: $Fetch<unknown, NitroFetchRequest>
  }
}

declare global {
  interface Window {
    snap?: {
      pay: (token: string, options: {
        onSuccess: (result: { order_id: string }) => void
        onPending: (result: { order_id: string }) => void
        onError: (result: { order_id: string }) => void
        onClose: () => void
      }) => void
    }
  }
}

export {}
