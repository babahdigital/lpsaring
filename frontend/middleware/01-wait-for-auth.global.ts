// middleware/01-wait-for-auth.global.ts

import { useNuxtApp } from '#app'
import { watch } from 'vue'

import { useAuthStore } from '~/store/auth'

/**
 * Middleware ini memiliki SATU tugas: memastikan pengecekan autentikasi awal selesai
 * sebelum middleware lain yang bergantung pada status login dijalankan.
 * Ini mencegah kondisi "race condition" di mana middleware redirect berjalan
 * sebelum kita tahu apakah pengguna sudah login atau belum.
 */
export default defineNuxtRouteMiddleware(async () => {
  const nuxtApp = useNuxtApp()
  const authStore = useAuthStore(nuxtApp.$pinia)

  // Jika pengecekan dari plugin init.client.ts belum selesai, tunggu di sini.
  if (!authStore.isAuthCheckDone) {
    await new Promise<void>((resolve) => {
      const unwatch = watch(() => authStore.isAuthCheckDone, (isDone) => {
        if (isDone) {
          unwatch()
          resolve()
        }
      })
    })
  }
})
