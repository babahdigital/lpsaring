// frontend/composables/useApiFetch.ts
import type {
  AsyncData,
  UseFetchOptions,
} from '#app'
import type { KeysOf, PickFrom } from '#app/composables/asyncData'
import type { FetchError as OFetchError } from 'ofetch'
import type { Ref } from 'vue'

import { useCookie, useFetch, useRuntimeConfig } from '#app'
import { defu } from 'defu'
import { useAuthStore } from '~/store/auth'

type FetchRequestInput = string | Request | Ref<string | Request> | (() => string | Request)

export function useApiFetch<
  ResT,
  ErrorT extends OFetchError = OFetchError,
  DataT = ResT,
  PickKeys extends KeysOf<DataT> = KeysOf<DataT>,
>(
  request: FetchRequestInput,
  options?: UseFetchOptions<ResT, DataT, PickKeys, ErrorT>,
): AsyncData<PickFrom<DataT, PickKeys>, ErrorT | null> {
  const config = useRuntimeConfig()
  const authToken = useCookie<string | null>('auth_token')
  const authStore = useAuthStore()

  // PERUBAHAN KUNCI: Logika baseURL yang berbeda untuk server dan client
  const calculatedBaseURL = import.meta.server
    ? config.internalApiBaseUrl // Gunakan URL backend langsung saat SSR (mis. http://backend:5010/api)
    : config.public.apiBaseUrl // Gunakan path relatif untuk client (mis. /api, akan di-proxy oleh Nitro)

  const defaultOptions: UseFetchOptions<ResT, DataT, PickKeys, ErrorT> = {
    baseURL: calculatedBaseURL, // Menggunakan baseURL yang sudah dihitung
    headers: {
      Accept: 'application/json',
    } as HeadersInit,

    onRequest({ options: opts }) {
      if (authToken.value) {
        const currentHeaders = new Headers(opts.headers as HeadersInit | undefined)
        currentHeaders.set('Authorization', `Bearer ${authToken.value}`)
        opts.headers = currentHeaders
      }
    },

    async onResponse({ response }) {
      if (response.status === 401) {
        if (import.meta.client) {
          await authStore.logout(true)
        }
      }
    },

    async onResponseError({ response }) {
      if (response?.status === 401) {
        if (import.meta.client) {
          await authStore.logout(true)
        }
      }
    },
  }

  const finalOptions = defu(options, defaultOptions) as UseFetchOptions<ResT, DataT, PickKeys, ErrorT>

  const result = useFetch(request, finalOptions)

  return result as AsyncData<PickFrom<DataT, PickKeys>, ErrorT | null>
}
