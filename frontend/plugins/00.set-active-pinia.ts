// plugins/00.set-active-pinia.ts
import { setActivePinia } from 'pinia'

export default defineNuxtPlugin((nuxtApp) => {
  // Nuxt 4 + @pinia/nuxt sudah menyuntikkan instansinya di sini
  // Properti diperkenalkan sebagai 'pinia' (server) dan '$pinia' (client legacy)
  const pinia = (nuxtApp as any).pinia ?? (nuxtApp as any).$pinia
  if (pinia)
    setActivePinia(pinia)
})
