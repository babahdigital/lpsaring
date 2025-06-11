// frontend/plugins/api.ts
import type { FetchContext, FetchResponse } from 'ofetch'
import {
  defineNuxtPlugin,
  useRoute,
  useRuntimeConfig,
  createError,
} from '#app'
import { Headers, ofetch } from 'ofetch'
import { useAuthStore } from '~/store/auth'
import { useMaintenanceStore } from '@/store/maintenance'

export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig()
  const route = useRoute()
  const authStore = useAuthStore()

  const effectiveBaseURL = import.meta.server
    ? runtimeConfig.internalApiBaseUrl
    : runtimeConfig.public.apiBaseUrl;

  const apiClient = ofetch.create({
    baseURL: effectiveBaseURL,

    async onRequest(context: FetchContext) {
      const token = authStore.token
      const currentHeaders = new Headers(context.options.headers as HeadersInit)

      if (token) {
        currentHeaders.set('Authorization', `Bearer ${token}`)
      }
      if (!currentHeaders.has('Accept')) {
        currentHeaders.set('Accept', 'application/json')
      }
      if (context.options.body
        && (['POST', 'PUT', 'PATCH'].includes(context.options.method?.toUpperCase() || ''))) {
        if (!currentHeaders.has('Content-Type') && !(context.options.body instanceof FormData)) {
          currentHeaders.set('Content-Type', 'application/json')
        }
      }
      context.options.headers = currentHeaders
    },

    async onResponseError(context: FetchContext) {
      const { request, response } = context as { request: any, response?: FetchResponse<any> }

      // --- PERBAIKAN: Hanya log error jika status BUKAN 503 ---
      if (response?.status !== 503) {
        console.error(
          `[API Plugin onResponseError] Request: ${request}, Status: ${response?.status}, Data:`,
          response?._data,
        )
      }
      // ----------------------------------------------------
      
      if (response?.status === 503) {
        const maintenanceStore = useMaintenanceStore()
        const message = response?._data?.message || 'Aplikasi sedang dalam perbaikan.'
        
        // Perbarui status maintenance tanpa redirect
        maintenanceStore.setMaintenanceStatus(true, message)
        
        // Tidak perlu throw error agar middleware bisa menangani
        return
      }
      
      if (import.meta.client && response?.status === 401) {
        const requestUrl = typeof request === 'string' ? request : (request as Request).url
        if (!requestUrl.includes('/auth/')) {
           await authStore.logout(true)
        }
      }

      if (response) {
        throw response._data || new Error(`HTTP error ${response.status} on ${request}`)
      }
      else {
        throw new Error(`Network error or no response on ${request}`)
      }
    },
  })

  return {
    provide: {
      api: apiClient,
    },
  }
})