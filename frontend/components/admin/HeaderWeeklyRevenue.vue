<script setup lang="ts">
import { computed } from 'vue'
import { useDashboardStore } from '~/store/dashboard'

const dashboardStore = useDashboardStore()

// Helper untuk format mata uang menjadi lebih ringkas (Contoh: Rp 10.000.000)
const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

const weeklyRevenueDisplay = computed(() => {
  if (dashboardStore.stats) {
    return formatCurrency(dashboardStore.stats.weeklyRevenue)
  }
  return 'Rp 0' // Default value
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
          prepend-icon="tabler-cash"
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