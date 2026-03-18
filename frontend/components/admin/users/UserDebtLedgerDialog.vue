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
  due_date: string | null
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
const settlingAll = ref(false)

const debtAutoMb = computed(() => Number(props.user?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0))
const debtTotalMb = computed(() => Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))

function formatDataSize(sizeInMB: number): string {
  if (!Number.isFinite(sizeInMB) || Number.isNaN(sizeInMB))
    return '0 MB'
  const options = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (sizeInMB < 1)
    return `${(sizeInMB * 1024).toLocaleString('id-ID', options)} KB`
  else if (sizeInMB < 1024)
    return `${sizeInMB.toLocaleString('id-ID', options)} MB`
  else
    return `${(sizeInMB / 1024).toLocaleString('id-ID', options)} GB`
}

/** Format ISO datetime → tanggal + waktu WIB/WITA lokal (UTC+8 Makassar) */
function formatDatetimeLocal(isoStr: string | null | undefined): string {
  if (!isoStr)
    return '-'
  try {
    const d = new Date(isoStr)
    if (Number.isNaN(d.getTime()))
      return '-'
    return d.toLocaleString('id-ID', {
      timeZone: 'Asia/Makassar',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  catch {
    return '-'
  }
}

/** Format date string (YYYY-MM-DD) → tanggal saja */
function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr)
    return '-'
  try {
    const d = new Date(`${dateStr}T00:00:00+08:00`)
    if (Number.isNaN(d.getTime()))
      return '-'
    return d.toLocaleDateString('id-ID', {
      timeZone: 'Asia/Makassar',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }
  catch {
    return '-'
  }
}

function close() {
  emit('update:modelValue', false)
}

function openPdf() {
  if (!props.user)
    return
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

async function settleAll() {
  if (!props.user)
    return

  settlingAll.value = true
  try {
    await $api(`/admin/users/${props.user.id}/debts/settle-all`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: 'Semua tunggakan berhasil dilunasi.' })
    await fetchLedger()
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal melunasi semua tunggakan.' })
  }
  finally {
    settlingAll.value = false
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
  <VDialog :model-value="props.modelValue" max-width="1100" persistent @update:model-value="close">
    <VCard v-if="props.user">
      <VCardTitle class="pa-4 bg-primary rounded-t-lg">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title">
            <VIcon icon="tabler-notes" start />
            <span class="headline text-white">Riwayat Tunggakan</span>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-printer" variant="text" class="text-white" @click="openPdf" />
            <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="close" />
          </div>
        </div>
      </VCardTitle>
      <VDivider />

      <AppPerfectScrollbar class="pa-5" style="max-height: 72vh;">
        <div class="d-flex flex-wrap gap-2 mb-4">
          <VChip size="small" label color="info" variant="tonal">
            {{ props.user.full_name }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            {{ props.user.phone_number }}
          </VChip>
          <VChip size="small" label color="warning" variant="tonal">
            Total Tunggakan: {{ formatDataSize(debtTotalMb) }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            Otomatis: {{ formatDataSize(debtAutoMb) }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            Manual: {{ formatDataSize(debtManualMb) }}
          </VChip>
        </div>

        <VAlert v-if="summary" type="info" variant="tonal" density="compact" icon="tabler-info-circle" class="mb-4">
          Total item: <strong>{{ summary.total_items }}</strong> • Belum lunas: <strong>{{ summary.open_items }}</strong> • Lunas: <strong>{{ summary.paid_items }}</strong>
        </VAlert>

        <!-- Tabel debt — horizontal scroll di layar kecil -->
        <div class="debt-table-scroll">
          <VDataTable
            :items="items"
            :loading="loading"
            density="compact"
            item-key="id"
            class="debt-ledger-table elevation-0"
            hide-default-footer
          >
            <template #headers>
              <tr>
                <th class="col-tanggal">Tanggal Utang</th>
                <th class="col-dicatat">Dicatat Pada</th>
                <th class="col-tempo">Jatuh Tempo</th>
                <th class="text-end col-jumlah">Jumlah</th>
                <th class="text-end col-dibayar">Dibayar</th>
                <th class="col-status">Status</th>
                <th class="col-catatan">Catatan</th>
                <th class="text-end col-aksi">Aksi</th>
              </tr>
            </template>

            <template #item="{ item }">
              <tr>
                <!-- Tanggal utang (debt_date — tanggal billing) -->
                <td class="col-tanggal text-no-wrap">
                  {{ formatDate(item.debt_date) }}
                </td>
                <!-- Waktu pencatatan (created_at — datetime) -->
                <td class="col-dicatat text-no-wrap text-caption text-medium-emphasis">
                  {{ formatDatetimeLocal(item.created_at) }}
                </td>
                <!-- Jatuh tempo (due_date — opsional) -->
                <td class="col-tempo text-no-wrap">
                  <span v-if="item.due_date">
                    <VChip
                      size="x-small"
                      :color="item.is_paid ? 'default' : 'error'"
                      variant="tonal"
                      label
                    >
                      {{ formatDate(item.due_date) }}
                    </VChip>
                  </span>
                  <span v-else class="text-disabled text-caption">—</span>
                </td>
                <!-- Jumlah -->
                <td class="text-end col-jumlah text-no-wrap">
                  {{ formatDataSize(Number(item.amount_mb || 0)) }}
                </td>
                <!-- Dibayar -->
                <td class="text-end col-dibayar text-no-wrap">
                  {{ formatDataSize(Number(item.paid_mb || 0)) }}
                </td>
                <!-- Status + waktu dibayar -->
                <td class="col-status">
                  <div class="d-flex flex-column gap-1">
                    <VChip :color="item.is_paid ? 'success' : 'warning'" size="x-small" label>
                      {{ item.is_paid ? 'LUNAS' : 'BELUM LUNAS' }}
                    </VChip>
                    <span v-if="item.is_paid && item.paid_at" class="text-caption text-medium-emphasis text-no-wrap">
                      {{ formatDatetimeLocal(item.paid_at) }}
                    </span>
                  </div>
                </td>
                <!-- Catatan -->
                <td class="col-catatan">
                  <span :title="item.note || ''" class="debt-note-cell">{{ item.note || '' }}</span>
                </td>
                <!-- Aksi -->
                <td class="text-end col-aksi text-no-wrap">
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
        </div>
      </AppPerfectScrollbar>

      <VDivider />
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn
          v-if="debtTotalMb > 0"
          variant="tonal"
          color="success"
          :loading="settlingAll"
          @click="settleAll"
        >
          Lunasi Semua
        </VBtn>
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

/* Horizontal scroll container untuk tabel di layar kecil */
.debt-table-scroll {
  overflow-x: auto;
  padding-block-end: 6px;
}

/* Lebar minimum agar tabel tidak terlalu sempit di desktop */
.debt-ledger-table :deep(.v-table__wrapper > table),
.debt-ledger-table :deep(table) {
  min-width: 920px;
  width: 100%;
  table-layout: fixed;
}

/* Lebar kolom yang terdefinisi */
.col-tanggal   { width: 110px; min-width: 100px; white-space: nowrap; }
.col-dicatat   { width: 160px; min-width: 140px; white-space: nowrap; }
.col-tempo     { width: 120px; min-width: 110px; white-space: nowrap; }
.col-jumlah    { width: 100px; min-width:  90px; }
.col-dibayar   { width: 100px; min-width:  90px; }
.col-status    { width: 140px; min-width: 120px; }
.col-catatan   { min-width: 160px; }
.col-aksi      { width:  80px; min-width:  80px; }

.debt-note-cell {
  display: block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
}
</style>
