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
    return packages.value.filter(pkg => pkg.is_active === true).length
  })

  async function fetchPackages(forceRefresh: boolean = false) {
    if (forceRefresh === false && packages.value.length > 0 && error.value == null) {
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

      if (response?.success === true && Array.isArray(response.data)) {
        packages.value = response.data
      }
      else {
        throw new Error(response?.message ?? 'Struktur respons API paket tidak valid.')
      }
    }
    catch (err: any) {
      const errorData = err.data ?? {}
      const status = err.statusCode ?? err.response?.status ?? 500

      let message = 'Terjadi kesalahan saat memuat paket.'
      if (status === 404) {
        message = 'Endpoint API paket tidak ditemukan.'
      }
      else if (status === 401) {
        message = 'Autentikasi diperlukan untuk paket.'
      }
      // PERBAIKAN FINAL: Pengecekan string kosong secara eksplisit.
      else if (typeof errorData.message === 'string' && errorData.message.length > 0) {
        message = errorData.message
      }
      // PERBAIKAN FINAL: Pengecekan string kosong secara eksplisit.
      else if (typeof err.message === 'string' && err.message.length > 0) {
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
