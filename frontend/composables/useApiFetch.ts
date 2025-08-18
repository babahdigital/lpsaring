// frontend/composables/useApiFetch.ts - VERSI DISEMPURNAKAN

import type { KeysOf, PickFrom } from '#app/composables/asyncData'
import type { AsyncData, UseFetchOptions } from 'nuxt/app'
import type { FetchError as OFetchError } from 'ofetch'

import { useFetch, useNuxtApp } from 'nuxt/app'

interface SimpleError {
  statusCode: number | undefined
  message: string
  data: any
}

export function useApiFetch<
  ResT,
  DataT = ResT,
  PickKeys extends KeysOf<DataT> = KeysOf<DataT>,
>(
  request: string | Ref<string>,
  options: UseFetchOptions<ResT, DataT, PickKeys> = {},
): AsyncData<PickFrom<DataT, PickKeys>, SimpleError | null> {
  // Gunakan $api yang sudah disediakan oleh plugin api.ts
  const nuxtApp = useNuxtApp()

  return useFetch(request, {
    ...options,
    $fetch: nuxtApp.$api,

    // --- [PENAMBAHAN KUNCI DI SINI] ---
    // 'transformError' akan mengubah objek error yang kompleks menjadi objek sederhana
    // sebelum Nuxt mencoba untuk men-serialize nya. Ini akan menghilangkan warning DevalueError.
    transformError: (error: OFetchError): SimpleError => {
      return {
        statusCode: error.statusCode,
        message: error.data?.message || error.statusMessage || 'An unexpected error occurred.',
        data: error.data,
      }
    },
  } as any) as AsyncData<PickFrom<DataT, PickKeys>, SimpleError | null>
}
