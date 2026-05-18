import type { Pinia } from 'pinia'
import { ofetch } from 'ofetch'
import { useAuthStore } from '~/store/auth'
import { navigateTo, useNuxtApp, useRequestHeaders } from '#app'

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function')
    return globalThis.crypto.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

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
      const headers = new Headers(options.headers)

      if (!headers.has('X-Request-ID')) {
        if (import.meta.server) {
          const requestHeaders = useRequestHeaders(['x-request-id'])
          const incomingRequestId = requestHeaders['x-request-id']
          if (typeof incomingRequestId === 'string' && incomingRequestId.trim() !== '')
            headers.set('X-Request-ID', incomingRequestId)
          else
            headers.set('X-Request-ID', createRequestId())
        }
        else {
          headers.set('X-Request-ID', createRequestId())
        }
      }

      if (import.meta.server) {
        const requestHeaders = useRequestHeaders(['cookie'])
        if (requestHeaders.cookie) {
          headers.set('cookie', requestHeaders.cookie)
        }
      }
      const devBypassToken = config.public.devBypassToken
      if (devBypassToken) {
        headers.set('X-Dev-Bypass', devBypassToken)
      }

      options.headers = headers
    },

    // Interceptor yang dijalankan SETELAH permintaan yang GAGAL.
    async onResponseError({ request, response }) {
      // H-2 fix: useRoute() di interceptor (executed at request-time, bukan setup-time)
      // tidak reliable di SSR/worker context. Gunakan $router.currentRoute.value via
      // useNuxtApp() yang selalu ter-bound.
      const getCurrentRoute = () => {
        try {
          return useNuxtApp().$router.currentRoute.value
        }
        catch {
          return null
        }
      }

      // Jika kita mendapatkan error 401 (Unauthorized), itu berarti token tidak valid.
      // Lakukan logout secara otomatis.
      if (response.status === 401) {
        const requestPath = getRequestPath(request)
        const isAuthSessionRequest = requestPath.includes('/auth/me')
          || requestPath.includes('/auth/logout')
          || requestPath.includes('/auth/session/consume')

        // H-1 fix: cek cooldown DULU, tapi JANGAN set lastUnauthorizedAt sebelum
        // menentukan action (kasus dimana store.currentUser == null tidak boleh
        // memakan slot cooldown — biarkan 401 berikutnya yang punya action eligible).
        const now = Date.now()
        if (now - lastUnauthorizedAt < unauthorizedCooldownMs)
          return
        const store = getAuthStore()

        if (store.currentUser != null) {
          // Sekarang baru set cooldown — karena kita benar-benar akan ambil action.
          lastUnauthorizedAt = now
          // SECURITY FIX: Always logout on 401, even for non-auth requests
          // This prevents silent failures where user thinks they're logged in but API calls fail
          store.clearSession(401)

          if (!isAuthSessionRequest && import.meta.dev) {
            console.warn('API 401 Unauthorized: Session expired on non-auth endpoint. Redirecting to login.')
          }
          if (import.meta.client) {
            const route = getCurrentRoute()
            const path = route?.path ?? '/'
            const fullPath = route?.fullPath ?? path
            // L-C4: tambah `/captive/*` dan `/login/hotspot-required` ke guest path.
            // Sebelumnya: user di-kick mid-flow saat token belum siap.
            const isGuestPath = path === '/login'
              || path === '/admin'
              || path === '/admin/login'
              || path.startsWith('/session/consume')
              || path.startsWith('/captive/')
              || path.startsWith('/login/hotspot-required')
              || path.startsWith('/login/')

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
            const route = getCurrentRoute()
            const isAdminRoute = (route?.path ?? '').startsWith('/admin')
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
