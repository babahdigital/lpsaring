// frontend/composables/useApiFetch.ts
import type {
  AsyncData,
  UseFetchOptions,
} from '#app'
import type { KeysOf, PickFrom } from '#app/composables/asyncData'
import type { FetchError as OFetchError, FetchResponse } from 'ofetch'
import type { Ref } from 'vue'

import { useCookie, useFetch, useRuntimeConfig, useRoute, navigateTo } from '#app'
import { defu } from 'defu'
import { useAuthStore } from '~/store/auth'
import { useMaintenanceStore } from '@/store/maintenance'

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
  const route = useRoute()

  const calculatedBaseURL = import.meta.server
    ? config.internalApiBaseUrl
    : config.public.apiBaseUrl

  const defaultOptions: UseFetchOptions<ResT, DataT, PickKeys, ErrorT> = {
    baseURL: calculatedBaseURL,
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

    onResponseError({ request, response, error }) {
      if (response?.status === 503) {
        const maintenanceStore = useMaintenanceStore()
        const message = response?._data?.message || 'Aplikasi sedang dalam perbaikan.'
        
        // --- PERBAIKAN: Gunakan nama fungsi yang benar ---
        maintenanceStore.setMaintenanceStatus(true, message)
        
        if (route.path !== '/maintenance') {
          navigateTo('/maintenance')
        }
        return
      }

      if (response?.status === 401 && import.meta.client) {
        console.warn(`[useApiFetch Interceptor] 401 Unauthorized terdeteksi pada ${request}.`)
        authStore.logout(true)
      }
    },
  }

  const finalOptions = defu(options, defaultOptions) as UseFetchOptions<ResT, DataT, PickKeys, ErrorT>

  const result = useFetch(request, finalOptions)

  return result as AsyncData<PickFrom<DataT, PickKeys>, ErrorT | null>
}