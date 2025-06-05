// frontend/plugins/api.ts
import type { FetchContext } from 'ofetch'
import {
  defineNuxtPlugin,
  navigateTo, // Impor navigateTo
  useRoute,
  useRuntimeConfig,
} from '#app'
import { Headers, ofetch } from 'ofetch'
import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig()
  const route = useRoute() // Gunakan useRoute() untuk informasi rute
  const authStore = useAuthStore() // Panggil langsung tanpa argumen

  let effectiveBaseURL: string
  const configuredApiBaseUrl = runtimeConfig.public.apiBaseUrl || '/api'

  if (import.meta.server) {
    if (configuredApiBaseUrl.startsWith('http://') || configuredApiBaseUrl.startsWith('https://')) {
      effectiveBaseURL = configuredApiBaseUrl
    }
    else {
      const nginxInternalHost = process.env.NGINX_INTERNAL_HOST || 'http://nginx'
      effectiveBaseURL = `${nginxInternalHost}${configuredApiBaseUrl.startsWith('/') ? configuredApiBaseUrl : `/${configuredApiBaseUrl}`}`
    }
  }
  else {
    effectiveBaseURL = configuredApiBaseUrl
  }

  const apiClient = ofetch.create({
    baseURL: effectiveBaseURL,

    async onRequest(context: FetchContext) {
      const token = authStore.token

      if (!context.options.headers) {
        context.options.headers = new Headers()
      }
      const currentHeaders = new Headers(context.options.headers as HeadersInit)

      if (token) {
        currentHeaders.set('Authorization', `Bearer ${token}`)
      }
      if (!currentHeaders.has('Accept')) {
        currentHeaders.set('Accept', 'application/json')
      }
      if (context.options.body
        && (context.options.method?.toUpperCase() === 'POST'
          || context.options.method?.toUpperCase() === 'PUT'
          || context.options.method?.toUpperCase() === 'PATCH')) {
        if (!currentHeaders.has('Content-Type') && !(context.options.body instanceof FormData)) {
          currentHeaders.set('Content-Type', 'application/json')
        }
      }
      context.options.headers = currentHeaders
    },

    async onResponseError(context: FetchContext) {
      const { request, response } = context
      const requestUrl = typeof request === 'string' ? request : (request as Request).url

      console.error(
        `[API Plugin onResponseError] Request: ${requestUrl}, Status: ${response?.status}, Data:`,
        response?._data,
      )

      if (import.meta.client && response?.status === 401) {
        const currentPath = route.path // Variabel digunakan di sini
        const isOtpVerification = requestUrl.includes('/auth/verify-otp') // Variabel digunakan di sini

        console.warn(`[API Plugin Interceptor] 401 Unauthorized terdeteksi pada ${requestUrl}.`)

        // Mengembalikan logika lama Anda untuk penanganan 401 yang lebih detail
        if (isOtpVerification) {
          // Jika error 401 terjadi pada saat verifikasi OTP,
          // panggil logout(false) agar tidak ada redirect otomatis dari store.
          // Halaman OTP/login mungkin perlu menampilkan pesan error spesifik dari authStore.getError.
          await authStore.logout(false)
          // Pesan error spesifik untuk OTP gagal biasanya sudah di-set oleh action verifyOtp di authStore.
        }
        else {
          // Untuk error 401 lainnya (misalnya token kedaluwarsa di endpoint lain)
          await authStore.logout(false) // Logout state pengguna tanpa redirect dari store
          // Set pesan error default jika belum ada error lain yang lebih spesifik dari proses logout
          if (!authStore.getError) {
            authStore.setError('Sesi Anda telah berakhir atau tidak valid. Silakan login kembali.')
          }
          authStore.setMessage('') // Bersihkan pesan sukses jika ada
        }

        // Lakukan redirect ke halaman login jika pengguna tidak sedang di halaman login
        if (currentPath !== '/login') {
          // Pertimbangkan untuk menambahkan query 'message' jika ingin menampilkan pesan di halaman login
          // Contoh: query: { message: 'session_expired' }
          await navigateTo('/login', { replace: true })
        }
        // Tidak melempar error 401 lebih lanjut karena sudah ditangani (logout dan redirect)
        return // Hentikan eksekusi lebih lanjut untuk error 401
      }

      // Untuk error selain 401, atau jika tidak di sisi klien, atau jika tidak ada response
      if (response) {
        // Lempar error agar bisa ditangkap oleh pemanggil ($api atau useApiFetch)
        throw response._data || new Error(`HTTP error ${response.status} on ${requestUrl}`)
      }
      else {
        // Jika tidak ada response sama sekali (misalnya, masalah jaringan)
        throw new Error(`Network error or no response on ${requestUrl}`)
      }
    },
  })

  return {
    provide: {
      api: apiClient,
    },
  }
})
