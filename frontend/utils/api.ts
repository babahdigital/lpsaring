import { useCookie, useRuntimeConfig } from '#app'
// frontend/utils/api.ts
import { $fetch } from 'ofetch'
import { useAuthStore } from '~/store/auth' // Impor langsung

export const $api = $fetch.create({
  async onRequest({ options }) {
    const config = useRuntimeConfig()
    options.baseURL = config.public.apiBaseUrl || '/api'

    const token = useCookie('auth_token').value
    const currentHeaders = new Headers(options.headers as HeadersInit | undefined)

    // Set default Accept header jika belum ada
    if (!currentHeaders.has('Accept')) {
      currentHeaders.set('Accept', 'application/json')
    }

    // Set default Content-Type untuk metode tertentu jika body ada dan bukan FormData
    if (options.body
      && (options.method?.toUpperCase() === 'POST'
        || options.method?.toUpperCase() === 'PUT'
        || options.method?.toUpperCase() === 'PATCH')) {
      if (!currentHeaders.has('Content-Type') && !(options.body instanceof FormData)) {
        currentHeaders.set('Content-Type', 'application/json')
      }
    }

    if (token) {
      currentHeaders.set('Authorization', `Bearer ${token}`)
    }
    options.headers = currentHeaders
  },

  async onResponseError({ request, response }) {
    const requestUrl = typeof request === 'string' ? request : (request as Request).url
    console.error(`[API Global onResponseError] Path: ${requestUrl}, Status: ${response?.status}, Data:`, response?._data)

    if (import.meta.client && response?.status === 401) {
      // Panggil useAuthStore() secara langsung.
      const authStore = useAuthStore()
      console.warn('[API Interceptor Global] 401 Unauthorized. Logging out...')
      await authStore.logout(true) // Gunakan logout(true) untuk penanganan terpusat
    }
  },
})
