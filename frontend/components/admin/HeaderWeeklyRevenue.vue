<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { useAuthStore } from '~/store/auth'
import { useDashboardStore } from '~/store/dashboard'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.isAdmin)
const isLoggedIn = computed(() => authStore.isLoggedIn)

// Mengambil nilai pendapatan hari ini
const todayRevenue = computed(() => dashboardStore.stats?.pendapatanHariIni ?? 0)

// Helper untuk format mata uang yang sudah diperkuat
function formatCurrency(value: number) {
  // Pastikan value adalah number dan valid
  // PERBAIKAN: Mengganti isNaN() dengan Number.isNaN()
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'Rp 0'
  }

  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

// Computed property untuk menampilkan pendapatan yang sudah diformat
const todayRevenueDisplay = computed(() => {
  return formatCurrency(todayRevenue.value)
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
      text="Pendapatan Hari Ini"
      location="bottom"
    >
      <template #activator="{ props }">
        <VChip
          v-bind="props"
          color="primary"
          variant="elevated"
          prepend-icon="tabler-cash"
          :disabled="dashboardStore.isLoading"
        >
          <template v-if="dashboardStore.isLoading">
            <VProgressCircular
              indeterminate
              size="16"
              width="2"
              class="me-2"
            />
            <span>Memuat...</span>
          </template>
          <template v-else>
            <strong>{{ todayRevenueDisplay }}</strong>
          </template>
        </VChip>
      </template>
    </VTooltip>
  </div>
</template>

<style scoped>
/* Style untuk membuat loading indicator lebih rapi */
.v-progress-circular {
  margin-right: 8px;
}
</style>
