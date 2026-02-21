<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'

interface User {
  id: string
  full_name: string
  phone_number: string
  manual_debt_mb?: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
}

interface ManualDebtItem {
  id: string
  debt_date: string | null
  amount_mb: number
  paid_mb: number
  remaining_mb: number
  is_paid: boolean
  paid_at: string | null
  note: string | null
  created_at: string
  last_paid_source?: string | null
}

const props = defineProps<{ modelValue: boolean, user: User | null }>()
const emit = defineEmits(['update:modelValue'])

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()

const loading = ref(false)
const items = ref<ManualDebtItem[]>([])
const summary = ref<{ manual_debt_mb: number, open_items: number, paid_items: number, total_items: number } | null>(null)
const settlingId = ref<string | null>(null)

const debtAutoMb = computed(() => Number(props.user?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0))
const debtTotalMb = computed(() => Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))

function close() {
  emit('update:modelValue', false)
}

function openPdf() {
  if (!props.user)
    return
  // Open in new tab so admin can print or save as PDF.
  window.open(`/api/admin/users/${props.user.id}/debts/export?format=pdf`, '_blank', 'noopener')
}

async function fetchLedger() {
  if (!props.user)
    return
  loading.value = true
  items.value = []
  summary.value = null
  try {
    const resp = await $api<{ items: ManualDebtItem[], summary: any }>(`/admin/users/${props.user.id}/debts`)
    items.value = Array.isArray(resp.items) ? resp.items : []
    summary.value = resp.summary ?? null
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal memuat riwayat tunggakan.' })
  }
  finally {
    loading.value = false
  }
}

async function settleItem(item: ManualDebtItem) {
  if (!props.user)
    return
  if (item.is_paid === true)
    return

  settlingId.value = item.id
  try {
    await $api(`/admin/users/${props.user.id}/debts/${item.id}/settle`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: 'Item tunggakan berhasil ditandai lunas.' })
    await fetchLedger()
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal menandai item tunggakan sebagai lunas.' })
  }
  finally {
    settlingId.value = null
  }
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen)
      fetchLedger()
  },
)

watch(
  () => props.user?.id,
  () => {
    if (props.modelValue)
      fetchLedger()
  },
)
</script>

<template>
  <VDialog :model-value="props.modelValue" max-width="900" persistent scrollable @update:model-value="close">
    <VCard v-if="props.user">
      <VCardTitle class="pa-4 d-flex align-center bg-primary rounded-t-lg">
        <VIcon icon="tabler-notes" start />
        <span class="headline text-white">Riwayat Tunggakan</span>
        <VSpacer />
        <VBtn icon="tabler-printer" variant="text" class="text-white" @click="openPdf" />
        <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="close" />
      </VCardTitle>
      <VDivider />

      <VCardText class="pa-5" style="max-height: 70vh; overflow-y: auto;">
        <div class="d-flex flex-wrap gap-2 mb-4">
          <VChip size="small" label color="info" variant="tonal">
            {{ props.user.full_name }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            {{ props.user.phone_number }}
          </VChip>
          <VChip size="small" label color="warning" variant="tonal">
            Total Tunggakan: {{ debtTotalMb.toLocaleString('id-ID', { maximumFractionDigits: 2 }) }} MB
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            Otomatis: {{ debtAutoMb.toLocaleString('id-ID', { maximumFractionDigits: 2 }) }} MB
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            Manual: {{ debtManualMb.toLocaleString('id-ID', { maximumFractionDigits: 2 }) }} MB
          </VChip>
        </div>

        <VAlert v-if="summary" type="info" variant="tonal" density="compact" icon="tabler-info-circle" class="mb-4">
          Total item: <strong>{{ summary.total_items }}</strong> • Belum lunas: <strong>{{ summary.open_items }}</strong> • Lunas: <strong>{{ summary.paid_items }}</strong>
        </VAlert>

        <VDataTable
          :items="items"
          :loading="loading"
          density="compact"
          item-key="id"
          class="elevation-0"
        >
          <template #headers>
            <tr>
              <th>Tanggal</th>
              <th class="text-end">Jumlah (MB)</th>
              <th class="text-end">Dibayar (MB)</th>
              <th class="text-end">Sisa (MB)</th>
              <th>Status</th>
              <th>Catatan</th>
              <th class="text-end">Aksi</th>
            </tr>
          </template>

          <template #item="{ item }">
            <tr>
              <td>{{ item.debt_date || '-' }}</td>
              <td class="text-end">{{ Number(item.amount_mb || 0).toLocaleString('id-ID') }}</td>
              <td class="text-end">{{ Number(item.paid_mb || 0).toLocaleString('id-ID') }}</td>
              <td class="text-end">{{ Number(item.remaining_mb || 0).toLocaleString('id-ID') }}</td>
              <td>
                <VChip :color="item.is_paid ? 'success' : 'warning'" size="x-small" label>
                  {{ item.is_paid ? 'LUNAS' : 'BELUM LUNAS' }}
                </VChip>
              </td>
              <td style="min-width: 220px;">{{ item.note || '' }}</td>
              <td class="text-end" style="min-width: 90px;">
                <VBtn
                  v-if="item.is_paid !== true"
                  size="x-small"
                  variant="tonal"
                  color="success"
                  :loading="settlingId === item.id"
                  @click="settleItem(item)"
                >
                  Lunasi
                </VBtn>
              </td>
            </tr>
          </template>

          <template #no-data>
            <div class="text-caption text-disabled pa-4">Tidak ada data.</div>
          </template>
        </VDataTable>
      </VCardText>

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
