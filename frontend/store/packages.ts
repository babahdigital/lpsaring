// frontend/store/packages.ts
import type { Package } from '~/types/package'
import { useNuxtApp } from '#app'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

interface PackagesApiResponse {
  success: boolean
  data: Package[]
  message?: string
}

export const usePackageStore = defineStore('packages', () => {
  const packages = ref<Package[]>([])
  const isLoading = ref<boolean>(false) // Default false, set true saat fetch dimulai
  const error = ref<string | null>(null)
  const { $api } = useNuxtApp() // Inisialisasi sekali

  const getPackageById = computed(() => {
    return (id: string): Package | undefined => packages.value.find(pkg => pkg.id === id)
  })

  const activePackagesCount = computed<number>(() => {
    return packages.value.filter(pkg => pkg.is_active).length
  })

  // Gunakan nama yang konsisten untuk state dan getter
  // const isLoadingPackages = computed(() => isLoading.value);
  // const getFetchError = computed(() => error.value);

  async function fetchPackages(forceRefresh: boolean = false) {
    if (!forceRefresh && packages.value.length > 0 && !error.value) {
      // isLoading.value = false; // Tidak perlu jika sudah false
      return
    }

    isLoading.value = true
    error.value = null

    try {
      const response = await $api<PackagesApiResponse>('/packages', { // Path relatif ke baseURL $api
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
        },
      })

      if (response?.success && Array.isArray(response.data)) {
        packages.value = response.data
      }
      else {
        throw new Error(response?.message || 'Struktur respons API paket tidak valid.')
      }
    }
    catch (err: any) {
      const errorData = err.data || {}
      const status = err.statusCode || err.response?.status || 500

      let message = 'Terjadi kesalahan saat memuat paket.'
      if (status === 404) {
        message = 'Endpoint API paket tidak ditemukan.'
      }
      else if (status === 401) {
        message = 'Autentikasi diperlukan untuk paket.' // Interceptor $api akan menangani logout
      }
      else if (errorData.message) {
        message = errorData.message
      }
      else if (err.message) {
        message = err.message
      }
      error.value = `${message} [Status: ${status}]`
      packages.value = []
    }
    finally {
      isLoading.value = false
    }
  }

  return {
    packages,
    isLoading,
    error,
    getPackageById,
    activePackagesCount,
    fetchPackages,
  }
})
