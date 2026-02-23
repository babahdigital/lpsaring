<script setup lang="ts">
import type { AsyncData } from '#app'
import { useNuxtApp, useRuntimeConfig } from '#app'
import { computed, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useApiFetch } from '~/composables/useApiFetch'
import type { UserQuotaResponse } from '~/types/user'
import { useDebtSettlementPayment } from '~/composables/useDebtSettlementPayment'
import { useSnackbar } from '@/composables/useSnackbar'

// --- Tipe Data ---
interface Transaction {
  id: string
  midtrans_order_id: string
  package_name: string
  package_price: number | null
  amount: number
  status: 'PENDING' | 'PAID' | 'SETTLEMENT' | 'EXPIRED' | 'CANCELLED' | 'FAILED' | 'SUCCESS' | string
  payment_method: string | null
  created_at: string | null
  updated_at: string | null
  payment_expiry_time: string | null
  payment_settlement_time: string | null
  payment_va_number: string | null
  payment_biller_code: string | null
  payment_bill_key: string | null
}

interface PaginationInfo {
  page: number
  per_page: number
  total_pages: number
  total_items: number
  has_prev: boolean
  has_next: boolean
  prev_num: number | null
  next_num: number | null
}

interface ApiResponse {
  success: boolean
  transactions: Transaction[]
  pagination: PaginationInfo
  message?: string
}

// --- State & Config ---
const { $api } = useNuxtApp()
const runtimeConfig = useRuntimeConfig()
const { mobile } = useDisplay()
const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? mobile.value : false))

const transactions = ref<Transaction[]>([])
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const sortBy = ref<any[]>([])

const { add: addSnackbar } = useSnackbar()

function toast(type: 'success' | 'error' | 'info' | 'warning', text: string, title?: string) {
  addSnackbar({
    type,
    title: title ?? (type === 'success' ? 'Berhasil' : type === 'error' ? 'Gagal' : type === 'warning' ? 'Peringatan' : 'Info'),
    text,
  })
}

const downloadingInvoice = ref<string | null>(null)

const { paying: debtPaying, pay: payDebt } = useDebtSettlementPayment()

function payManualDebtItem(debtId: string) {
  if (typeof debtId !== 'string' || debtId.trim() === '')
    return
  void payDebt(debtId)
}

// --- Data Tunggakan Kuota (untuk tombol Lunasi di Riwayat) ---
const quotaApiUrl = computed(() => '/users/me/quota')
const { data: quotaData } = useApiFetch<UserQuotaResponse>(
  quotaApiUrl,
  {
    server: false,
    key: 'userQuotaDataRiwayat',
    default: () => ({
      success: false,
      total_quota_purchased_mb: 0,
      total_quota_used_mb: 0,
      remaining_mb: 0,
      quota_debt_auto_mb: 0,
      quota_debt_manual_mb: 0,
      quota_debt_total_mb: 0,
      quota_debt_total_estimated_rp: 0,
      hotspot_username: '...',
      last_sync_time: null,
      is_unlimited_user: false,
      quota_expiry_date: null,
    }),
    immediate: true,
    watch: false,
  },
)

const debtAutoMb = computed(() => Number(quotaData.value?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(quotaData.value?.quota_debt_manual_mb ?? 0))
const debtTotalMb = computed(() => Number(quotaData.value?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))
const debtEstimatedRp = computed(() => Number(quotaData.value?.quota_debt_total_estimated_rp ?? 0))

const showDebtCard = computed(() => {
  if (quotaData.value?.is_unlimited_user === true)
    return false
  return debtTotalMb.value > 0 && debtEstimatedRp.value > 0
})

function formatQuota(mbValue: number | null | undefined): string {
  const mb = Number(mbValue ?? 0)
  if (!Number.isFinite(mb) || mb <= 0)
    return '0 MB'
  if (mb < 1)
    return `${Math.round(mb * 1024).toLocaleString('id-ID')} KB`
  if (mb >= 1024)
    return `${(Math.round((mb / 1024) * 100) / 100).toLocaleString('id-ID', { maximumFractionDigits: 2 })} GB`
  return `${Math.round(mb).toLocaleString('id-ID')} MB`
}

// --- Data Tunggakan Manual (Per Tanggal) ---
interface QuotaDebtItem {
  id: string
  debt_date: string | null
  amount_mb: number
  paid_mb: number
  remaining_mb: number
  is_paid: boolean
  paid_at: string | null
  note: string | null
  created_at: string | null
}

interface QuotaDebtApiResponse {
  success: boolean
  items: QuotaDebtItem[]
  message?: string
}

const quotaDebtsApiUrl = computed(() => '/users/me/quota-debts?status=open')
const { data: quotaDebtsData, pending: quotaDebtsPending, error: quotaDebtsError, refresh: refreshQuotaDebts } = useApiFetch<QuotaDebtApiResponse>(
  quotaDebtsApiUrl,
  {
    server: false,
    key: 'userQuotaDebtsRiwayat',
    default: () => ({ success: false, items: [] }),
    immediate: true,
    watch: false,
  },
)

const quotaDebtItems = computed(() => {
  const items = quotaDebtsData.value?.items
  return Array.isArray(items) ? items : []
})

function formatDebtDate(dateStr: string | null | undefined): string {
  if (!dateStr)
    return '-'
  try {
    const date = new Date(dateStr)
    if (Number.isNaN(date.getTime()))
      return '-'
    return new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium' }).format(date)
  }
  catch {
    return '-'
  }
}

// --- Header Tabel (Responsif) ---
const headers = computed(() => {
  const baseHeaders = [
    { title: 'Tanggal', key: 'created_at', sortable: true },
    { title: 'Order ID', key: 'midtrans_order_id', sortable: false },
    { title: 'Nama Paket', key: 'package_name', sortable: false },
    { title: 'Jumlah', key: 'amount', sortable: true, align: 'end' },
    { title: 'Status', key: 'status', sortable: true, align: 'center' },
    { title: 'Aksi', key: 'actions', sortable: false, align: 'center' },
  ]

  // Sembunyikan kolom tertentu di mobile
  if (isMobile.value) {
    return baseHeaders.filter(header =>
      header.key !== 'midtrans_order_id'
      && header.key !== 'package_name',
    )
  }

  return baseHeaders
})

// --- Logika untuk Fetch Data ---
const queryParams = computed(() => {
  const params = new URLSearchParams()
  params.append('page', currentPage.value.toString())
  params.append('per_page', itemsPerPage.value.toString())

  // PERBAIKAN: Pengecekan eksplisit untuk properti dari 'any'
  if (sortBy.value.length > 0 && typeof sortBy.value[0].key === 'string' && typeof sortBy.value[0].order === 'string') {
    params.append('sort_by', sortBy.value[0].key)
    params.append('sort_order', sortBy.value[0].order)
  }

  return params
})

const apiUrl = computed(() => `/users/me/transactions?${queryParams.value.toString()}`)

const apiRequest = useApiFetch(apiUrl, {
  method: 'GET',
  watch: [queryParams],
}) as AsyncData<ApiResponse, any>

const { data: apiResponse, pending: loading, error: fetchError, refresh: _loadItems } = apiRequest

const hasLoadedOnce = ref(false)
const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)

const normalizedResponse = computed<ApiResponse | null>(() => apiResponse.value as ApiResponse | null)

watch(normalizedResponse, (newData) => {
  // PERBAIKAN: Pengecekan boolean eksplisit
  if (newData?.success === true && Array.isArray(newData.transactions)) {
    transactions.value = newData.transactions
    hasLoadedOnce.value = true

    // PERBAIKAN: Pengecekan null eksplisit
    if (newData.pagination != null) {
      totalItems.value = newData.pagination.total_items
      currentPage.value = newData.pagination.page
      itemsPerPage.value = newData.pagination.per_page
    }
  }
  // PERBAIKAN: Pengecekan null dan boolean eksplisit
  else if (newData != null && newData.success === false) {
    transactions.value = []
    totalItems.value = 0
    hasLoadedOnce.value = true
  }
}, { immediate: true })

function handleOptionsUpdate({ page, itemsPerPage: limit, sortBy: newSortBy }: {
  page: number
  itemsPerPage: number
  sortBy: any[]
}) {
  currentPage.value = page
  itemsPerPage.value = limit
  sortBy.value = newSortBy
}

// --- Helper Functions ---
function formatDateTime(dateTimeString: string | null | undefined): string {
  // PERBAIKAN: Pengecekan null eksplisit
  if (dateTimeString == null)
    return '-'

  try {
    const date = new Date(dateTimeString)
    return Number.isNaN(date.getTime())
      ? 'Tanggal Invalid'
      : date.toLocaleString('id-ID', {
          day: '2-digit',
          month: '2-digit',
          year: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        }).replace(/\./g, ':').replace(',', '')
  }
  catch {
    return 'Error Format'
  }
}

function formatCurrency(value: number | null | undefined): string {
  const numValue = Number(value ?? 0)
  return Number.isNaN(numValue)
    ? 'Jumlah Invalid'
    : new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(numValue)
}

function getStatusColor(status: string | undefined | null): string {
  const upperStatus = status?.toUpperCase()
  switch (upperStatus) {
    case 'PAID':
    case 'SETTLEMENT':
    case 'SUCCESS':
      return 'success'
    case 'PENDING':
      return 'warning'
    case 'EXPIRED':
      return 'error'
    case 'CANCELLED':
    case 'FAILED':
      return 'error'
    default:
      return 'default'
  }
}

function getStatusText(status: string | undefined | null): string {
  const upperStatus = status?.toUpperCase()
  switch (upperStatus) {
    case 'PAID': return 'Dibayar'
    case 'SETTLEMENT': return 'Selesai'
    case 'SUCCESS': return 'Sukses'
    case 'PENDING': return 'Menunggu'
    case 'EXPIRED': return 'Kedaluwarsa'
    case 'CANCELLED': return 'Dibatalkan'
    case 'FAILED': return 'Gagal'
    // PERBAIKAN: Mengganti || dengan ??
    default: return status ?? 'Tidak Diketahui'
  }
}

function isDownloadable(status: string | undefined | null): boolean {
  const upperStatus = status?.toUpperCase()
  // PERBAIKAN: Mengganti || dengan ??
  return ['SUCCESS', 'SETTLEMENT', 'PAID'].includes(upperStatus ?? '')
}

async function downloadInvoice(midtransOrderId: string) {
  downloadingInvoice.value = midtransOrderId
  toast('info', `Memulai download invoice ${midtransOrderId}...`)

  const invoicePath = `/transactions/${midtransOrderId}/invoice`
  const invoiceDownloadUrl = `${(runtimeConfig.public.apiBaseUrl ?? '/api').replace(/\/$/, '')}${invoicePath}`

  try {
    if (import.meta.client) {
      const newWindow = window.open(invoiceDownloadUrl, '_blank')
      if (newWindow) {
        toast('success', `Invoice ${midtransOrderId} sedang dibuka di tab baru.`)
        return
      }
    }

    const blob = await $api<Blob>(invoicePath, {
      method: 'GET',
      responseType: 'blob',
    })

    // PERBAIKAN: Pengecekan null eksplisit
    if (blob == null || blob.size === 0) {
      throw new Error('Gagal menerima data file dari server (blob kosong).')
    }

    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `invoice-${midtransOrderId}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objectUrl)

    toast('success', `Invoice ${midtransOrderId} berhasil diunduh.`)
  }
  catch (err: any) {
    // PERBAIKAN: Mengganti || dengan ?? untuk nilai fallback
    const message = err.data?.message ?? err.message ?? 'Gagal mengunduh invoice.'
    toast('error', message)
  }
  finally {
    downloadingInvoice.value = null
  }
}

onMounted(() => {
  isHydrated.value = true
  // Pemanggilan data awal sudah ditangani oleh `watch` pada `useApiFetch`
})
useHead({ title: 'Riwayat Transaksi' })
</script>

<template>
  <VContainer fluid>
    <VRow>
      <VCol cols="12">
        <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-4">
          <h1 class="text-h5 mb-0">
            Riwayat Transaksi
          </h1>

          <VBtn
            v-if="showDebtCard"
            size="small"
            color="warning"
            variant="flat"
            prepend-icon="tabler-credit-card"
            :loading="debtPaying"
            :disabled="debtPaying"
            @click="payDebt"
          >
            Lunasi Semua
          </VBtn>
        </div>

        <VCard v-if="showDebtCard" variant="tonal" class="mb-4">
          <VCardText class="py-4">
            <div class="d-flex align-center justify-space-between flex-wrap gap-2">
              <div>
                <div class="text-subtitle-1 font-weight-medium">
                  Tunggakan Kuota
                </div>
                <div class="text-caption text-medium-emphasis">
                  Estimasi
                </div>
              </div>

              <div class="text-body-1 font-weight-medium">
                {{ formatCurrency(debtEstimatedRp) }}
              </div>
            </div>

            <VList class="debt-card-list mt-3" density="compact">
              <VListItem v-if="debtTotalMb > 0" class="py-2">
                <template #prepend>
                  <VAvatar color="info" variant="tonal" rounded size="38" class="me-1">
                    <VIcon icon="tabler-robot" size="22" />
                  </VAvatar>
                </template>
                <VListItemTitle class="me-2">Tunggakan otomatis</VListItemTitle>
                <template #append>
                  <span class="text-body-1 font-weight-medium">{{ formatQuota(debtAutoMb) }}</span>
                </template>
              </VListItem>

              <VDivider v-if="debtManualMb > 0" class="my-0" />

              <VListItem v-if="debtManualMb > 0" class="py-2">
                <template #prepend>
                  <VAvatar color="secondary" variant="tonal" rounded size="38" class="me-1">
                    <VIcon icon="tabler-hand-stop" size="22" />
                  </VAvatar>
                </template>
                <VListItemTitle class="me-2">Tunggakan manual</VListItemTitle>
                <template #append>
                  <span class="text-body-1 font-weight-medium">{{ formatQuota(debtManualMb) }}</span>
                </template>
              </VListItem>
            </VList>

            <div class="mt-4">
              <div class="text-subtitle-2 font-weight-medium mb-2">
                Hutang manual per tanggal
              </div>

              <VAlert v-if="quotaDebtsError" type="error" variant="tonal" density="compact" class="mb-3">
                Gagal memuat data hutang per tanggal.
              </VAlert>

              <div v-if="quotaDebtsPending" class="d-flex justify-center py-4">
                <VProgressCircular indeterminate color="primary" />
              </div>

              <div v-else class="debt-ledger-scroll">
                <VTable density="compact" class="debt-ledger-table">
                  <colgroup>
                    <col style="width: 124px;">
                    <col style="width: 110px;">
                    <col style="width: 110px;">
                    <col style="width: 110px;">
                    <col style="width: 260px;">
                    <col style="width: 110px;">
                  </colgroup>
                  <thead>
                    <tr>
                      <th class="text-no-wrap">Tanggal</th>
                      <th class="text-end text-no-wrap">Jumlah</th>
                      <th class="text-end text-no-wrap">Dibayar</th>
                      <th class="text-end text-no-wrap">Sisa</th>
                      <th class="text-no-wrap">Catatan</th>
                      <th class="text-end text-no-wrap">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="it in quotaDebtItems" :key="it.id">
                      <td class="text-no-wrap">{{ formatDebtDate(it.debt_date) }}</td>
                      <td class="text-end text-no-wrap">{{ formatQuota(it.amount_mb) }}</td>
                      <td class="text-end text-no-wrap">{{ formatQuota(it.paid_mb) }}</td>
                      <td class="text-end font-weight-medium text-no-wrap">{{ formatQuota(it.remaining_mb) }}</td>
                      <td class="debt-ledger-note">{{ it.note || '-' }}</td>
                      <td class="text-end text-no-wrap">
                        <VBtn
                          v-if="it.remaining_mb > 0"
                          size="x-small"
                          color="warning"
                          variant="tonal"
                          prepend-icon="tabler-credit-card"
                          :loading="debtPaying"
                          :disabled="debtPaying"
                          @click="payManualDebtItem(it.id)"
                        >
                          Lunasi
                        </VBtn>
                      </td>
                    </tr>
                    <tr v-if="quotaDebtItems.length === 0">
                      <td colspan="6" class="text-center text-medium-emphasis py-3">
                        Tidak ada hutang manual yang belum lunas.
                      </td>
                    </tr>
                  </tbody>
                </VTable>
              </div>
            </div>
          </VCardText>
        </VCard>

        <VCard>
          <VCardText>
            <VProgressLinear
              v-if="showSilentRefreshing"
              indeterminate
              color="primary"
              height="2"
              class="mb-4"
            />

            <VAlert
              v-if="fetchError"
              type="error"
              variant="tonal"
              prominent
              class="mb-4"
            >
              Gagal memuat riwayat transaksi.
              <div v-if="fetchError.message" class="mt-2 text-caption">
                Pesan: {{ fetchError.message }}
              </div>
              <div v-if="fetchError.data?.message" class="mt-1 text-caption">
                Detail: {{ fetchError.data.message }}
              </div>
              <div v-else-if="typeof fetchError.data === 'string'" class="mt-1 text-caption">
                Detail: {{ fetchError.data }}
              </div>
            </VAlert>

            <ClientOnly>
              <!-- Tampilan Mobile (Card) -->
              <div v-if="isMobile" class="d-flex flex-column gap-3">
                <VCard
                  v-for="item in transactions"
                  :key="item.id"
                  class="elevation-1"
                >
                  <VCardText class="d-flex flex-column gap-2">
                    <div class="d-flex justify-space-between">
                      <span class="font-weight-bold">Tanggal:</span>
                      <span>{{ formatDateTime(item.created_at) }}</span>
                    </div>

                    <div class="d-flex justify-space-between">
                      <span class="font-weight-bold">Jumlah:</span>
                      <span>{{ formatCurrency(item.amount) }}</span>
                    </div>

                    <div class="d-flex justify-space-between align-center">
                      <span class="font-weight-bold">Status:</span>
                      <VChip :color="getStatusColor(item.status)" label>
                        {{ getStatusText(item.status) }}
                      </VChip>
                    </div>

                    <div class="d-flex justify-end mt-2">
                      <VBtn
                        size="small"
                        variant="outlined"
                        :color="isDownloadable(item.status) ? 'primary' : 'grey-lighten-1'"
                        :disabled="!isDownloadable(item.status) || downloadingInvoice === item.midtrans_order_id"
                        :loading="downloadingInvoice === item.midtrans_order_id"
                        prepend-icon="tabler-download"
                        @click="downloadInvoice(item.midtrans_order_id)"
                      >
                        Invoice
                      </VBtn>
                    </div>
                  </VCardText>
                </VCard>

                <div v-if="transactions.length === 0 && !loading" class="text-center py-4">
                  Belum ada riwayat transaksi.
                </div>

                <div v-if="showInitialSkeleton" class="d-flex flex-column gap-3">
                  <VSkeletonLoader
                    v-for="i in 3"
                    :key="i"
                    type="card"
                  />
                </div>

                <!-- Pagination Mobile -->
                <TablePagination
                  v-if="totalItems > 0"
                  :page="currentPage"
                  :items-per-page="itemsPerPage"
                  :total-items="totalItems"
                  @update:page="val => (currentPage = val)"
                />
              </div>

              <!-- Tampilan Desktop (Tabel) -->
              <div v-else>
                <div class="pb-2">
                  <DataTableToolbar
                    v-model:items-per-page="itemsPerPage"
                    :show-search="false"
                    @update:items-per-page="() => (currentPage = 1)"
                  />
                </div>

                <VDataTableServer
                  :headers="headers"
                  :items="transactions"
                  :items-length="totalItems"
                  :loading="showInitialSkeleton"
                  :items-per-page="itemsPerPage"
                  :page="currentPage"
                  density="compact"
                  class="elevation-1"
                  item-value="id"
                  @update:options="handleOptionsUpdate"
                  hide-default-footer
                >
                <template #[`item.created_at`]="props">
                  {{ formatDateTime(props.item.created_at) }}
                </template>

                <template #[`item.amount`]="props">
                  {{ formatCurrency(props.item.amount) }}
                </template>

                <template #[`item.status`]="props">
                  <VChip :color="getStatusColor(props.item.status)" label>
                    {{ getStatusText(props.item.status) }}
                  </VChip>
                </template>

                <template #[`item.actions`]="props">
                  <VBtn
                    icon
                    size="x-small"
                    variant="text"
                    :color="isDownloadable(props.item.status) ? 'primary' : 'grey-lighten-1'"
                    :disabled="!isDownloadable(props.item.status) || downloadingInvoice === props.item.midtrans_order_id"
                    :loading="downloadingInvoice === props.item.midtrans_order_id"
                    title="Download Invoice"
                    @click="downloadInvoice(props.item.midtrans_order_id)"
                  >
                    <VIcon v-if="downloadingInvoice !== props.item.midtrans_order_id" size="18">
                      tabler-download
                    </VIcon>
                  </VBtn>
                </template>

                <template #no-data>
                  <div v-if="!loading" class="text-center py-4">
                    Belum ada riwayat transaksi.
                  </div>
                </template>

                <template #loading>
                  <VSkeletonLoader type="table-row@5" />
                </template>
                </VDataTableServer>
              </div>

              <TablePagination
                v-if="!isMobile && totalItems > 0"
                :page="currentPage"
                :items-per-page="itemsPerPage"
                :total-items="totalItems"
                @update:page="val => (currentPage = val)"
              />

              <template #placeholder>
                <VSkeletonLoader type="table@1" />
                <div class="text-center pa-4 text-caption">
                  Memuat tabel data...
                </div>
              </template>
            </ClientOnly>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

  </VContainer>
</template>

<style scoped>
/* Hapus fixed width untuk responsif */
.v-data-table {
  width: 100%;
  overflow-x: auto;
}

.v-alert div.text-caption {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 100px;
  overflow-y: auto;
  background-color: rgba(0,0,0,0.05);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-top: 4px;
}

.v-data-table .v-btn {
  margin: 0 2px;
}

/* Responsif teks di mobile */
@media (max-width: 600px) {
  .v-card-text > div {
    font-size: 0.875rem;
  }

  .v-btn {
    font-size: 0.75rem;
  }
}

.debt-ledger-scroll {
  overflow-x: auto;
  padding-block-end: 6px;
}

/* VTable merender <div class="v-table__wrapper"><table>... */
.debt-ledger-table :deep(.v-table__wrapper > table) {
  min-width: 740px;
  width: 100%;
  table-layout: fixed;
}

.debt-ledger-note {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
