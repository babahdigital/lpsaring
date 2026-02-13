import type { Pinia } from 'pinia'
import { ofetch } from 'ofetch'
import { useAuthStore } from '~/store/auth'
import { navigateTo, useRequestHeaders, useRoute } from '#app'

/**
 * Plugin universal untuk membuat instance $fetch yang sudah dikonfigurasi.
 * Ini menangani baseURL yang berbeda untuk server/klien dan memastikan cookie
 * otentikasi terkirim serta menangani error 401 (Unauthorized).
 */
export default defineNuxtPlugin((nuxtApp) => {
  const config = useRuntimeConfig()
  let authStore: ReturnType<typeof useAuthStore> | null = null
  let lastUnauthorizedAt = 0
  const unauthorizedCooldownMs = 5000

  const getRequestPath = (request: Request | string): string => {
    if (typeof request === 'string')
      return request
    if (request instanceof Request)
      return request.url
    return ''
  }

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

    credentials: 'include',

    // Interceptor yang dijalankan SEBELUM setiap permintaan.
    onRequest({ options }) {
      if (import.meta.server) {
        const headers = new Headers(options.headers)
        const requestHeaders = useRequestHeaders(['cookie'])
        if (requestHeaders.cookie) {
          headers.set('cookie', requestHeaders.cookie)
        }
        options.headers = headers
      }
      const devBypassToken = config.public.devBypassToken
      if (devBypassToken) {
        const headers = new Headers(options.headers)
        headers.set('X-Dev-Bypass', devBypassToken)
        options.headers = headers
      }
    },

    // Interceptor yang dijalankan SETELAH permintaan yang GAGAL.
    async onResponseError({ request, response }) {
      // Jika kita mendapatkan error 401 (Unauthorized), itu berarti token tidak valid.
      // Lakukan logout secara otomatis.
      if (response.status === 401) {
        const requestPath = getRequestPath(request)
        const isAuthSessionRequest = requestPath.includes('/auth/me')
          || requestPath.includes('/auth/logout')
          || requestPath.includes('/auth/session/consume')

        if (!isAuthSessionRequest)
          return

        const now = Date.now()
        if (now - lastUnauthorizedAt < unauthorizedCooldownMs)
          return
        lastUnauthorizedAt = now
        const store = getAuthStore()

        if (store.currentUser != null) {
          store.clearSession(401)
          if (import.meta.client) {
            const route = useRoute()
            const path = route.path
            const fullPath = route.fullPath
            const isGuestPath = path === '/login'
              || path === '/admin'
              || path === '/admin/login'
              || path.startsWith('/session/consume')

            if (!isGuestPath) {
              const nextTarget = encodeURIComponent(fullPath)
              const redirectPath = path.startsWith('/admin')
                ? `/admin?redirect=${nextTarget}`
                : `/login?redirect=${nextTarget}`
              await navigateTo(redirectPath, { replace: true })
            }
          }
        }
      }

      if (response.status === 403) {
        const store = getAuthStore()
        const payload = (response as any)?._data ?? {}
        const statusFromPayload = typeof payload.status === 'string'
          ? payload.status
          : null
        const sigFromPayload = typeof payload.status_token === 'string'
          ? payload.status_token
          : null
        if (statusFromPayload && sigFromPayload) {
          store.setStatusRedirect(statusFromPayload, sigFromPayload)
        }
        const errorText = payload.error ?? payload.message ?? ''
        const status = statusFromPayload ?? store.getAccessStatusFromError(errorText)
        if (status === 'blocked' || status === 'inactive') {
          await store.logout(false)
          if (import.meta.client) {
            const route = useRoute()
            const isAdminRoute = route.path.startsWith('/admin')
            const redirectPath = store.getStatusRedirectPath('login')
              ?? store.getRedirectPathForStatus(status, 'login')
            await navigateTo(redirectPath ?? (isAdminRoute ? '/admin' : '/login'), { replace: true })
          }
        }
      }
    },
  })

  // Sediakan $api untuk digunakan di seluruh aplikasi.
  nuxtApp.provide('api', apiFetch)
})
