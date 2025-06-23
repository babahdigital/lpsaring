<script setup lang="ts">
import { useNuxtApp } from '#app'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useApiFetch } from '~/composables/useApiFetch'

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
const { mobile } = useDisplay()

const transactions = ref<Transaction[]>([])
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const sortBy = ref<any[]>([])

const snackbar = reactive({
  show: false,
  text: '',
  color: 'info',
  timeout: 3000,
})

const downloadingInvoice = ref<string | null>(null)

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
  if (mobile.value) {
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

const { data: apiResponse, pending: loading, error: fetchError, refresh: _loadItems } = useApiFetch<ApiResponse>(
  () => `/users/me/transactions?${queryParams.value.toString()}`,
  {
    method: 'GET',
    watch: [queryParams],
    default: () => ({
      success: false,
      transactions: [],
      pagination: {
        page: 1,
        per_page: itemsPerPage.value,
        total_pages: 0,
        total_items: 0,
        has_prev: false,
        has_next: false,
        prev_num: null,
        next_num: null,
      },
    }),
  },
)

watch(apiResponse, (newData) => {
  // PERBAIKAN: Pengecekan boolean eksplisit
  if (newData?.success === true && Array.isArray(newData.transactions)) {
    transactions.value = newData.transactions

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
  snackbar.text = `Memulai download invoice ${midtransOrderId}...`
  snackbar.color = 'info'
  snackbar.show = true

  const invoiceUrl = `/transactions/${midtransOrderId}/invoice`

  try {
    const blob = await $api<Blob>(invoiceUrl, {
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

    snackbar.text = `Invoice ${midtransOrderId} berhasil diunduh.`
    snackbar.color = 'success'
    snackbar.show = true
  }
  catch (err: any) {
    // PERBAIKAN: Mengganti || dengan ?? untuk nilai fallback
    const message = err.data?.message ?? err.message ?? 'Gagal mengunduh invoice.'
    snackbar.text = message
    snackbar.color = 'error'
    snackbar.show = true
  }
  finally {
    downloadingInvoice.value = null
  }
}

onMounted(() => {
  // Pemanggilan data awal sudah ditangani oleh `watch` pada `useApiFetch`
})
useHead({ title: 'Riwayat Transaksi' })
</script>

<template>
  <VContainer fluid>
    <VRow>
      <VCol cols="12">
        <h1 class="text-h5 mb-4">
          Riwayat Transaksi
        </h1>
        <VCard>
          <VCardText>
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
              <div v-if="mobile" class="d-flex flex-column gap-3">
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

                <div v-if="loading" class="d-flex flex-column gap-3">
                  <VSkeletonLoader
                    v-for="i in 3"
                    :key="i"
                    type="card"
                  />
                </div>

                <!-- Pagination Mobile -->
                <VPagination
                  v-if="totalItems > 0"
                  v-model="currentPage"
                  :length="Math.ceil(totalItems / itemsPerPage)"
                  density="comfortable"
                  rounded="circle"
                  class="mt-4"
                />
              </div>

              <!-- Tampilan Desktop (Tabel) -->
              <VDataTableServer
                v-else
                :headers="headers"
                :items="transactions"
                :items-length="totalItems"
                :loading="loading"
                :items-per-page="itemsPerPage"
                :page="currentPage"
                density="compact"
                class="elevation-1"
                item-value="id"
                :items-per-page-options="[
                  { value: 10, title: '10' },
                  { value: 25, title: '25' },
                  { value: 50, title: '50' },
                ]"
                @update:options="handleOptionsUpdate"
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

    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="snackbar.timeout"
    >
      {{ snackbar.text }}
      <template #actions>
        <VBtn
          color="white"
          variant="text"
          @click="snackbar.show = false"
        >
          Tutup
        </VBtn>
      </template>
    </VSnackbar>
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
</style>
