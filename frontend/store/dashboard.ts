import { useNuxtApp } from '#app'
import { defineStore } from 'pinia'
import { ref } from 'vue'

// Definisikan tipe untuk respons API statistik
interface DashboardStats {
  totalUsers: number
  pendingApprovals: number
  activePackages: number
  monthlyRevenue: number
  weeklyRevenue: number
}

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const isLoading = ref(false)

  const { $api } = useNuxtApp()

  /**
   * Mengambil semua data statistik dari API.
   */
  async function fetchDashboardStats() {
    // Periksa secara eksplisit apakah stats.value tidak null untuk menghindari error linter.
    if (isLoading.value || stats.value !== null)
      return // Jangan fetch ulang jika sedang loading atau sudah ada data

    isLoading.value = true
    try {
      const response = await $api<DashboardStats>('/admin/dashboard/stats', {
        method: 'GET',
      })

      // Periksa secara eksplisit apakah response adalah objek yang valid dan tidak null.
      if (typeof response === 'object' && response !== null) {
        stats.value = response
      }
    }
    catch (error) {
      console.error('Failed to fetch dashboard stats:', error)
      stats.value = null // Reset jika gagal
    }
    finally {
      isLoading.value = false
    }
  }

  /**
   * Mereset state saat admin logout.
   */
  function resetState() {
    stats.value = null
    isLoading.value = false
  }

  return {
    stats,
    isLoading,
    fetchDashboardStats,
    resetState,
  }
})