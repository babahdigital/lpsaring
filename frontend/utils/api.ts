// frontend/utils/api.ts

import { useCookie, useRuntimeConfig } from '#app'
import { $fetch, type FetchOptions } from 'ofetch'
import { useAuthStore } from '~/store/auth'

export const $api = $fetch.create({
  async onRequest({ options }: { options: FetchOptions }) {
    const config = useRuntimeConfig()
    options.baseURL = config.public.apiBaseUrl || '/api'

    const token = useCookie('auth_token').value
    const currentHeaders = new Headers(options.headers as HeadersInit | undefined)

    if (!currentHeaders.has('Accept')) {
      currentHeaders.set('Accept', 'application/json')
    }

    if (
      options.body
      && (options.method?.toUpperCase() === 'POST'
      || options.method?.toUpperCase() === 'PUT'
      || options.method?.toUpperCase() === 'PATCH')
    ) {
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
      const authStore = useAuthStore()

      // PERBAIKAN: Daftar path yang tidak akan memicu logout otomatis saat error 401
      const ignoredPaths = [
        '/auth/admin/login', // Gagal login admin
        '/auth/verify-otp',   // Gagal verifikasi OTP
        '/auth/logout',       // Gagal saat proses logout itu sendiri
      ]

      const isIgnoredPath = ignoredPaths.some(path => requestUrl.includes(path))

      if (!isIgnoredPath) {
        console.warn(`[API Interceptor Global] 401 pada rute terproteksi (${requestUrl}). Menjalankan logout otomatis...`)
        await authStore.logout(true)
      }
      else {
        console.warn(`[API Interceptor Global] 401 pada rute otentikasi (${requestUrl}). Logout otomatis diabaikan.`)
      }
    }
  },
})