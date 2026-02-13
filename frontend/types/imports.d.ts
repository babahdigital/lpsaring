declare module '#imports' {
  import type { Pinia } from 'pinia'

  export const usePinia: () => Pinia
  export const definePageMeta: (meta: any) => void
  // Tambahkan composable lain sesuai kebutuhan
}

export {}
