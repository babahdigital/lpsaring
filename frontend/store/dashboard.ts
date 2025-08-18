// frontend/store/dashboard.ts

import { useNuxtApp } from 'nuxt/app'
import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Mendefinisikan struktur objek untuk data transaksi terakhir.
 */
interface TransaksiTerakhir {
  id: string
  amount: number
  created_at: string
  package: { name: string } | null
  user: { full_name: string | null, phone_number: string } | null
}

/**
 * Mendefinisikan struktur objek untuk data paket terlaris.
 */
interface PaketTerlaris {
  name: string
  count: number
}

// Tipe data untuk statistik dashboard yang sekarang lebih spesifik.
interface DashboardStats {
  pendapatanHariIni: number
  pendapatanBulanIni: number
  pendaftarBaru: number
  penggunaAktif: number
  akanKadaluwarsa: number
  kuotaTerjualMb?: number
  transaksiTerakhir: TransaksiTerakhir[]
  paketTerlaris: PaketTerlaris[]
  pendapatanMingguIni?: number
  pendapatanMingguLalu?: number
  transaksiMingguIni?: number
  transaksiMingguLalu?: number
  kuotaPerHari?: number[]
  pendapatanPerHari?: { x: string, y: number }[]
}

export const useDashboardStore = defineStore('dashboard', () => {
  const { $api } = useNuxtApp()

  // State
  const stats = ref<DashboardStats | null>(null)
  const isLoading = ref(false)
  const error = ref<any | null>(null)

  // Actions
  async function fetchDashboardStats() {
    if (isLoading.value)
      return

    isLoading.value = true
    error.value = null
    try {
      // [PERBAIKAN UTAMA] Menambahkan parameter query start_date dan end_date.
      // Backend memerlukan rentang tanggal untuk memproses permintaan statistik.
      // Kita akan mengambil data untuk 30 hari terakhir sebagai default.
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(endDate.getDate() - 29) // Mengatur tanggal mulai ke 29 hari sebelum hari ini

      // Fungsi helper untuk memformat tanggal ke format YYYY-MM-DD
      const toISODateString = (date: Date) => date.toISOString().split('T')[0]!

      // Membuat parameter URL
      const params = new URLSearchParams({
        start_date: toISODateString(startDate),
        end_date: toISODateString(endDate),
      })

      // Menggabungkan path dengan parameter
      const urlWithParams = `/admin/dashboard/stats?${params.toString()}`

      // Tipe data yang diharapkan dari $api sekarang lebih kuat.
      const data = await $api<DashboardStats>(urlWithParams, {
        method: 'GET',
      })
      stats.value = data
    }
    catch (e) {
      console.error('Gagal mengambil statistik dashboard:', e)
      error.value = e
    }
    finally {
      isLoading.value = false
    }
  }

  // Mereset setiap state secara manual agar 100% type-safe.
  function resetState() {
    stats.value = null
    isLoading.value = false
    error.value = null
    console.log('[Dashboard Store] State telah direset.')
  }

  // Kembalikan semua state dan actions
  return {
    stats,
    isLoading,
    error,
    fetchDashboardStats,
    resetState,
  }
})
