<script setup lang="ts">
import type { VDataTableServer } from 'vuetify/components'
import { computed, onMounted, ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'

// --- Tipe Data ---
interface Transaction {
  id: string
  order_id: string
  midtrans_transaction_id?: string | null
  amount: number
  status: 'PENDING' | 'SUCCESS' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'UNKNOWN'
  created_at: string
  updated_at?: string | null
  payment_method?: string | null
  payment_time?: string | null
  expiry_time?: string | null
  va_number?: string | null
  payment_code?: string | null
  biller_code?: string | null
  qr_code_url?: string | null
  user: { full_name: string, phone_number: string }
  package_name: string
  midtrans_notification_payload?: unknown | null
  events?: Array<{
    id: string
    created_at: string | null
    source: string
    event_type: string
    status: string | null
    payload: unknown | null
  }> | null
}
interface UserSelectItem {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN' // Menambahkan 'role'
}

// --- State Management ---
const { $api } = useNuxtApp()

const options = ref<InstanceType<typeof VDataTableServer>['$props']['options']>({
  page: 1,
  itemsPerPage: 10,
  sortBy: [{ key: 'created_at', order: 'desc' }],
})

const exportLoading = ref(false)
const search = ref('')
const selectedUser = ref<UserSelectItem | null>(null)
const tempSelectedUser = ref<UserSelectItem | null>(null)

const startDate = ref<Date | null>(null)
const endDate = ref<Date | null>(null)
const isStartDateMenuOpen = ref(false)
const isEndDateMenuOpen = ref(false)

const isUserFilterDialogOpen = ref(false)
const userList = ref<UserSelectItem[]>([])
const userSearch = ref('')

const { add: addSnackbar } = useSnackbar()
const isHydrated = ref(false)
const hasLoadedOnce = ref(false)

const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)

// --- Data Fetching Reaktif dengan useAsyncData ---
const queryParams = computed(() => ({
  page: options.value.page,
  itemsPerPage: options.value.itemsPerPage,
  sortBy: options.value.sortBy?.[0]?.key ?? 'created_at',
  sortOrder: options.value.sortBy?.[0]?.order ?? 'desc',
  search: search.value,
  user_id: selectedUser.value?.id,
  start_date: startDate.value ? startDate.value.toISOString().split('T')[0] : undefined,
  end_date: endDate.value ? endDate.value.toISOString().split('T')[0] : undefined,
}))

const { data: transactionData, pending: loading, error, refresh } = useAsyncData(
  'fetch-transactions',
  () => $api<{ items: Transaction[], totalItems: number }>('/admin/transactions', {
    params: queryParams.value,
  }),
  {
    watch: [queryParams],
  },
)

onMounted(() => {
  isHydrated.value = true
})

// Perbaikan baris 88 (sesuai error user baris 75): Menangani nilai nullable number secara eksplisit
const transactions = computed(() => transactionData.value?.items || [])
const totalTransactions = computed(() => transactionData.value?.totalItems ?? 0) // Menggunakan ?? untuk explicit nullish check

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const data = (err as { data?: unknown }).data
    if (data && typeof data === 'object' && 'message' in data) {
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string' && message !== '')
        return message
    }
    if ('message' in err) {
      const message = (err as { message?: unknown }).message
      if (typeof message === 'string' && message !== '')
        return message
    }
  }
  return fallback
}

watch(error, (newError) => {
  if (newError !== null && newError !== undefined)
    showSnackbar(extractErrorMessage(newError, 'Gagal memuat data transaksi'), 'error')
})

watch(loading, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })

// --- Konfigurasi & Format ---
const headers = [
  { title: 'NAMA PENGGUNA', key: 'user.full_name', sortable: false, width: '200px' },
  { title: 'ID INVOICE', key: 'order_id', sortable: true, width: '200px' },
  { title: 'PAKET', key: 'package_name', sortable: false, width: '180px' },
  { title: 'METODE', key: 'payment_method', sortable: false, width: '140px' },
  { title: 'JUMLAH', key: 'amount', sortable: true, align: 'end', width: '160px' },
  { title: 'STATUS', key: 'status', sortable: true, width: '140px' },
  { title: 'KADALUARSA', key: 'expiry_time', sortable: false, width: '200px' },
  { title: 'TANGGAL', key: 'created_at', sortable: true, width: '200px' },
  { title: 'AKSI', key: 'actions', sortable: false, width: '160px' },
]

const statusColorMap: Record<Transaction['status'], string> = {
  SUCCESS: 'success',
  PENDING: 'warning',
  FAILED: 'error',
  EXPIRED: 'error',
  CANCELLED: 'info',
  UNKNOWN: 'secondary',
}

const getStatusColor = (status: Transaction['status']) => statusColorMap[status]

function getStatusVariant(status: Transaction['status']) {
  if (status === 'SUCCESS')
    return 'flat'
  if (status === 'PENDING')
    return 'outlined'
  // Kadaluarsa/Gagal/Dibatalkan/Belum mulai dibuat lebih jelas
  return 'tonal'
}

function formatStatus(status: string) {
  const statusMap: Record<string, string> = {
    SUCCESS: 'Sukses',
    PENDING: 'Menunggu',
    FAILED: 'Gagal',
    EXPIRED: 'Kadaluarsa',
    CANCELLED: 'Dibatalkan',
    UNKNOWN: 'Belum Mulai',
  }
  return statusMap[status] || status
}

function formatPaymentMethod(method?: string | null): string {
  if (method == null || method === '')
    return '-'
  const m = method.toUpperCase()
  const map: Record<string, string> = {
    QRIS: 'QRIS',
    GOPAY: 'GoPay',
    SHOPEEPAY: 'ShopeePay',
    BANK_TRANSFER: 'VA',
    CREDIT_CARD: 'Kartu',
    CSTORE: 'Konter',
    ALFAMART: 'Alfamart',
    INDOMARET: 'Indomaret',
  }
  return map[m] ?? method
}

function openAdminReportPdf(orderId: string) {
  if (!orderId)
    return
  window.open(`/api/admin/transactions/${encodeURIComponent(orderId)}/report.pdf`, '_blank', 'noopener')
}

function printAdminReport(orderId: string) {
  if (!orderId)
    return

  const url = `/api/admin/transactions/${encodeURIComponent(orderId)}/report.pdf`
  const popup = window.open(url, '_blank', 'noopener')
  // Best-effort: beberapa browser blok auto-print untuk PDF, jadi tetap buka tabnya.
  if (!popup)
    return

  const timer = window.setInterval(() => {
    try {
      if (popup.closed) {
        window.clearInterval(timer)
        return
      }
      if (popup.document?.readyState === 'complete') {
        window.clearInterval(timer)
        popup.focus()
        popup.print()
      }
    }
    catch {
      // cross-origin / PDF viewer; abaikan
      window.clearInterval(timer)
    }
  }, 500)
}

const expandedOrderIds = ref<string[]>([])
const detailCache = ref<Record<string, Transaction>>({})
const detailLoading = ref<Record<string, boolean>>({})

async function fetchTransactionDetail(orderId: string) {
  if (!orderId)
    return
  if (detailCache.value[orderId])
    return
  if (detailLoading.value[orderId])
    return

  detailLoading.value = { ...detailLoading.value, [orderId]: true }
  try {
    const detail = await $api<Transaction>(`/admin/transactions/${encodeURIComponent(orderId)}/detail`)
    detailCache.value = { ...detailCache.value, [orderId]: detail }
  }
  catch (err) {
    showSnackbar(extractErrorMessage(err, 'Gagal memuat detail transaksi'), 'error')
  }
  finally {
    detailLoading.value = { ...detailLoading.value, [orderId]: false }
  }
}

async function toggleDetail(orderId: string) {
  const current = expandedOrderIds.value
  const isExpanded = current.includes(orderId)
  expandedOrderIds.value = isExpanded ? current.filter(id => id !== orderId) : [...current, orderId]
  if (!isExpanded)
    await fetchTransactionDetail(orderId)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function formatMaybeDateTime(value: unknown): string {
  if (typeof value !== 'string' || value === '')
    return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()))
    return value
  return formatDateTime(value)
}

// Fungsi baru untuk format nomor telepon
function formatPhoneNumberForDisplay(phoneNumber: string | null) {
  // Perbaikan baris 115: Menambahkan pengecekan eksplisit untuk null/undefined/kosong
  if (phoneNumber === null || phoneNumber === undefined || phoneNumber === '')
    return ''
  if (phoneNumber.startsWith('+62'))
    return `0${phoneNumber.substring(3)}`

  return phoneNumber
}

const formatCurrency = (value: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(value)
const formatDateTime = (dateString: string) => new Date(dateString).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const formatDate = (date: Date | null) => date ? new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }) : ''

// Perbaikan baris 209: Menambahkan perbandingan eksplisit dengan null
const hasActiveFilters = computed(() => selectedUser.value !== null || startDate.value !== null || endDate.value !== null)
const formattedDateRangeForChip = computed(() => {
  if (startDate.value === null && endDate.value === null) // Perbaikan baris 218
    return ''
  const start = startDate.value ? formatDate(startDate.value) : '...'
  const end = endDate.value ? formatDate(endDate.value) : '...'
  return `${start} - ${end}`
})

function getPhoneNumberVariationsJS(query: string): string[] {
  const cleaned = query.replace(/\D/g, '')
  if (!cleaned)
    return []
  const variations = new Set<string>()
  if (cleaned.startsWith('08'))
    variations.add(`+62${cleaned.substring(1)}`)

  if (cleaned.startsWith('628'))
    variations.add(`+${cleaned}`)

  if (cleaned.startsWith('628'))
    variations.add(`+62${cleaned.substring(2)}`)

  variations.add(cleaned)
  return Array.from(variations)
}

const filteredUserList = computed(() => {
  if (userSearch.value === null || userSearch.value === '') // Perbaikan: Pengecekan eksplisit untuk userSearch.value
    return userList.value
  const queryLower = userSearch.value.toLowerCase()

  const phoneVariations = getPhoneNumberVariationsJS(userSearch.value)

  return userList.value.filter((user) => {
    if (user.full_name.toLowerCase().includes(queryLower))
      return true

    if (phoneVariations.length > 0)
      return phoneVariations.some(variation => user.phone_number?.includes(variation) === true)

    return user.phone_number?.includes(queryLower) === true
  })
})

// --- Logika & Fungsi ---
function showSnackbar(text: string, type: 'success' | 'error' | 'warning' = 'success') {
  const titleMap: Record<typeof type, string> = {
    success: 'Berhasil',
    error: 'Gagal',
    warning: 'Perhatian',
  }

  addSnackbar({
    type,
    title: titleMap[type],
    text,
  })
}

const applyFilter = () => refresh()
function clearAllFilters() {
  search.value = ''
  startDate.value = null
  endDate.value = null
  selectedUser.value = null
  tempSelectedUser.value = null
}
function clearUserFilter() {
  selectedUser.value = null
  tempSelectedUser.value = null
}
function clearDateFilter() {
  startDate.value = null
  endDate.value = null
}
function clearStartDate() {
  startDate.value = null
  endDate.value = null
}
function clearEndDate() {
  endDate.value = null
}

async function openUserFilterDialog() {
  isUserFilterDialogOpen.value = true
  tempSelectedUser.value = selectedUser.value
  if (userList.value.length > 0)
    return
  try {
    const responseData = await $api<{ items: UserSelectItem[] }>('/admin/users?all=true')
    // Perbaikan baris 260: Menambahkan pengecekan eksplisit untuk responseData dan Array.isArray
    if (responseData !== null && responseData !== undefined && Array.isArray(responseData.items)) {
      // Filter hanya untuk peran 'USER'
      userList.value = responseData.items.filter(user => user.role === 'USER')
    }
    else {
      // Perbaikan baris 230 (sesuai error user baris 230): Pengecekan eksplisit ini sudah ada
      userList.value = []
    }
  }
  catch (e: unknown) {
    showSnackbar(extractErrorMessage(e, 'Gagal memuat daftar pengguna.'), 'error')
    userList.value = []
  }
}

async function ensureUsersLoaded() {
  if (userList.value.length > 0)
    return
  try {
    const responseData = await $api<{ items: UserSelectItem[] }>('/admin/users?all=true')
    if (responseData && Array.isArray(responseData.items))
      userList.value = responseData.items.filter(u => u.role === 'USER')
  }
  catch {
    userList.value = []
  }
}


const getUserInitials = (name: string) => name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()
function selectUser(user: UserSelectItem) {
  tempSelectedUser.value = user
}

function confirmUserSelection() {
  selectedUser.value = tempSelectedUser.value
  isUserFilterDialogOpen.value = false
  userSearch.value = ''
}

async function exportReport(format: 'pdf' | 'csv') {
  if (startDate.value === null) {
    showSnackbar('Pilih tanggal mulai terlebih dahulu', 'warning')
    return
  }
  exportLoading.value = true
  try {
    const start = startDate.value.toISOString().split('T')[0]
    const end = (endDate.value || startDate.value).toISOString().split('T')[0]
    const params = new URLSearchParams({ format, start_date: start, end_date: end })
    if (selectedUser.value !== null)
      params.append('user_id', selectedUser.value.id)
    const data = await $api<Blob>(`/admin/transactions/export?${params.toString()}`, { responseType: 'blob' as const })
    if (data === null || data === undefined)
      throw new Error('Tidak ada data laporan yang diterima')
    const blob = data instanceof Blob ? data : new Blob([data as BlobPart])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `laporan-transaksi-${start}-to-${end}.${format}`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    showSnackbar('Laporan berhasil diunduh', 'success')
  }
  catch (err: unknown) {
    showSnackbar(`Gagal mengunduh laporan: ${extractErrorMessage(err, 'Kesalahan tidak diketahui')}`, 'error')
  }
  finally {
    exportLoading.value = false
  }
}

useHead({ title: 'Laporan Penjualan' })
</script>

<template>
  <div class="transaction-manager">
    <VCard title="Manajemen Transaksi" class="elevation-3">
      <VCardText class="pa-6">
        <VRow class="d-flex flex-wrap gap-y-4 align-center">
          <VCol cols="12" sm="6" md="3" lg="3">
            <VTextField
              id="start-date-activator"
              :model-value="formatDate(startDate)"
              label="Tanggal Mulai"
              placeholder="Pilih tanggal"
              prepend-inner-icon="tabler-calendar"
              readonly
              clearable
              variant="outlined"
              class="date-field"
              :class="{ 'active-field': startDate !== null }"
              hide-details="auto"
              @click:clear="clearStartDate"
            />
            <VMenu
              v-model="isStartDateMenuOpen"
              activator="#start-date-activator"
              :close-on-content-click="false"
              location="bottom start"
              offset="10"
            >
              <client-only>
                <VDatePicker
                  v-model="startDate"
                  no-title
                  color="primary"
                  :max="new Date()"
                  show-adjacent-months
                  @update:model-value="isStartDateMenuOpen = false"
                />
              </client-only>
            </VMenu>
          </VCol>

          <VCol cols="12" sm="6" md="3" lg="3">
            <VTextField
              id="end-date-activator"
              :model-value="formatDate(endDate)"
              label="Tanggal Akhir"
              placeholder="Pilih tanggal"
              prepend-inner-icon="tabler-calendar"
              readonly
              clearable
              :disabled="startDate === null"
              variant="outlined"
              class="date-field"
              :class="{ 'active-field': endDate !== null }"
              hide-details="auto"
              @click:clear="clearEndDate"
            />
            <VMenu
              v-model="isEndDateMenuOpen"
              activator="#end-date-activator"
              :close-on-content-click="false"
              location="bottom start"
              offset="10"
            >
              <client-only>
                <VDatePicker
                  v-model="endDate"
                  no-title
                  color="primary"
                  :min="startDate"
                  :max="new Date()"
                  show-adjacent-months
                  @update:model-value="isEndDateMenuOpen = false"
                />
              </client-only>
            </VMenu>
          </VCol>

          <VCol cols="12" sm="6" md="3" lg="3">
            <VBtn
              block
              prepend-icon="tabler-user-search"
              variant="outlined"
              color="primary"
              height="56"
              class="filter-btn"
              @click="openUserFilterDialog"
            >
              <span class="text-truncate">Filter Pengguna</span>
            </VBtn>
          </VCol>

          <VCol cols="12" sm="6" md="3" lg="3" class="d-flex align-center gap-2 flex-wrap">
            <VBtn
              prepend-icon="tabler-filter"
              color="primary"
              height="56"
              class="action-btn flex-grow-1"
              @click="applyFilter"
            >
              Terapkan
            </VBtn>
            <VBtn
              prepend-icon="tabler-filter-off"
              variant="tonal"
              height="56"
              class="action-btn flex-grow-1"
              @click="clearAllFilters"
            >
              Reset
            </VBtn>
          </VCol>
        </VRow>

        <VRow v-if="hasActiveFilters === true" class="mt-4">
          <VCol cols="12" class="d-flex flex-wrap gap-2 align-center">
            <VChip
              v-if="selectedUser !== null"
              color="primary"
              closable
              prepend-icon="tabler-user"
              size="small"
              class="active-filter-chip"
              @click:close="clearUserFilter"
            >
              Pengguna: {{ selectedUser.full_name }}
            </VChip>

            <VChip
              v-if="startDate !== null || endDate !== null"
              color="primary"
              closable
              prepend-icon="tabler-calendar"
              size="small"
              class="active-filter-chip"
              @click:close="clearDateFilter"
            >
              Periode: {{ formattedDateRangeForChip }}
            </VChip>
          </VCol>
        </VRow>
      </VCardText>
      <VDivider />

      <VCardText class="py-4 px-6">
        <DataTableToolbar
          v-model:items-per-page="options.itemsPerPage"
          v-model:search="search"
          search-placeholder="Cari ID Invoice..."
          @update:items-per-page="() => (options.page = 1)"
        >
          <template #start>
            <VMenu offset-y>
              <template #activator="{ props }">
                <VBtn
                  color="primary"
                  v-bind="props"
                  prepend-icon="tabler-download"
                  variant="tonal"
                  class="export-btn"
                  :loading="exportLoading"
                >
                  Unduh Laporan
                </VBtn>
              </template>
              <VList density="compact">
                <VListItem @click="exportReport('pdf')">
                  <template #prepend>
                    <VIcon icon="tabler-file-type-pdf" class="text-error" />
                  </template>
                  <VListItemTitle>PDF</VListItemTitle>
                </VListItem>
                <VListItem @click="exportReport('csv')">
                  <template #prepend>
                    <VIcon icon="tabler-file-type-csv" class="text-success" />
                  </template>
                  <VListItemTitle>CSV</VListItemTitle>
                </VListItem>
              </VList>
            </VMenu>
          </template>
        </DataTableToolbar>
      </VCardText>
      <VProgressLinear
        v-if="showSilentRefreshing"
        indeterminate
        color="primary"
        height="2"
      />
      <div class="px-6 pb-6">
        <VDataTableServer
          v-model:items-per-page="options.itemsPerPage"
          v-model:page="options.page"
          v-model:sort-by="options.sortBy"
          v-model:expanded="expandedOrderIds"
          :headers="headers"
          :items="transactions"
          :items-length="totalTransactions"
          :loading="showInitialSkeleton"
          item-value="order_id"
          class="elevation-1 rounded data-table"
          hide-default-footer
        >
          <template #item.user.full_name="{ item }">
            <span class="font-weight-medium user-name">{{ item.user.full_name }}</span>
          </template>

          <template #item.amount="{ item }">
            <span class="font-weight-bold amount-value">{{ formatCurrency(item.amount) }}</span>
          </template>

          <template #item.status="{ item }">
            <VChip
              :color="getStatusColor(item.status as Transaction['status'])"
              size="small"
              :variant="getStatusVariant(item.status as Transaction['status'])"
              class="status-chip font-weight-bold"
            >
              {{ formatStatus(item.status) }}
            </VChip>
          </template>

          <template #item.created_at="{ item }">
            <span class="text-sm date-time">{{ formatDateTime(item.created_at) }}</span>
          </template>

          <template #item.payment_method="{ item }">
            <span class="text-sm">{{ formatPaymentMethod(item.payment_method) }}</span>
          </template>

          <template #item.expiry_time="{ item }">
            <span class="text-sm">{{ item.expiry_time ? formatDateTime(item.expiry_time) : '-' }}</span>
          </template>

          <template #item.actions="{ item }">
            <div class="d-flex align-center ga-1">
              <VBtn
                icon
                variant="text"
                size="small"
                :title="`Detail ${item.order_id}`"
                @click="toggleDetail(item.order_id)"
              >
                <VIcon icon="tabler-info-circle" />
              </VBtn>

              <VBtn
                v-if="item.status === 'SUCCESS'"
                icon
                variant="text"
                size="small"
                :title="`PDF Admin ${item.order_id}`"
                @click="openAdminReportPdf(item.order_id)"
              >
                <VIcon icon="tabler-file-type-pdf" />
              </VBtn>

              <VBtn
                v-if="item.status === 'SUCCESS'"
                icon
                variant="text"
                size="small"
                :title="`Print ${item.order_id}`"
                @click="printAdminReport(item.order_id)"
              >
                <VIcon icon="tabler-printer" />
              </VBtn>
            </div>
          </template>

          <template #expanded-row="{ columns, item }">
            <tr>
              <td :colspan="columns.length" class="pa-0">
                <div class="pa-4" style="background-color: rgba(var(--v-theme-on-surface), 0.02);">
                  <div v-if="detailLoading[item.order_id]" class="d-flex align-center ga-3">
                    <VProgressCircular indeterminate size="20" color="primary" />
                    <span class="text-medium-emphasis">Memuat detail transaksi...</span>
                  </div>

                  <div v-else>
                    <div class="detail-row">
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">ID Invoice</div>
                        <div class="font-weight-medium">{{ item.order_id }}</div>
                      </div>
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Pengguna</div>
                        <div class="font-weight-medium">{{ item.user.full_name }}</div>
                        <div class="text-caption text-medium-emphasis">{{ formatPhoneNumberForDisplay(item.user.phone_number) }}</div>
                      </div>
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Paket</div>
                        <div class="font-weight-medium">{{ item.package_name }}</div>
                      </div>
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Jumlah</div>
                        <div class="font-weight-medium">{{ formatCurrency(item.amount) }}</div>
                      </div>
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Metode</div>
                        <div class="font-weight-medium">{{ formatPaymentMethod(item.payment_method) }}</div>
                      </div>
                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Kadaluarsa</div>
                        <div class="font-weight-medium">{{ item.expiry_time ? formatDateTime(item.expiry_time) : '-' }}</div>
                      </div>
                    </div>

                    <VDivider class="my-4" />

                    <div v-if="detailCache[item.order_id]" class="detail-row">
                      <template v-if="item.status === 'SUCCESS'">
                        <div class="detail-item">
                          <div class="text-caption text-medium-emphasis">Midtrans Transaction ID</div>
                          <div class="font-weight-medium">{{ detailCache[item.order_id].midtrans_transaction_id || '-' }}</div>
                        </div>
                        <div class="detail-item">
                          <div class="text-caption text-medium-emphasis">Waktu Bayar</div>
                          <div class="font-weight-medium">{{ detailCache[item.order_id].payment_time ? formatDateTime(detailCache[item.order_id].payment_time!) : '-' }}</div>
                        </div>
                      </template>

                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">VA / Kode Bayar</div>
                        <div class="font-weight-medium">
                          {{ detailCache[item.order_id].va_number || detailCache[item.order_id].payment_code || '-' }}
                        </div>
                      </div>

                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">Biller Code</div>
                        <div class="font-weight-medium">{{ detailCache[item.order_id].biller_code || '-' }}</div>
                      </div>

                      <div class="detail-item">
                        <div class="text-caption text-medium-emphasis">QR Code URL</div>
                        <div class="font-weight-medium">
                          <a
                            v-if="detailCache[item.order_id].qr_code_url"
                            :href="detailCache[item.order_id].qr_code_url!"
                            target="_blank"
                            rel="noopener"
                          >
                            Buka
                          </a>
                          <span v-else>-</span>
                        </div>
                      </div>
                    </div>

                    <div v-if="detailCache[item.order_id]?.midtrans_notification_payload" class="mt-4">
                      <div class="text-caption text-medium-emphasis mb-2">Midtrans Notification Payload</div>
                      <div class="payload-grid">
                        <template v-for="(v, k) in (asRecord(detailCache[item.order_id].midtrans_notification_payload) || {})" :key="String(k)">
                          <div class="payload-key">{{ String(k) }}</div>
                          <div class="payload-value">
                            <span v-if="typeof v === 'string' && (String(k).includes('time') || String(k).includes('expiry'))">
                              {{ formatMaybeDateTime(v) }}
                            </span>
                            <span v-else-if="typeof v === 'object'">
                              {{ JSON.stringify(v) }}
                            </span>
                            <span v-else>
                              {{ String(v) }}
                            </span>
                          </div>
                        </template>
                      </div>
                    </div>

                    <div v-if="detailCache[item.order_id]?.events && detailCache[item.order_id]!.events!.length" class="mt-4">
                      <div class="text-caption text-medium-emphasis mb-2">Histori Transaksi (APP / MIDTRANS)</div>
                      <div class="payload-grid">
                        <template v-for="ev in detailCache[item.order_id]!.events!" :key="ev.id">
                          <div class="payload-key">
                            {{ ev.created_at ? formatDateTime(ev.created_at) : '-' }}
                          </div>
                          <div class="payload-value">
                            <span class="font-weight-medium">{{ ev.source }}</span>
                            • <span class="mono">{{ ev.event_type }}</span>
                            <span v-if="ev.status"> • {{ ev.status }}</span>
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>

          <template #loading>
            <div class="loading-overlay">
              <VProgressCircular indeterminate size="48" color="primary" />
              <p class="mt-4 text-primary">
                Memuat data...
              </p>
            </div>
          </template>

          <template #no-data>
            <div class="py-8 text-center no-data">
              <VIcon size="64" color="grey-lighten-1" icon="tabler-database-off" />
              <p class="text-grey mt-4">
                Tidak ada data transaksi yang ditemukan
              </p>
              <VBtn color="primary" variant="tonal" class="mt-4" @click="refresh">
                <VIcon start icon="tabler-refresh" />
                Muat Ulang
              </VBtn>
            </div>
          </template>
        </VDataTableServer>

        <TablePagination
          v-if="totalTransactions > 0"
          :page="options.page"
          :items-per-page="options.itemsPerPage"
          :total-items="totalTransactions"
          @update:page="val => (options.page = val)"
        />
      </div>
    </VCard>


    <VDialog v-if="isHydrated" v-model="isUserFilterDialogOpen" max-width="600px" scrollable>
      <VCard class="user-dialog">
        <VCardTitle class="pa-4 bg-primary">
          <div class="dialog-titlebar">
            <div class="dialog-titlebar__title">
              <span class="text-white font-weight-medium">Pilih Pengguna</span>
            </div>
            <div class="dialog-titlebar__actions">
              <VBtn icon variant="text" @click="isUserFilterDialogOpen = false">
                <VIcon color="white" icon="tabler-x" size="24" />
              </VBtn>
            </div>
          </div>
        </VCardTitle>
        <VDivider />
        <VCardText class="pa-4">
          <VTextField
            v-model="userSearch"
            label="Cari pengguna..."
            prepend-inner-icon="tabler-search"
            variant="outlined"
            autofocus
            clearable
            class="mb-4 user-search"
          />

          <div class="mt-2 user-list-container">
            <VList lines="two">
              <template v-if="filteredUserList.length > 0">
                <VListItem
                  v-for="user in filteredUserList"
                  :key="user.id"
                  class="cursor-pointer user-item"
                  :class="{ 'bg-light-primary': tempSelectedUser?.id === user.id }"
                  @click="selectUser(user)"
                >
                  <template #prepend>
                    <VAvatar color="primary" size="40">
                      <span class="text-white">{{ getUserInitials(user.full_name) }}</span>
                    </VAvatar>
                  </template>
                  <VListItemTitle class="font-weight-medium">
                    {{ user.full_name }}
                  </VListItemTitle>
                  <VListItemSubtitle class="text-medium-emphasis">
                    {{ formatPhoneNumberForDisplay(user.phone_number) }}
                  </VListItemSubtitle>
                </VListItem>
              </template>
              <VListItem v-else class="text-center py-8 no-users">
                <VIcon size="48" color="grey" icon="tabler-user-off" />
                <VListItemTitle class="text-grey mt-4">
                  Pengguna tidak ditemukan
                </VListItemTitle>
              </VListItem>
            </VList>
          </div>
        </VCardText>
        <VDivider />
        <VCardActions class="pa-4">
          <VBtn variant="tonal" @click="isUserFilterDialogOpen = false">
            Batal
          </VBtn>
          <VBtn color="primary" :disabled="tempSelectedUser === null" @click="confirmUserSelection">
            Pilih
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.transaction-manager {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.v-card {
  border-radius: 12px;
  overflow: hidden;
}
.date-field :deep(.v-field) {
  cursor: pointer;
}
.date-field.active-field {
  font-weight: 500;
  color: rgba(var(--v-theme-primary));
}
.filter-btn, .action-btn {
  font-weight: 500;
  letter-spacing: 0.25px;
  border-radius: 8px;
}
.active-filter-chip {
  font-weight: 500;
  border-radius: 16px;
}
.data-table :deep(th) {
  font-weight: 600 !important;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 13px;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.data-table :deep(td) {
  vertical-align: middle;
}
.user-name, .amount-value {
  font-weight: 500;
}
.date-time {
  color: rgba(var(--v-theme-on-surface), 0.7);
  min-height: 50px;
}
.loading-overlay, .no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}
.user-dialog .v-card-title {
  font-size: 18px;
}
.user-list-container {
  max-height: 400px;
  overflow-y: auto;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.user-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.05);
}

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
.search-container {
  flex: 1;
  max-width: 400px;
}
.search-field {
  width: 100%;
}

.status-chip {
  font-weight: 600;
  letter-spacing: 0.15px;
}

.detail-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  align-items: flex-start;
}

.detail-item {
  flex: 1 1 220px;
  min-width: 180px;
}

.payload-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 8px 16px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 12px;
}

.payload-key {
  font-size: 12px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.7);
  word-break: break-word;
}

.payload-value {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.9);
  word-break: break-word;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

/* Perbaikan utama untuk alignment kalender */
:deep(.v-date-picker-month) {
  padding: 0 !important;
  width: 100% !important;
}

:deep(.v-date-picker-month__weeks) {
  display: grid !important;
  grid-template-columns: repeat(7, 1fr) !important;
  justify-items: center !important;
  width: 100% !important;
  column-gap: 0 !important;
}

:deep(.v-date-picker-month__weekday) {
  padding: 0 !important;
  margin: 0 !important;
  width: 100% !important;
  text-align: center !important;
  font-size: 0.875rem !important;
  height: 40px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

:deep(.v-date-picker-month__days) {
  display: grid !important;
  grid-template-columns: repeat(7, 1fr) !important;
  justify-items: center !important;
  width: 100% !important;
  column-gap: 0 !important;
}

:deep(.v-date-picker-month__day) {
  margin: 0 !important;
  padding: 0 !important;
  width: 100% !important;
  height: 40px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

:deep(.v-date-picker-month__day-btn) {
  width: 36px !important;
  height: 36px !important;
  margin: 0 !important;
}

:deep(.v-date-picker-month__day--adjacent) {
  opacity: 0.5 !important;
}

/* Perbaikan tambahan untuk layout responsif */
.v-menu :deep(.v-overlay__content) {
  width: 320px !important;
  min-width: 320px !important;
  max-width: 320px !important;
}

:deep(.v-date-picker-controls) {
  padding: 4px 8px !important;
}

:deep(.v-date-picker-header) {
  padding: 10px 20px !important;
}
</style>
