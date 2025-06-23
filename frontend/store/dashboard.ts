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
    if (isLoading.value || stats.value)
      return // Jangan fetch ulang jika sedang loading atau sudah ada data

    isLoading.value = true
    try {
      const response = await $api<DashboardStats>('/admin/dashboard/stats', {
        method: 'GET',
      })

      if (response) {
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
