import type { AsyncData, UseFetchOptions } from '#app'
import type { KeysOf, PickFrom } from '#app/composables/asyncData'
import type { FetchError as OFetchError } from 'ofetch'
import { useFetch } from '#app'

/**
 * Composable wrapper di sekitar useFetch yang secara otomatis menggunakan
 * instance $api yang sudah dikonfigurasi dari plugin kita.
 * Ini memastikan semua panggilan API yang dibuat dengan useApiFetch akan
 * secara otomatis memiliki token otentikasi dan penanganan error terpusat.
 */
export function useApiFetch<
  ResT,
  ErrorT extends OFetchError = OFetchError,
  DataT = ResT,
  PickKeys extends KeysOf<DataT> = KeysOf<DataT>,
  DefaultT = DataT,
>(
  request: string | Ref<string>,
  options: UseFetchOptions<ResT, DataT, PickKeys, DefaultT> = {},
): AsyncData<PickFrom<DataT, PickKeys> | DefaultT, ErrorT | null> {
  // Gunakan $api yang sudah disediakan oleh plugin api.ts
  // Opsi seperti baseURL dan interceptor sudah ditangani di sana.
  // Cukup teruskan opsi spesifik dari komponen.
  return useFetch(request, {
    ...options,
    $fetch: useNuxtApp().$api,
  }) as AsyncData<PickFrom<DataT, PickKeys>, ErrorT | null>
}
