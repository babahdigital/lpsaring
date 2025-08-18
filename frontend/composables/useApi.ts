import type { UseFetchOptions } from 'nuxt/app'
import type { MaybeRefOrGetter } from 'vue'

import { useStorage } from '@vueuse/core'
import { useCookie } from '#imports'
import { defu } from 'defu'
import { useFetch, useRuntimeConfig } from 'nuxt/app'
import { toValue } from 'vue'

// Extend typing to allow baseURL (Nuxt runtime supports it even if generic signature narrowed)
type ExtendedFetchOptions<T> = UseFetchOptions<T> & { baseURL?: string, headers?: Record<string, string> }

export const useApi: typeof useFetch = <T>(url: MaybeRefOrGetter<string>, options: ExtendedFetchOptions<T> = {}) => {
  const config = useRuntimeConfig()

  // Ambil token (cookie dulu jika ada, fallback localStorage)
  const authTokenCookie = useCookie<string | null>('app_token')
  const tokenLocal = useStorage<string | null>('app_token_local_copy', null)
  const accessToken = authTokenCookie.value || tokenLocal.value || null

  // Normalisasi URL penuh kalau baseURL tidak diterima oleh tipe
  // (Tetap simpan baseURL agar tetap future-proof)
  const base = config.public.apiBaseUrl?.replace(/\/$/, '') || ''
  const path = toValue(url)
  const fullUrl = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? '' : '/'}${path}`

  const defaults: ExtendedFetchOptions<T> = {
    baseURL: undefined, // tidak wajib, sudah digabung manual di fullUrl
    key: fullUrl, // cache key unik
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    // mode SPA: hindari server prefetch
    server: false,
  }

  const params = defu(options, defaults) as ExtendedFetchOptions<T>

  return useFetch(fullUrl, params as UseFetchOptions<T>)
}
