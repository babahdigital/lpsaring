<script setup lang="ts">
import type { TransaksiTerakhir } from '~/types/dashboard'

import { useDashboardUtils } from '~/composables/useDashboardUtils'

defineProps<{
  transactions: TransaksiTerakhir[]
  isRefreshing: boolean
  onRefresh: () => void
}>()

const { formatCurrency, formatRelativeTime, getUserInitials, formatPhoneNumberForDisplay } = useDashboardUtils()
</script>

<template>
  <VCard>
    <VCardItem>
      <VCardTitle>Aktivitas Terakhir</VCardTitle>
      <template #append>
        <div class="me-n2">
          <VBtn
            icon
            variant="text"
            size="small"
            color="default"
            :loading="isRefreshing"
            @click="onRefresh"
          >
            <VIcon
              size="24"
              icon="tabler-refresh"
            />
          </VBtn>
        </div>
      </template>
    </VCardItem>
    <VCardText>
      <VTimeline
        v-if="transactions.length > 0"
        side="end"
        align="start"
        line-inset="8"
        truncate-line="start"
        density="compact"
      >
        <VTimelineItem
          v-for="transaksi in transactions.slice(0, 3)"
          :key="transaksi.id"
          dot-color="success"
          size="x-small"
        >
          <div class="d-flex justify-space-between align-start flex-wrap mb-2">
            <div class="app-timeline-title">
              Pembelian {{ transaksi.package.name }}
            </div>
            <span class="app-timeline-meta">{{ formatRelativeTime(transaksi.created_at) }}</span>
          </div>
          <div class="app-timeline-text mt-1 mb-3">
            Transaksi sebesar {{ formatCurrency(transaksi.amount) }} telah berhasil.
          </div>
          <div class="d-flex justify-space-between align-center flex-wrap">
            <div class="d-flex align-center mt-2">
              <VAvatar
                size="32"
                class="me-2"
                color="primary"
                variant="tonal"
              >
                <span class="text-sm font-weight-medium">{{ getUserInitials(transaksi.user?.full_name) }}</span>
              </VAvatar>
              <div class="d-flex flex-column">
                <p class="text-sm font-weight-medium text-medium-emphasis mb-0">
                  {{ transaksi.user?.full_name ?? 'Pengguna Dihapus' }}
                </p>
                <span class="text-sm">{{ formatPhoneNumberForDisplay(transaksi.user?.phone_number) }}</span>
              </div>
            </div>
          </div>
        </VTimelineItem>
      </VTimeline>
      <div
        v-else
        class="d-flex flex-column align-center justify-center text-center"
        style="min-height: 300px;"
      >
        <VIcon
          icon="tabler-file-off"
          size="50"
          class="text-disabled mb-2"
        />
        <p class="text-disabled">
          Belum ada aktivitas transaksi.
        </p>
      </div>
    </VCardText>
  </VCard>
</template>
