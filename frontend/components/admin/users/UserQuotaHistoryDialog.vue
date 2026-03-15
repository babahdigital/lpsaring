<script lang="ts" setup>
import type { QuotaHistoryItem, QuotaHistoryResponse, QuotaHistorySummary } from '~/types/user'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '@/composables/useSnackbar'

interface UserLite {
  id: string
  full_name: string
  phone_number: string
}

const props = defineProps<{ modelValue: boolean, user: UserLite | null }>()
const emit = defineEmits(['update:modelValue'])

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()

const loading = ref(false)
const items = ref<QuotaHistoryItem[]>([])
const summary = ref<QuotaHistorySummary | null>(null)
const isMobile = computed(() => smAndDown.value)

function close() {
  emit('update:modelValue', false)
}

function categoryColor(category?: string | null): string {
  switch (category) {
    case 'usage':
      return 'info'
    case 'purchase':
      return 'success'
    case 'debt':
      return 'warning'
    case 'policy':
      return 'secondary'
    case 'adjustment':
      return 'primary'
    default:
      return 'default'
  }
}

function categoryLabel(category?: string | null): string {
  switch (category) {
    case 'usage':
      return 'Usage'
    case 'purchase':
      return 'Purchase'
    case 'debt':
      return 'Debt'
    case 'policy':
      return 'Policy'
    case 'adjustment':
      return 'Adjust'
    default:
      return 'System'
  }
}

function openPdf() {
  if (!props.user)
    return
  window.open(`/api/admin/users/${props.user.id}/quota-history/export?format=pdf`, '_blank', 'noopener')
}

async function fetchHistory() {
  if (!props.user)
    return

  loading.value = true
  items.value = []
  summary.value = null
  try {
    const resp = await $api<QuotaHistoryResponse>(`/admin/users/${props.user.id}/quota-history?page=1&itemsPerPage=50`)
    items.value = Array.isArray(resp.items) ? resp.items : []
    summary.value = resp.summary ?? null
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Riwayat Kuota', text: error?.data?.message || 'Gagal memuat riwayat mutasi kuota.' })
  }
  finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen)
      fetchHistory()
  },
)

watch(
  () => props.user?.id,
  () => {
    if (props.modelValue)
      fetchHistory()
  },
)
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    :fullscreen="isMobile"
    :max-width="isMobile ? undefined : 1100"
    persistent
    @update:model-value="close"
  >
    <VCard v-if="props.user">
      <VCardTitle class="pa-4 bg-primary rounded-t-lg">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title">
            <VIcon icon="tabler-history-toggle" start />
            <span class="headline text-white">Riwayat Mutasi Kuota</span>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-printer" variant="text" class="text-white" @click="openPdf" />
            <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="close" />
          </div>
        </div>
      </VCardTitle>
      <VDivider />

      <AppPerfectScrollbar class="history-dialog__scroll pa-5">
        <div class="history-summary-chips d-flex flex-wrap gap-2 mb-4">
          <VChip size="small" label color="info" variant="tonal">
            {{ props.user.full_name }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            {{ props.user.phone_number }}
          </VChip>
          <VChip v-if="summary" size="small" label color="primary" variant="tonal">
            Event: {{ summary.page_items }}
          </VChip>
          <VChip v-if="summary" size="small" label color="success" variant="tonal">
            Net beli: {{ summary.total_net_purchased_mb }} MB
          </VChip>
          <VChip v-if="summary" size="small" label color="warning" variant="tonal">
            Net pakai: {{ summary.total_net_used_mb }} MB
          </VChip>
        </div>

        <VAlert
          v-if="summary"
          type="info"
          variant="tonal"
          density="compact"
          icon="tabler-info-circle"
          class="mb-4"
        >
          Rentang data: <strong>{{ summary.first_event_at_display || '-' }}</strong> sampai <strong>{{ summary.last_event_at_display || '-' }}</strong>
          • Usage: <strong>{{ summary.usage_events }}</strong>
          • Purchase: <strong>{{ summary.purchase_events }}</strong>
          • Debt: <strong>{{ summary.debt_events }}</strong>
          • Policy: <strong>{{ summary.policy_events }}</strong>
        </VAlert>

        <div v-if="loading" class="d-flex justify-center py-8">
          <VProgressCircular indeterminate color="primary" />
        </div>

        <div v-else-if="isMobile" class="history-mobile-list">
          <VCard v-for="item in items" :key="item.id" variant="outlined" class="history-mobile-card">
            <VCardText class="history-mobile-card__body">
              <div class="history-mobile-card__header">
                <div>
                  <div class="font-weight-medium">{{ item.title }}</div>
                  <div class="text-caption text-medium-emphasis mt-1">{{ item.created_at_display || '-' }}</div>
                </div>
                <VChip size="x-small" :color="categoryColor(item.category)" label>
                  {{ categoryLabel(item.category) }}
                </VChip>
              </div>

              <div class="text-body-2 mt-3">{{ item.description }}</div>

              <div v-if="item.actor_name" class="text-caption text-medium-emphasis mt-2">
                Aktor: {{ item.actor_name }}
              </div>

              <div class="d-flex flex-wrap gap-2 mt-3">
                <VChip v-if="item.deltas_display.purchased" size="small" color="success" variant="tonal" label>
                  Beli {{ item.deltas_display.purchased }}
                </VChip>
                <VChip v-if="item.deltas_display.used" size="small" color="info" variant="tonal" label>
                  Pakai {{ item.deltas_display.used }}
                </VChip>
                <VChip v-if="item.deltas_display.debt_total" size="small" color="warning" variant="tonal" label>
                  Debt {{ item.deltas_display.debt_total }}
                </VChip>
                <VChip v-if="item.deltas_display.remaining_after" size="small" color="default" variant="tonal" label>
                  Sisa {{ item.deltas_display.remaining_after }}
                </VChip>
              </div>

              <ul v-if="item.highlights?.length" class="history-highlights mt-3">
                <li v-for="highlight in item.highlights.slice(0, 6)" :key="`${item.id}-${highlight}`">
                  {{ highlight }}
                </li>
              </ul>
            </VCardText>
          </VCard>

          <VAlert v-if="items.length === 0" variant="tonal" color="default" class="mt-2">
            Belum ada riwayat mutasi kuota.
          </VAlert>
        </div>

        <div v-else class="history-table-scroll">
          <VTable density="compact" class="history-table">
            <thead>
              <tr>
                <th>Waktu</th>
                <th>Event</th>
                <th class="text-end">Delta</th>
                <th class="text-end">Sisa Setelah</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id">
                <td class="text-no-wrap align-top">{{ item.created_at_display || '-' }}</td>
                <td class="history-table__event align-top">
                  <div class="font-weight-medium">{{ item.title }}</div>
                  <div class="text-caption text-medium-emphasis mt-1">{{ item.source }}</div>
                  <VChip size="x-small" :color="categoryColor(item.category)" label class="mt-2">
                    {{ categoryLabel(item.category) }}
                  </VChip>
                </td>
                <td class="history-table__delta text-end align-top">
                  <div v-if="item.deltas_display.purchased" class="text-no-wrap">Beli {{ item.deltas_display.purchased }}</div>
                  <div v-if="item.deltas_display.used" class="text-no-wrap">Pakai {{ item.deltas_display.used }}</div>
                  <div v-if="item.deltas_display.debt_total" class="text-no-wrap">Debt {{ item.deltas_display.debt_total }}</div>
                  <div v-if="!item.deltas_display.purchased && !item.deltas_display.used && !item.deltas_display.debt_total">-</div>
                </td>
                <td class="text-end align-top text-no-wrap">{{ item.deltas_display.remaining_after || '-' }}</td>
                <td class="history-table__detail align-top">
                  <div>{{ item.description }}</div>
                  <div v-if="item.actor_name" class="text-caption text-medium-emphasis mt-1">
                    Aktor: {{ item.actor_name }}
                  </div>

                  <ul v-if="item.highlights?.length" class="history-highlights mt-2">
                    <li v-for="highlight in item.highlights.slice(0, 6)" :key="`${item.id}-${highlight}`">
                      {{ highlight }}
                    </li>
                  </ul>
                </td>
              </tr>

              <tr v-if="items.length === 0">
                <td colspan="5" class="text-center text-medium-emphasis py-6">
                  Belum ada riwayat mutasi kuota.
                </td>
              </tr>
            </tbody>
          </VTable>
        </div>
      </AppPerfectScrollbar>

      <VDivider />
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" color="secondary" @click="close">
          Tutup
        </VBtn>
        <VBtn color="primary" prepend-icon="tabler-file-type-pdf" @click="openPdf">
          PDF (Cetak / Simpan)
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.dialog-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.dialog-titlebar__title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-dialog__scroll {
  max-height: 72vh;
}

.history-summary-chips {
  align-items: flex-start;
}

.history-table-scroll {
  overflow-x: auto;
}

.history-table__event {
  min-width: 220px;
}

.history-table__delta {
  min-width: 160px;
}

.history-table__detail {
  min-width: 340px;
}

.history-mobile-list {
  display: grid;
  gap: 12px;
}

.history-mobile-card {
  border-radius: 16px;
}

.history-mobile-card__body {
  display: flex;
  flex-direction: column;
}

.history-mobile-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.history-highlights {
  margin: 0;
  padding-left: 18px;
}

.history-highlights li {
  margin: 0 0 2px;
}

@media (max-width: 600px) {
  .dialog-titlebar {
    flex-direction: column;
    align-items: flex-start;
  }

  .dialog-titlebar__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .history-dialog__scroll {
    max-height: none;
  }

  .history-mobile-card__header {
    flex-direction: column;
  }
}
</style>