<script setup lang="ts">
import type { DashboardStats } from '~/types/dashboard'

import { useDashboardUtils } from '~/composables/useDashboardUtils'

defineProps<{
  stats: DashboardStats
  perbandingan: { persentase: number }
}>()

const { formatCurrency } = useDashboardUtils()
</script>

<template>
  <VCard class="h-100">
    <VCardItem>
      <VCardTitle>Pendapatan Mingguan</VCardTitle>
      <template #append>
        <div
          class="font-weight-medium"
          :class="perbandingan.persentase >= 0 ? 'text-success' : 'text-error'"
        >
          <span v-if="stats.pendapatanMingguLalu === 0 && stats.pendapatanMingguIni > 0">BARU</span>
          <span v-else>{{ perbandingan.persentase >= 0 ? '+' : '' }}{{ perbandingan.persentase.toFixed(1) }}%</span>
        </div>
      </template>
    </VCardItem>
    <VCardText>
      <h4 class="text-h4 my-2">
        {{ formatCurrency(stats.pendapatanMingguIni) }}
      </h4>
      <div class="text-body-2 text-disabled">
        Total pendapatan minggu ini
      </div>
    </VCardText>
    <VCardText>
      <VRow no-gutters>
        <VCol cols="5">
          <div class="d-flex align-center mb-3">
            <VAvatar
              color="info"
              variant="tonal"
              :size="24"
              rounded
              class="me-2"
            >
              <VIcon
                size="18"
                icon="tabler-calendar-check"
              />
            </VAvatar>
            <span>Hari Ini</span>
          </div>
          <h5 class="text-h5">
            {{ formatCurrency(stats.pendapatanHariIni) }}
          </h5>
          <div class="text-body-2 text-disabled">
            {{ stats.transaksiHariIni }} Transaksi
          </div>
        </VCol>
        <VCol cols="2">
          <div class="d-flex flex-column align-center justify-center h-100">
            <VDivider
              vertical
              class="mx-auto"
            />
            <VAvatar
              size="24"
              color="rgba(var(--v-theme-on-surface), var(--v-hover-opacity))"
              class="my-2"
            >
              <div class="text-overline text-disabled">
                VS
              </div>
            </VAvatar>
            <VDivider
              vertical
              class="mx-auto"
            />
          </div>
        </VCol>
        <VCol
          cols="5"
          class="text-end"
        >
          <div class="d-flex align-center justify-end mb-3">
            <span class="me-2">Kemarin</span>
            <VAvatar
              color="secondary"
              variant="tonal"
              :size="24"
              rounded
            >
              <VIcon
                size="18"
                icon="tabler-calendar-stats"
              />
            </VAvatar>
          </div>
          <h5 class="text-h5">
            {{ formatCurrency(stats.pendapatanKemarin) }}
          </h5>
          <div class="text-body-2 text-disabled">
            {{ stats.transaksiMingguLalu }} Transaksi
          </div>
        </VCol>
      </VRow>
      <div class="mt-6">
        <VProgressLinear
          :model-value="(stats.pendapatanMingguIni) / ((stats.pendapatanMingguIni) + (stats.pendapatanMingguLalu || 1)) * 100"
          :color="perbandingan.persentase >= 0 ? 'success' : 'error'"
          height="10"
          bg-color="secondary"
          :rounded-bar="false"
          rounded
        />
      </div>
    </VCardText>
  </VCard>
</template>
