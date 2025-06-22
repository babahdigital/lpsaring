import { ofetch } from 'ofetch'
import { useAuthStore } from '~/store/auth'
import type { Pinia } from 'pinia'

/**
 * Plugin universal untuk membuat instance $fetch yang sudah dikonfigurasi.
 * Ini menangani baseURL yang berbeda untuk server/klien dan secara otomatis
 * menyisipkan token otentikasi serta menangani error 401 (Unauthorized).
 */
export default defineNuxtPlugin((nuxtApp) => {
  const config = useRuntimeConfig()
  let authStore: ReturnType<typeof useAuthStore> | null = null

  // Fungsi helper untuk mendapatkan instance auth store dengan aman.
  const getAuthStore = () => {
    if (!authStore) {
      // Menggunakan nuxtApp.$pinia yang di-cast ke tipe Pinia untuk mengatasi masalah tipe.
      authStore = useAuthStore(nuxtApp.$pinia as Pinia)
    }
    return authStore
  }

  const apiFetch = ofetch.create({
    // Gunakan URL internal di server, dan URL publik (proxy) di klien.
    baseURL: import.meta.server
      ? config.internalApiBaseUrl
      : config.public.apiBaseUrl,

    // Interceptor yang dijalankan SEBELUM setiap permintaan.
    onRequest({ options }) {
      const store = getAuthStore()
      const token = store.token

      if (token) {
        // PERBAIKAN: Gunakan objek 'Headers' untuk memanipulasi header secara aman.
        // Ini mengatasi error tipe dan memastikan kompatibilitas.
        const headers = new Headers(options.headers)
        headers.set('Authorization', `Bearer ${token}`)
        options.headers = headers
      }
    },

    // Interceptor yang dijalankan SETELAH permintaan yang GAGAL.
    async onResponseError({ response }) {
      // Jika kita mendapatkan error 401 (Unauthorized), itu berarti token tidak valid.
      // Lakukan logout secara otomatis.
      if (response.status === 401) {
        const store = getAuthStore()
        
        // Cek apakah masih ada token di state untuk mencegah loop logout.
        if (store.token) {
            const side = import.meta.server ? 'SERVER' : 'CLIENT'
            console.warn(`[API Plugin:${side}] Menerima 401. Melakukan logout...`)
            
            // Panggil logout dari store. Redirect hanya akan terjadi di sisi klien.
            await store.logout(import.meta.client)
        }
      }
    },
  })

  // Sediakan $api untuk digunakan di seluruh aplikasi.
  nuxtApp.provide('api', apiFetch)
})