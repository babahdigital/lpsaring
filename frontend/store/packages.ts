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

  async function fetchPackages(forceRefresh: boolean = false) {
    // PERBAIKAN: Mengganti !error.value dengan pengecekan null yang eksplisit.
    if (!forceRefresh && packages.value.length > 0 && error.value == null) {
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
        // PERBAIKAN: Mengganti || dengan ?? untuk nilai default.
        throw new Error(response?.message ?? 'Struktur respons API paket tidak valid.')
      }
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ?? untuk nilai default.
      const errorData = err.data ?? {}
      // PERBAIKAN: Mengganti || dengan ?? untuk nilai fallback.
      const status = err.statusCode ?? err.response?.status ?? 500

      let message = 'Terjadi kesalahan saat memuat paket.'
      if (status === 404) {
        message = 'Endpoint API paket tidak ditemukan.'
      }
      else if (status === 401) {
        message = 'Autentikasi diperlukan untuk paket.'
      }
      // PERBAIKAN: Menambah pengecekan tipe data string yang eksplisit.
      else if (typeof errorData.message === 'string' && errorData.message) {
        message = errorData.message
      }
      // PERBAIKAN: Menambah pengecekan tipe data string yang eksplisit.
      else if (typeof err.message === 'string' && err.message) {
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
