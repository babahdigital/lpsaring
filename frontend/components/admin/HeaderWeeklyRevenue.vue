<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useDashboardStore } from '~/store/dashboard'
import { useAuthStore } from '~/store/auth'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.isAdmin)
const isLoggedIn = computed(() => authStore.isLoggedIn)

// Mengambil nilai pendapatan mingguan dengan aman menggunakan optional chaining
const weeklyRevenue = computed(() => dashboardStore.stats?.weeklyRevenue)

// Helper untuk format mata uang yang sudah diperkuat untuk menangani nilai non-numerik
const formatCurrency = (value: number | undefined | null) => {
  if (typeof value !== 'number') {
    return 'Rp 0'
  }
  
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

// Computed property untuk menampilkan pendapatan mingguan yang sudah diformat
const weeklyRevenueDisplay = computed(() => {
  return formatCurrency(weeklyRevenue.value)
})

// Secara otomatis mengambil data saat komponen dimuat, jika pengguna adalah admin
onMounted(() => {
  if (isAdmin.value && isLoggedIn.value) {
    dashboardStore.fetchDashboardStats()
  }
})
</script>

<template>
  <div>
    <VTooltip
      text="Pendapatan Minggu Ini"
      location="bottom"
    >
      <template #activator="{ props }">
        <VChip
          v-bind="props"
          color="primary"
          variant="elevated"
          prepend-icon="tabler-currency-rupiah"
        >
          <VProgressCircular
            v-if="dashboardStore.isLoading"
            indeterminate
            size="20"
            class="me-2"
          />
          <strong v-else>{{ weeklyRevenueDisplay }}</strong>
        </VChip>
      </template>
    </VTooltip>
  </div>
</template>