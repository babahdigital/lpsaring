<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
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
  is_paid: boolean
  paid_at: string | null
  note: string | null
  price_rp: number | null
  estimated_rp: number
  created_at: string
  last_paid_source?: string | null
}

const props = defineProps<{ modelValue: boolean, user: User | null }>()
const emit = defineEmits(['update:modelValue'])

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()

const loading = ref(false)
const items = ref<ManualDebtItem[]>([])
const summary = ref<{ manual_debt_mb: number, open_items: number, paid_items: number, total_items: number } | null>(null)
const settlingId = ref<string | null>(null)
const settlingAll = ref(false)
const sendingWhatsapp = ref(false)

const debtAutoMb = computed(() => Number(props.user?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0))
const debtTotalMb = computed(() => Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))
const isMobile = computed(() => smAndDown.value)
const hasUnlimitedDebtItem = computed(() => items.value.some(item => isUnlimitedDebtItem(item)))
const debtOverviewCards = computed(() => {
  const currentSummary = summary.value
  const totalValue = hasUnlimitedDebtItem.value ? 'Unlimited' : formatDataSize(debtTotalMb.value)
  const manualValue = hasUnlimitedDebtItem.value ? 'Unlimited' : formatDataSize(debtManualMb.value)

  return [
    {
      key: 'total',
      label: 'Total Tunggakan',
      value: totalValue,
      caption: currentSummary ? `${currentSummary.total_items} item tercatat` : 'Menunggu data ringkasan',
      color: debtTotalMb.value > 0 ? 'warning' : 'secondary',
      icon: 'tabler-stack-2',
    },
    {
      key: 'open',
      label: 'Belum Lunas',
      value: currentSummary ? `${currentSummary.open_items}` : '-',
      caption: currentSummary ? 'Item yang masih perlu follow up' : 'Ringkasan status belum tersedia',
      color: (currentSummary?.open_items ?? 0) > 0 ? 'error' : 'secondary',
      icon: 'tabler-alert-triangle',
    },
    {
      key: 'manual',
      label: 'Manual',
      value: manualValue,
      caption: 'Akumulasi dari pencatatan manual',
      color: debtManualMb.value > 0 ? 'primary' : 'secondary',
      icon: 'tabler-pencil-dollar',
    },
    {
      key: 'auto',
      label: 'Otomatis',
      value: formatDataSize(debtAutoMb.value),
      caption: currentSummary ? `${currentSummary.paid_items} item sudah lunas` : 'Akumulasi otomatis dari sistem',
      color: debtAutoMb.value > 0 ? 'info' : 'secondary',
      icon: 'tabler-bolt',
    },
  ]
})

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

function formatRupiah(rp: number | null | undefined): string {
  if (!rp || rp <= 0)
    return '—'
  return `Rp ${rp.toLocaleString('id-ID')}`
}

function isUnlimitedDebtItem(item: Pick<ManualDebtItem, 'note' | 'amount_mb'> | null | undefined): boolean {
  if (!item)
    return false
  const note = String(item.note ?? '').toLowerCase()
  return note.startsWith('paket:') && note.includes('unlimited') && Number(item.amount_mb ?? 0) <= 1
}

function formatDebtAmountLabel(item: Pick<ManualDebtItem, 'note' | 'amount_mb'>): string {
  if (isUnlimitedDebtItem(item))
    return 'Unlimited'
  return formatDataSize(Number(item.amount_mb || 0))
}

/** Format ISO datetime → tanggal + waktu WITA (UTC+8) */
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

/**
 * Format due_date (YYYY-MM-DD) → "18 Apr 2026, 23:59" (end-of-day WITA)
 * Menampilkan "23:59" karena jatuh tempo berlaku s.d. akhir hari.
 */
function formatDueDate(dateStr: string | null | undefined): string {
  if (!dateStr)
    return ''
  try {
    // Treat as end-of-day in WITA (UTC+8)
    const d = new Date(`${dateStr}T23:59:00+08:00`)
    if (Number.isNaN(d.getTime()))
      return dateStr
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
    return dateStr
  }
}

/** Apakah jatuh tempo sudah lewat (merah) */
function isDueDateOverdue(dateStr: string | null | undefined): boolean {
  if (!dateStr)
    return false
  try {
    const due = new Date(`${dateStr}T23:59:00+08:00`)
    return due < new Date()
  }
  catch {
    return false
  }
}

/** Tampilkan hanya nama paket dari note format "Paket: Nama Paket (... GB, Rp ...)" */
function parsePackageName(note: string | null | undefined): string | null {
  if (!note)
    return null
  const prefix = 'Paket: '
  if (!note.startsWith(prefix))
    return note
  const rest = note.slice(prefix.length)
  const parenIdx = rest.indexOf(' (')
  return parenIdx > 0 ? rest.slice(0, parenIdx) : rest
}

/**
 * Kembalikan due_date yang efektif.
 * Jika due_date sudah ada gunakan itu; jika null, hitung hari terakhir bulan dari debt_date.
 * Ini sebagai fallback untuk record lama sebelum auto-compute due_date diterapkan.
 */
function getEffectiveDueDate(debtDate: string | null | undefined, dueDate: string | null | undefined): string | null {
  if (dueDate)
    return dueDate
  if (!debtDate)
    return null
  const d = new Date(`${debtDate}T00:00:00`)
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0)
  return lastDay.toISOString().slice(0, 10)
}

function close() {
  emit('update:modelValue', false)
}

function openPdf() {
  if (!props.user)
    return
  openPdfDocument(`/api/admin/users/${props.user.id}/debts/export?format=pdf`).catch((error: any) => {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || error?.message || 'Gagal membuka PDF tunggakan.' })
  })
}

async function sendWhatsAppReport() {
  if (!props.user)
    return

  sendingWhatsapp.value = true
  try {
    const resp = await $api<{ message?: string }>(`/admin/users/${props.user.id}/debts/send-whatsapp`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: resp?.message || 'Ringkasan tunggakan berhasil diantrikan ke WhatsApp.' })
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal mengirim ringkasan tunggakan ke WhatsApp.' })
  }
  finally {
    sendingWhatsapp.value = false
  }
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
  if (!props.user || item.is_paid === true)
    return

  settlingId.value = item.id
  try {
    const resp = await $api<{ receipt_url?: string }>(`/admin/users/${props.user.id}/debts/${item.id}/settle`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: 'Item tunggakan berhasil ditandai lunas.' })
    if (resp?.receipt_url)
      await openPdfDocument(resp.receipt_url)
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
    const resp = await $api<{ receipt_url?: string }>(`/admin/users/${props.user.id}/debts/settle-all`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: 'Semua tunggakan berhasil dilunasi.' })
    if (resp?.receipt_url)
      await openPdfDocument(resp.receipt_url)
    await fetchLedger()
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal melunasi semua tunggakan.' })
  }
  finally {
    settlingAll.value = false
  }
}

async function openPdfDocument(url: string) {
  const data = await $api<Blob>(url, {
    method: 'GET',
    responseType: 'blob' as const,
  })
  const blob = data instanceof Blob ? data : new Blob([data as BlobPart], { type: 'application/pdf' })
  const objectUrl = window.URL.createObjectURL(blob)
  const pdfWindow = window.open(objectUrl, '_blank', 'noopener')
  if (!pdfWindow)
    showSnackbar({ type: 'info', title: 'PDF', text: 'Popup diblokir browser. Cek izin popup.' })
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000)
}

watch(
  () => props.modelValue,
  (isOpen) => { if (isOpen) fetchLedger() },
)

watch(
  () => props.user?.id,
  () => { if (props.modelValue) fetchLedger() },
)
</script>

<template>
  <VDialog :model-value="props.modelValue" :fullscreen="isMobile" :max-width="isMobile ? undefined : 1000" persistent @update:model-value="close">
    <VCard v-if="props.user" :class="isMobile ? 'rounded-0' : 'rounded-lg'">
      <VCardTitle class="debt-ledger__hero" :class="isMobile ? '' : 'rounded-t-lg'">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title debt-ledger__hero-titleWrap">
            <div class="debt-ledger__hero-icon">
              <VIcon icon="tabler-notes" size="22" />
            </div>
            <div class="debt-ledger__hero-copy">
              <span class="headline text-white">Riwayat Tunggakan</span>
              <div class="debt-ledger__hero-subtitle text-white">
                Ringkasan utang kuota & status pelunasan.
              </div>
            </div>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="close" />
          </div>
        </div>

        <div class="debt-ledger__hero-meta">
          <VChip size="small" label color="info" variant="tonal">
            {{ props.user.full_name }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            {{ props.user.phone_number }}
          </VChip>
          <VChip v-if="summary" size="small" label :color="summary.open_items > 0 ? 'warning' : 'success'" variant="tonal">
            {{ summary.open_items }} belum lunas
          </VChip>
        </div>
      </VCardTitle>
      <VDivider />

      <AppPerfectScrollbar class="pa-4 pa-md-5 debt-ledger__scroll" :native-scroll="isMobile" :style="isMobile ? 'max-height: calc(100vh - 132px);' : 'max-height: 74vh;'">
        <div class="debt-overview-grid mb-4">
          <div v-for="card in debtOverviewCards" :key="card.key" class="debt-overview-card">
            <div class="debt-overview-card__head">
              <VAvatar size="34" :color="card.color" variant="tonal">
                <VIcon :icon="card.icon" size="18" />
              </VAvatar>
              <div class="debt-overview-card__label">{{ card.label }}</div>
            </div>
            <div class="debt-overview-card__value">{{ card.value }}</div>
            <div class="debt-overview-card__caption">{{ card.caption }}</div>
          </div>
        </div>

        <VAlert v-if="summary && summary.open_items > 0" type="warning" variant="tonal" density="comfortable" icon="tabler-alert-triangle" class="mb-4">
          Ada <strong>{{ summary.open_items }}</strong> item yang masih belum lunas. Tinjau per baris untuk follow up atau gunakan aksi <strong>Lunasi Semua</strong> bila sudah selesai.
        </VAlert>

        <div class="debt-table-shell">
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
                <th class="col-dicatat">Dicatat Pada</th>
                <th class="col-tempo">Jatuh Tempo</th>
                <th class="text-end col-kuota">Kuota</th>
                <th class="col-paket">Paket / Info</th>
                <th class="text-end col-harga">Harga</th>
                <th class="col-status">Status</th>
                <th class="text-center col-aksi">Aksi</th>
              </tr>
            </template>

            <template #item="{ item }">
              <tr>
                <!-- Dicatat Pada (created_at) -->
                <td class="col-dicatat text-no-wrap text-caption text-medium-emphasis">
                  {{ formatDatetimeLocal(item.created_at) }}
                </td>

                <!-- Jatuh Tempo (due_date) dengan jam 23:59 WITA -->
                <td class="col-tempo text-no-wrap">
                  <span v-if="getEffectiveDueDate(item.debt_date, item.due_date)">
                    <VChip
                      size="x-small"
                      :color="item.is_paid ? 'default' : (isDueDateOverdue(getEffectiveDueDate(item.debt_date, item.due_date)) ? 'error' : 'warning')"
                      variant="tonal"
                      label
                    >
                      <VIcon start size="10" :icon="isDueDateOverdue(getEffectiveDueDate(item.debt_date, item.due_date)) && !item.is_paid ? 'tabler-alert-triangle' : 'tabler-calendar-due'" />
                      {{ formatDueDate(getEffectiveDueDate(item.debt_date, item.due_date)) }}
                    </VChip>
                  </span>
                  <span v-else class="text-disabled text-caption">Belum ditetapkan</span>
                </td>

                <!-- Kuota -->
                <td class="text-end col-kuota text-no-wrap font-weight-medium">
                  {{ formatDebtAmountLabel(item) }}
                </td>

                <!-- Paket / Info (note) -->
                <td class="col-paket">
                  <span
                    v-if="parsePackageName(item.note)"
                    :title="item.note ?? undefined"
                    class="debt-note-cell text-caption"
                  >{{ parsePackageName(item.note) }}</span>
                  <span v-else class="text-disabled text-caption">—</span>
                </td>

                <!-- Harga estimasi -->
                <td class="text-end col-harga text-no-wrap">
                  <span class="text-caption">{{ formatRupiah(item.price_rp ?? item.estimated_rp) }}</span>
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

                <!-- Aksi -->
                <td class="text-center col-aksi text-no-wrap">
                  <VBtn
                    v-if="item.is_paid !== true"
                    size="x-small"
                    variant="tonal"
                    color="success"
                    prepend-icon="tabler-check"
                    class="px-3 debt-settle-btn"
                    :loading="settlingId === item.id"
                    @click="settleItem(item)"
                  >
                    Lunasi
                  </VBtn>
                  <VIcon v-else icon="tabler-circle-check" color="success" size="18" />
                </td>
              </tr>
            </template>

            <template #no-data>
              <div class="text-caption text-disabled pa-4 text-center">
                <VIcon icon="tabler-inbox" class="mb-1" /><br>
                Tidak ada data tunggakan.
              </div>
            </template>
          </VDataTable>
        </div>
        </div>
      </AppPerfectScrollbar>

      <VDivider />

      <!-- ── Footer actions ── -->
      <VCardActions class="pa-4 flex-wrap gap-2" :class="isMobile ? 'flex-column align-stretch' : ''">
        <VSpacer />
        <VBtn
          v-if="debtTotalMb > 0"
          variant="tonal"
          color="success"
          prepend-icon="tabler-checks"
          :loading="settlingAll"
          @click="settleAll"
        >
          Lunasi Semua
        </VBtn>
        <VBtn variant="tonal" color="secondary" prepend-icon="tabler-x" @click="close">
          Tutup
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

.debt-ledger__hero {
  padding: 18px 20px 16px;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)) 0%, rgba(var(--v-theme-primary), 0.82) 100%);
}

.debt-ledger__hero-titleWrap {
  align-items: flex-start;
}

.debt-ledger__hero-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  flex: 0 0 auto;
}

.debt-ledger__hero-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.debt-ledger__hero-subtitle {
  font-size: 0.9rem;
  line-height: 1.45;
  opacity: 0.86;
}

.debt-ledger__hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.debt-ledger__hero-action {
  min-width: 98px;
}

.debt-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.debt-overview-card {
  padding: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 18px;
  background: rgba(var(--v-theme-surface), 0.88);
}

.debt-overview-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.debt-overview-card__label {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.debt-overview-card__value {
  margin-top: 12px;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.3;
}

.debt-overview-card__caption {
  margin-top: 4px;
  font-size: 0.79rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.debt-ledger__scroll:deep(.app-perfect-scrollbar--native) {
  min-height: 0;
}

.debt-table-shell {
  position: relative;
  isolation: isolate;
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.08);
}

/* ── Horizontal scroll untuk tabel di mobile ── */
.debt-table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding-block-end: 8px;
}

/* Lebar minimum agar kolom tidak terlalu sempit */
.debt-ledger-table :deep(.v-table__wrapper > table),
.debt-ledger-table :deep(table) {
  min-width: 820px;
  width: 100%;
  table-layout: fixed;
}

.debt-ledger-table :deep(thead th) {
  background: rgb(var(--v-theme-surface));
  box-shadow: inset 0 -1px rgba(var(--v-theme-on-surface), 0.08);
}

.debt-ledger-table :deep(tbody tr:nth-child(even)) {
  background: rgba(var(--v-theme-on-surface), 0.015);
}

/* Lebar kolom */
.col-dicatat  { width: 148px; min-width: 130px; white-space: nowrap; }
.col-tempo    { width: 175px; min-width: 175px; white-space: nowrap; }
.col-kuota    { width:  90px; min-width:  80px; }
.col-paket    { width: 150px; min-width: 150px; }
.col-harga    { width: 110px; min-width:  90px; }
.col-status   { width: 140px; min-width: 120px; }
.col-aksi     { width:  90px; min-width:  80px; }

.debt-note-cell {
  display: block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.debt-settle-btn {
  min-width: 70px;
  min-height: 28px;
  margin: 10px 0;
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

  .debt-ledger__hero {
    padding: 16px 16px 14px;
  }

  .debt-ledger__hero-icon {
    width: 36px;
    height: 36px;
    border-radius: 12px;
  }

  .debt-ledger__hero-subtitle {
    font-size: 0.8rem;
  }

  .debt-ledger__hero-action {
    width: 100%;
  }

  .debt-overview-grid {
    grid-template-columns: 1fr;
  }

  .debt-table-scroll {
    margin-inline: -4px;
  }
}
</style>
