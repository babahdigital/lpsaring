<script setup lang="ts">
import type { AsyncData } from '#app'
import { useNuxtApp, useRuntimeConfig } from '#app'
import { computed, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useApiFetch } from '~/composables/useApiFetch'
import type { QuotaHistoryFilters, QuotaHistoryItem, QuotaHistoryResponse, QuotaHistorySummary, UserQuotaResponse } from '~/types/user'
import { useDebtSettlementPayment } from '~/composables/useDebtSettlementPayment'
import { useSnackbar } from '@/composables/useSnackbar'
import { useSettingsStore } from '~/store/settings'
import { formatCurrencyIdr, formatDateMediumId, formatDateTimeShortNumericId, formatNumberId } from '~/utils/formatters'

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
const settingsStore = useSettingsStore()

function toast(type: 'success' | 'error' | 'info' | 'warning', text: string, title?: string) {
  addSnackbar({
    type,
    title: title ?? (type === 'success' ? 'Berhasil' : type === 'error' ? 'Gagal' : type === 'warning' ? 'Peringatan' : 'Info'),
    text,
  })
}

const downloadingInvoice = ref<string | null>(null)

const { paying: debtPaying, pay: payDebt } = useDebtSettlementPayment()

type PaymentMethod = 'qris' | 'gopay' | 'shopeepay' | 'va'
type VaBank = 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb'

function parseCsvList(value: string | null | undefined): string[] {
  const raw = (value ?? '').toString().trim()
  if (raw === '')
    return []
  return Array.from(new Set(raw.split(',').map(p => p.trim().toLowerCase()).filter(Boolean)))
}

const providerMode = computed<'snap' | 'core_api'>(() => {
  const raw = (settingsStore.getSetting('PAYMENT_PROVIDER_MODE', 'snap') ?? 'snap').toString().trim().toLowerCase()
  return raw === 'core_api' ? 'core_api' : 'snap'
})

const coreApiEnabledMethods = computed<PaymentMethod[]>(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_PAYMENT_METHODS', 'qris,gopay,va'))
  const allowed: PaymentMethod[] = ['qris', 'gopay', 'shopeepay', 'va']
  const enabled = allowed.filter(m => parsed.includes(m))
  return enabled.length > 0 ? enabled : ['qris', 'gopay', 'va']
})

const coreApiEnabledVaBanks = computed<VaBank[]>(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_VA_BANKS', 'bca,bni,bri,mandiri,permata,cimb'))
  const allowed: VaBank[] = ['bca', 'bni', 'bri', 'mandiri', 'permata', 'cimb']
  const enabled = allowed.filter(b => parsed.includes(b))
  return enabled.length > 0 ? enabled : ['bni', 'bca', 'mandiri', 'bri', 'permata', 'cimb']
})

const showDebtPaymentDialog = ref(false)
const selectedDebtMethod = ref<PaymentMethod>('qris')
const selectedDebtVaBank = ref<VaBank>('bni')
const pendingManualDebtId = ref<string | null>(null)

const allDebtPaymentMethodItems = [
  {
    value: 'qris' as const,
    title: 'QRIS',
    subtitle: 'Scan QR dari aplikasi pembayaran',
    icon: 'tabler-qrcode',
  },
  {
    value: 'gopay' as const,
    title: 'GoPay',
    subtitle: 'Buka GoPay / scan QR jika tersedia',
    icon: 'tabler-wallet',
  },
  {
    value: 'shopeepay' as const,
    title: 'ShopeePay',
    subtitle: 'Buka ShopeePay / scan QR jika tersedia',
    icon: 'tabler-wallet',
  },
  {
    value: 'va' as const,
    title: 'Transfer Virtual Account',
    subtitle: 'Pilih bank, lalu transfer via VA',
    icon: 'tabler-building-bank',
  },
] as const

const availableDebtPaymentMethodItems = computed(() => {
  const enabled = new Set(coreApiEnabledMethods.value)
  return allDebtPaymentMethodItems.filter(i => enabled.has(i.value))
})

const vaBankItems = [
  { title: 'BCA', value: 'bca' },
  { title: 'BNI', value: 'bni' },
  { title: 'BRI', value: 'bri' },
  { title: 'Mandiri', value: 'mandiri' },
  { title: 'Permata', value: 'permata' },
  { title: 'CIMB Niaga', value: 'cimb' },
] as const

const availableDebtVaBankItems = computed(() => {
  const enabled = new Set(coreApiEnabledVaBanks.value)
  return vaBankItems.filter(i => enabled.has(i.value))
})

watch(availableDebtPaymentMethodItems, (items) => {
  const first = items[0]?.value
  if (!first)
    return
  if (!items.some(i => i.value === selectedDebtMethod.value))
    selectedDebtMethod.value = first
}, { immediate: true })

watch([selectedDebtMethod, availableDebtVaBankItems], () => {
  if (selectedDebtMethod.value !== 'va')
    return
  const items = availableDebtVaBankItems.value
  const first = items[0]?.value
  if (!first)
    return
  if (!items.some(i => i.value === selectedDebtVaBank.value))
    selectedDebtVaBank.value = first
}, { immediate: true })

function openDebtPaymentDialog() {
  pendingManualDebtId.value = null
  const methods = coreApiEnabledMethods.value
  selectedDebtMethod.value = methods.includes(selectedDebtMethod.value) ? selectedDebtMethod.value : (methods[0] ?? 'qris')
  const banks = coreApiEnabledVaBanks.value
  selectedDebtVaBank.value = banks.includes(selectedDebtVaBank.value)
    ? selectedDebtVaBank.value
    : (banks.includes('bni') ? 'bni' : (banks[0] ?? 'bni'))
  showDebtPaymentDialog.value = true
}

function openDebtPaymentDialogForManualItem(debtId: string) {
  if (typeof debtId !== 'string' || debtId.trim() === '')
    return
  pendingManualDebtId.value = debtId
  const methods = coreApiEnabledMethods.value
  selectedDebtMethod.value = methods.includes(selectedDebtMethod.value) ? selectedDebtMethod.value : (methods[0] ?? 'qris')
  const banks = coreApiEnabledVaBanks.value
  selectedDebtVaBank.value = banks.includes(selectedDebtVaBank.value)
    ? selectedDebtVaBank.value
    : (banks.includes('bni') ? 'bni' : (banks[0] ?? 'bni'))
  showDebtPaymentDialog.value = true
}

function closeDebtPaymentDialog() {
  showDebtPaymentDialog.value = false
  pendingManualDebtId.value = null
}

function handleDebtPayClick() {
  if (providerMode.value === 'core_api') {
    openDebtPaymentDialog()
    return
  }
  void payDebt()
}

function confirmDebtPayment() {
  const method = selectedDebtMethod.value
  const body = {
    payment_method: method,
    va_bank: method === 'va' ? selectedDebtVaBank.value : undefined,
  }
  const manualDebtId = pendingManualDebtId.value
  closeDebtPaymentDialog()

  if (typeof manualDebtId === 'string' && manualDebtId.trim() !== '') {
    void payDebt({ manualDebtId, ...body } as any)
    return
  }

  void payDebt(body as any)
}

function payManualDebtItem(debtId: string) {
  if (typeof debtId !== 'string' || debtId.trim() === '')
    return
  if (providerMode.value === 'core_api') {
    openDebtPaymentDialogForManualItem(debtId)
    return
  }
  void payDebt(debtId)
}

const selectedManualDebtItem = computed(() => {
  const id = pendingManualDebtId.value
  if (id == null)
    return null
  return quotaDebtItems.value.find(it => it.id === id) ?? null
})

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
const debtEstimateHelperText = 'Nilai referensi otomatis memakai paket aktif termurah; item manual mengikuti nominal yang tercatat.'

const showDebtCard = computed(() => {
  return debtTotalMb.value > 0 || debtManualMb.value > 0 || quotaDebtItems.value.length > 0
})

const unpaidDebtCount = computed(() => quotaDebtItems.value.filter(d => !d.is_paid).length)

function isUnlimitedDebtItem(note: string | null | undefined, amountMb: number | null | undefined): boolean {
  const normalizedNote = String(note ?? '').toLowerCase()
  return normalizedNote.startsWith('paket:') && normalizedNote.includes('unlimited') && Number(amountMb ?? 0) <= 1
}

const debtCardValueText = computed(() => {
  if (quotaDebtItems.value.some(item => isUnlimitedDebtItem(item.note, item.amount_mb)))
    return 'Unlimited'
  if (debtEstimatedRp.value > 0)
    return formatCurrency(debtEstimatedRp.value)
  if (debtManualMb.value > 0)
    return formatQuota(debtManualMb.value)
  return formatQuota(debtTotalMb.value)
})

const debtCardHelperText = computed(() => {
  if (quotaData.value?.is_unlimited_user === true && quotaDebtItems.value.length > 0)
    return 'Akses Anda saat ini unlimited, tetapi catatan tunggakan manual tetap tercatat dan bisa ditinjau di bawah.'
  return debtEstimateHelperText
})

function formatDebtItemQuota(amountMb: number | null | undefined, note: string | null | undefined): string {
  if (isUnlimitedDebtItem(note, amountMb))
    return 'Unlimited'
  return formatQuota(amountMb)
}

function formatQuota(mbValue: number | null | undefined): string {
  const mb = Number(mbValue ?? 0)
  if (!Number.isFinite(mb) || mb <= 0)
    return '0 MB'
  if (mb < 1)
    return `${formatNumberId(Math.round(mb * 1024), 0, 0)} KB`
  if (mb >= 1024)
    return `${formatNumberId(Math.round((mb / 1024) * 100) / 100, 2, 0)} GB`
  return `${formatNumberId(Math.round(mb), 0, 0)} MB`
}

// --- Data Tunggakan Manual (Per Tanggal) ---
interface QuotaDebtItem {
  id: string
  debt_date: string | null
  due_date: string | null
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

type HistoryRangePreset = 'today' | '3d' | '7d' | '30d' | 'custom'
type FixedHistoryRangePreset = Exclude<HistoryRangePreset, 'custom'>

interface HistoryPresetOption {
  value: HistoryRangePreset
  label: string
  icon: string
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
    const formatted = formatDateMediumId(dateStr, 7)
    if (formatted === '-')
      return '-'
    return formatted
  }
  catch {
    return '-'
  }
}

/** Format due_date (YYYY-MM-DD) sebagai "18 Apr 2026, 23:59" (akhir hari WITA) */
function formatDueDate(dateStr: string | null | undefined): string {
  if (!dateStr)
    return ''
  try {
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

function isDueDateOverdue(dateStr: string | null | undefined): boolean {
  if (!dateStr)
    return false
  try {
    return new Date(`${dateStr}T23:59:00+08:00`) < new Date()
  }
  catch {
    return false
  }
}

/** Fallback: jika due_date null, hitung hari terakhir bulan dari debt_date */
function getEffectiveDueDate(debtDate: string | null | undefined, dueDate: string | null | undefined): string | null {
  if (dueDate)
    return dueDate
  if (!debtDate)
    return null
  const d = new Date(`${debtDate}T00:00:00`)
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0)
  return lastDay.toISOString().slice(0, 10)
}

const DEFAULT_QUOTA_HISTORY_ITEMS_PER_PAGE = 25
const MAX_QUOTA_HISTORY_FILTER_DAYS = 90
const DEFAULT_QUOTA_HISTORY_RANGE_PRESET: FixedHistoryRangePreset = '30d'
const quotaHistoryPresetOptions: HistoryPresetOption[] = [
  { value: 'today', label: 'Hari Ini', icon: 'tabler-calendar' },
  { value: '3d', label: '3 Hari', icon: 'tabler-calendar' },
  { value: '7d', label: '1 Minggu', icon: 'tabler-calendar' },
  { value: '30d', label: '1 Bulan', icon: 'tabler-calendar' },
  { value: 'custom', label: 'Kustom', icon: 'tabler-filter' },
]

const quotaHistoryItems = ref<QuotaHistoryItem[]>([])
const quotaHistorySummary = ref<QuotaHistorySummary | null>(null)
const quotaHistoryFilters = ref<QuotaHistoryFilters | null>(null)
const quotaHistoryPending = ref(false)
const quotaHistoryError = ref<string | null>(null)
const quotaHistoryTotalItems = ref(0)
const quotaHistoryRangePreset = ref<HistoryRangePreset>(DEFAULT_QUOTA_HISTORY_RANGE_PRESET)
const quotaHistorySearchQuery = ref('')
const quotaHistoryDraftSearchQuery = ref('')
const quotaHistoryStartDate = ref<Date | null>(null)
const quotaHistoryEndDate = ref<Date | null>(null)
const quotaHistoryStartDateMenuOpen = ref(false)
const quotaHistoryEndDateMenuOpen = ref(false)
const quotaHistoryActiveFilterLabel = computed(() => quotaHistoryFilters.value?.label || formatQuotaHistoryDateRangeLabel(quotaHistoryStartDate.value, quotaHistoryEndDate.value))
const quotaHistoryActiveSearchText = computed(() => {
  const serverSearch = String(quotaHistoryFilters.value?.search ?? '').trim()
  return serverSearch !== '' ? serverSearch : quotaHistorySearchQuery.value
})
const quotaHistoryRetentionDays = computed(() => Number(quotaHistoryFilters.value?.retention_days ?? MAX_QUOTA_HISTORY_FILTER_DAYS))

function toStartOfDay(value: Date): Date {
  const next = new Date(value)
  next.setHours(0, 0, 0, 0)
  return next
}

function cloneDate(value: Date): Date {
  return toStartOfDay(value)
}

function addDays(value: Date, days: number): Date {
  const next = cloneDate(value)
  next.setDate(next.getDate() + days)
  return next
}

function toYmd(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseYmd(value?: string | null): Date | null {
  const text = String(value ?? '').trim()
  if (text === '')
    return null

  const normalized = text.includes('T') ? text.split('T', 1)[0] : text
  const parts = normalized.split('-').map(Number)
  if (parts.length !== 3 || parts.some(part => Number.isNaN(part)))
    return null

  return new Date(parts[0], parts[1] - 1, parts[2])
}

function normalizePickerDate(value: unknown): Date | null {
  if (value instanceof Date)
    return cloneDate(value)
  if (typeof value === 'string' && value.trim() !== '')
    return parseYmd(value)

  return null
}

function formatQuotaHistoryDate(value: Date | null): string {
  return value !== null
    ? value.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' })
    : ''
}

function formatQuotaHistoryDateRangeLabel(start: Date | null, end: Date | null): string {
  const effectiveStart = start ?? end
  const effectiveEnd = end ?? start
  if (effectiveStart === null || effectiveEnd === null)
    return '30 hari terakhir'

  const today = toStartOfDay(new Date())
  const rangeDays = Math.floor((effectiveEnd.getTime() - effectiveStart.getTime()) / 86_400_000) + 1

  if (effectiveStart.getTime() === today.getTime() && effectiveEnd.getTime() === today.getTime())
    return 'Hari ini'
  if (effectiveEnd.getTime() === today.getTime() && rangeDays === 3)
    return '3 hari terakhir'
  if (effectiveEnd.getTime() === today.getTime() && rangeDays === 7)
    return '7 hari terakhir'
  if (effectiveEnd.getTime() === today.getTime() && rangeDays === 30)
    return '30 hari terakhir'
  if (effectiveStart.getTime() === effectiveEnd.getTime())
    return formatQuotaHistoryDate(effectiveStart)

  return `${formatQuotaHistoryDate(effectiveStart)} - ${formatQuotaHistoryDate(effectiveEnd)}`
}

function inferQuotaHistoryPresetFromDates(start: Date | null, end: Date | null): HistoryRangePreset {
  const effectiveStart = start ?? end
  const effectiveEnd = end ?? start
  if (effectiveStart === null || effectiveEnd === null)
    return DEFAULT_QUOTA_HISTORY_RANGE_PRESET

  const today = toStartOfDay(new Date())
  const rangeDays = Math.floor((effectiveEnd.getTime() - effectiveStart.getTime()) / 86_400_000) + 1
  if (effectiveEnd.getTime() !== today.getTime())
    return 'custom'
  if (rangeDays === 1 && effectiveStart.getTime() === today.getTime())
    return 'today'
  if (rangeDays === 3)
    return '3d'
  if (rangeDays === 7)
    return '7d'
  if (rangeDays === 30)
    return '30d'

  return 'custom'
}

function createQuotaHistoryPresetRange(preset: FixedHistoryRangePreset): { start: Date, end: Date } {
  const today = toStartOfDay(new Date())

  switch (preset) {
    case 'today':
      return { start: today, end: today }
    case '3d':
      return { start: addDays(today, -2), end: today }
    case '7d':
      return { start: addDays(today, -6), end: today }
    case '30d':
    default:
      return { start: addDays(today, -29), end: today }
  }
}

function setQuotaHistoryPresetRange(preset: FixedHistoryRangePreset) {
  const range = createQuotaHistoryPresetRange(preset)
  quotaHistoryStartDate.value = range.start
  quotaHistoryEndDate.value = range.end
  quotaHistoryRangePreset.value = preset
}

function syncQuotaHistoryFiltersFromResponse(nextFilters?: QuotaHistoryFilters | null) {
  quotaHistoryFilters.value = nextFilters ?? null
  if (!nextFilters)
    return

  const nextStart = parseYmd(nextFilters.start_date)
  const nextEnd = parseYmd(nextFilters.end_date)
  if (nextStart !== null)
    quotaHistoryStartDate.value = nextStart
  if (nextEnd !== null)
    quotaHistoryEndDate.value = nextEnd

  quotaHistorySearchQuery.value = String(nextFilters.search ?? '').trim()
  quotaHistoryDraftSearchQuery.value = quotaHistorySearchQuery.value
  quotaHistoryRangePreset.value = inferQuotaHistoryPresetFromDates(quotaHistoryStartDate.value, quotaHistoryEndDate.value)
}

function buildQuotaHistoryParams(): Record<string, string | number | undefined> {
  return {
    page: 1,
    itemsPerPage: DEFAULT_QUOTA_HISTORY_ITEMS_PER_PAGE,
    startDate: quotaHistoryStartDate.value ? toYmd(quotaHistoryStartDate.value) : undefined,
    endDate: quotaHistoryEndDate.value ? toYmd(quotaHistoryEndDate.value) : undefined,
    search: quotaHistorySearchQuery.value || undefined,
  }
}

function buildQuotaHistoryPdfQueryString(): string {
  const query = new URLSearchParams({ format: 'pdf' })

  for (const [key, value] of Object.entries(buildQuotaHistoryParams())) {
    if (value !== undefined && value !== '')
      query.set(key, String(value))
  }

  return query.toString()
}

function normalizeQuotaHistorySelectedRange(): boolean {
  let normalizedStart = quotaHistoryStartDate.value ? cloneDate(quotaHistoryStartDate.value) : null
  let normalizedEnd = quotaHistoryEndDate.value ? cloneDate(quotaHistoryEndDate.value) : null

  if (normalizedStart === null && normalizedEnd === null) {
    setQuotaHistoryPresetRange(DEFAULT_QUOTA_HISTORY_RANGE_PRESET)
    normalizedStart = quotaHistoryStartDate.value ? cloneDate(quotaHistoryStartDate.value) : null
    normalizedEnd = quotaHistoryEndDate.value ? cloneDate(quotaHistoryEndDate.value) : null
  }

  if (normalizedStart === null && normalizedEnd !== null)
    normalizedStart = cloneDate(normalizedEnd)
  if (normalizedEnd === null && normalizedStart !== null)
    normalizedEnd = cloneDate(normalizedStart)

  if (normalizedStart === null || normalizedEnd === null)
    return false

  if (normalizedStart.getTime() > normalizedEnd.getTime()) {
    toast('warning', 'Tanggal akhir tidak boleh sebelum tanggal mulai.', 'Filter Tanggal')
    return false
  }

  const totalDays = Math.floor((normalizedEnd.getTime() - normalizedStart.getTime()) / 86_400_000) + 1
  if (totalDays > MAX_QUOTA_HISTORY_FILTER_DAYS) {
    toast('warning', `Rentang maksimal ${MAX_QUOTA_HISTORY_FILTER_DAYS} hari.`, 'Filter Tanggal')
    return false
  }

  quotaHistoryStartDate.value = normalizedStart
  quotaHistoryEndDate.value = normalizedEnd
  return true
}

async function fetchQuotaHistory() {
  if (!normalizeQuotaHistorySelectedRange())
    return

  quotaHistoryPending.value = true
  quotaHistoryError.value = null

  try {
    const resp = await $api<QuotaHistoryResponse>('/users/me/quota-history', {
      method: 'GET',
      params: buildQuotaHistoryParams(),
    })

    quotaHistoryItems.value = Array.isArray(resp.items) ? resp.items : []
    quotaHistorySummary.value = resp.summary ?? null
    quotaHistoryTotalItems.value = Number(resp.totalItems ?? quotaHistoryItems.value.length)
    syncQuotaHistoryFiltersFromResponse(resp.filters ?? null)
  }
  catch (error: any) {
    quotaHistoryItems.value = []
    quotaHistorySummary.value = null
    quotaHistoryTotalItems.value = 0
    quotaHistoryError.value = error?.data?.message ?? error?.message ?? 'Gagal memuat riwayat mutasi kuota.'
  }
  finally {
    quotaHistoryPending.value = false
  }
}

async function applyQuotaHistoryFilters() {
  if (quotaHistoryPending.value)
    return

  if (!normalizeQuotaHistorySelectedRange())
    return

  quotaHistorySearchQuery.value = quotaHistoryDraftSearchQuery.value.trim()
  await fetchQuotaHistory()
}

async function resetQuotaHistoryFilters(shouldFetch = true) {
  quotaHistoryFilters.value = null
  quotaHistorySearchQuery.value = ''
  quotaHistoryDraftSearchQuery.value = ''
  quotaHistoryError.value = null
  quotaHistoryTotalItems.value = 0
  setQuotaHistoryPresetRange(DEFAULT_QUOTA_HISTORY_RANGE_PRESET)

  if (shouldFetch)
    await fetchQuotaHistory()
}

async function applyQuotaHistoryPreset(preset: FixedHistoryRangePreset) {
  if (quotaHistoryPending.value)
    return

  setQuotaHistoryPresetRange(preset)
  quotaHistorySearchQuery.value = quotaHistoryDraftSearchQuery.value.trim()
  await fetchQuotaHistory()
}

function enableQuotaHistoryCustomRange() {
  quotaHistoryRangePreset.value = 'custom'
  if (quotaHistoryStartDate.value === null && quotaHistoryEndDate.value === null)
    setQuotaHistoryPresetRange(DEFAULT_QUOTA_HISTORY_RANGE_PRESET)
}

function handleQuotaHistoryStartDatePicked(value: unknown) {
  quotaHistoryStartDate.value = normalizePickerDate(value)
  quotaHistoryRangePreset.value = 'custom'
  if (quotaHistoryStartDate.value && quotaHistoryEndDate.value && quotaHistoryStartDate.value.getTime() > quotaHistoryEndDate.value.getTime())
    quotaHistoryEndDate.value = cloneDate(quotaHistoryStartDate.value)
  quotaHistoryStartDateMenuOpen.value = false
}

function handleQuotaHistoryEndDatePicked(value: unknown) {
  quotaHistoryEndDate.value = normalizePickerDate(value)
  quotaHistoryRangePreset.value = 'custom'
  if (quotaHistoryStartDate.value && quotaHistoryEndDate.value && quotaHistoryEndDate.value.getTime() < quotaHistoryStartDate.value.getTime())
    quotaHistoryStartDate.value = cloneDate(quotaHistoryEndDate.value)
  quotaHistoryEndDateMenuOpen.value = false
}

async function clearQuotaHistoryStartDate() {
  quotaHistoryStartDate.value = null
  quotaHistoryRangePreset.value = 'custom'
  if (quotaHistorySearchQuery.value === '' && quotaHistoryEndDate.value === null)
    await resetQuotaHistoryFilters()
}

async function clearQuotaHistoryEndDate() {
  quotaHistoryEndDate.value = null
  quotaHistoryRangePreset.value = 'custom'
  if (quotaHistorySearchQuery.value === '' && quotaHistoryStartDate.value === null)
    await resetQuotaHistoryFilters()
}

async function clearQuotaHistorySearch() {
  quotaHistoryDraftSearchQuery.value = ''
  if (quotaHistorySearchQuery.value !== '') {
    quotaHistorySearchQuery.value = ''
    await fetchQuotaHistory()
  }
}

function getHistoryCategoryColor(category: string | null | undefined): string {
  switch (category) {
    case 'usage':
      return 'info'
    case 'sync':
      return 'secondary'
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

function getHistoryCategoryLabel(category: string | null | undefined): string {
  switch (category) {
    case 'usage':
      return 'Pemakaian'
    case 'sync':
      return 'Sinkronisasi'
    case 'purchase':
      return 'Pembelian'
    case 'debt':
      return 'Tunggakan'
    case 'policy':
      return 'Kebijakan'
    case 'adjustment':
      return 'Koreksi'
    default:
      return 'Sistem'
  }
}

function openQuotaHistoryPdf() {
  window.open(`/api/users/me/quota-history/export?${buildQuotaHistoryPdfQueryString()}`, '_blank', 'noopener')
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
    const formatted = formatDateTimeShortNumericId(dateTimeString, 7)
    return formatted === '-'
      ? 'Tanggal Invalid'
      : formatted
  }
  catch {
    return 'Error Format'
  }
}

function formatCurrency(value: number | null | undefined): string {
  const numValue = Number(value ?? 0)
  return Number.isNaN(numValue)
    ? 'Jumlah Invalid'
    : formatCurrencyIdr(numValue)
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
  void resetQuotaHistoryFilters()
})
useHead({ title: 'Riwayat Transaksi & Kuota' })
</script>

<template>
  <VContainer fluid>
    <VRow>
      <VCol cols="12">
        <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-4">
          <h1 class="text-h5 mb-0">
            Riwayat Transaksi & Kuota
          </h1>

          <VBtn
            v-if="showDebtCard"
            size="small"
            color="warning"
            variant="flat"
            prepend-icon="tabler-credit-card"
            :loading="debtPaying"
            :disabled="debtPaying"
            @click="handleDebtPayClick()"
          >
            Lunasi Semua
          </VBtn>
        </div>

        <VCard v-if="showDebtCard" variant="tonal" class="mb-4">
          <VCardText class="py-4">
            <div class="d-flex align-center justify-space-between flex-wrap gap-2">
              <div class="d-flex align-center gap-2">
                <div>
                  <div class="text-subtitle-1 font-weight-medium">
                    Tunggakan Kuota
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    Nilai referensi
                  </div>
                </div>
                <VChip
                  v-if="unpaidDebtCount > 0"
                  size="small"
                  color="warning"
                  variant="flat"
                  label
                >
                  {{ unpaidDebtCount }} belum lunas
                </VChip>
              </div>

              <div class="text-body-1 font-weight-medium">
                {{ debtCardValueText }}
              </div>
            </div>

            <div class="text-caption text-medium-emphasis mt-2">
              {{ debtCardHelperText }}
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
                    <col style="width: 130px;">
                    <col style="width: 155px;">
                    <col style="width: 110px;">
                    <col style="width: 110px;">
                    <col style="width: 110px;">
                  </colgroup>
                  <thead>
                    <tr>
                      <th class="text-no-wrap">Dicatat Pada</th>
                      <th class="text-no-wrap">Jatuh Tempo</th>
                      <th class="text-end text-no-wrap">Kuota</th>
                      <th class="text-no-wrap">Status</th>
                      <th class="text-end text-no-wrap">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="it in quotaDebtItems" :key="it.id">
                      <td class="text-no-wrap text-caption text-medium-emphasis">
                        {{ formatDebtDate(it.created_at) }}
                      </td>
                      <td class="text-no-wrap">
                        <span v-if="getEffectiveDueDate(it.debt_date, it.due_date)">
                          <VChip
                            size="x-small"
                            :color="it.is_paid ? 'default' : (isDueDateOverdue(getEffectiveDueDate(it.debt_date, it.due_date)) ? 'error' : 'warning')"
                            variant="tonal"
                            label
                          >
                            {{ formatDueDate(getEffectiveDueDate(it.debt_date, it.due_date)) }}
                          </VChip>
                        </span>
                        <span v-else class="text-disabled text-caption">Belum ditetapkan</span>
                      </td>
                      <td class="text-end text-no-wrap font-weight-medium">
                        {{ formatDebtItemQuota(it.amount_mb, it.note) }}
                      </td>
                      <td class="text-no-wrap">
                        <VChip :color="it.is_paid ? 'success' : 'warning'" size="x-small" label>
                          {{ it.is_paid ? 'LUNAS' : 'BELUM LUNAS' }}
                        </VChip>
                      </td>
                      <td class="text-end text-no-wrap">
                        <VBtn
                          v-if="!it.is_paid"
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
                      <td colspan="5" class="text-center text-medium-emphasis py-3">
                        Tidak ada hutang manual yang belum lunas.
                      </td>
                    </tr>
                  </tbody>
                </VTable>
              </div>
            </div>
          </VCardText>
        </VCard>

        <VCard class="mb-4">
          <VCardTitle class="d-flex align-center justify-space-between flex-wrap gap-2 py-3 px-4 bg-grey-lighten-4 border-b">
            <div class="d-flex align-center ga-2">
              <VIcon icon="tabler-history-toggle" color="primary" />
              <div>
                <div class="text-subtitle-1 font-weight-medium">
                  Riwayat Mutasi Kuota
                </div>
                <div class="text-caption text-medium-emphasis">
                  25 event terbaru dari pembelian, pemakaian, tunggakan, dan kebijakan sistem.
                </div>
              </div>
            </div>

            <VBtn
              size="small"
              color="primary"
              variant="tonal"
              prepend-icon="tabler-printer"
              @click="openQuotaHistoryPdf"
            >
              PDF
            </VBtn>
          </VCardTitle>

          <VCardText class="px-4 pt-4">
            <div class="history-summary-chips d-flex flex-wrap gap-2 mb-4">
              <VChip size="small" label color="primary" variant="tonal">
                Event: {{ quotaHistoryItems.length }} / {{ quotaHistoryTotalItems || quotaHistoryItems.length }}
              </VChip>
              <VChip v-if="quotaHistorySummary" size="small" label color="success" variant="tonal">
                Beli bersih: {{ formatQuota(quotaHistorySummary.total_net_purchased_mb) }}
              </VChip>
              <VChip v-if="quotaHistorySummary" size="small" label color="warning" variant="tonal">
                Pakai bersih: {{ formatQuota(quotaHistorySummary.total_net_used_mb) }}
              </VChip>
              <VChip size="small" label color="secondary" variant="tonal">
                Periode: {{ quotaHistoryActiveFilterLabel }}
              </VChip>
              <VChip v-if="quotaHistoryActiveSearchText" size="small" label color="secondary" variant="tonal">
                Cari: {{ quotaHistoryActiveSearchText }}
              </VChip>
              <VChip size="small" label color="default" variant="tonal">
                Retensi: {{ quotaHistoryRetentionDays }} hari
              </VChip>
            </div>

            <VCard variant="outlined" class="history-filter-card mb-4">
              <VCardText class="pa-4">
                <div class="history-filter-card__header">
                  <div>
                    <div class="text-subtitle-2 font-weight-medium">
                      Filter Riwayat
                    </div>
                    <div class="text-caption text-medium-emphasis mt-1">
                      Pilih periode harian, 3 hari, mingguan, atau bulanan. Data tersimpan maksimal {{ quotaHistoryRetentionDays }} hari.
                    </div>
                  </div>
                  <VBtn size="small" variant="text" color="secondary" prepend-icon="tabler-filter-off" @click="resetQuotaHistoryFilters()">
                    Reset
                  </VBtn>
                </div>

                <div class="history-filter-presets mt-4">
                  <VBtn
                    v-for="preset in quotaHistoryPresetOptions"
                    :key="preset.value"
                    size="small"
                    :color="quotaHistoryRangePreset === preset.value ? 'primary' : 'default'"
                    :variant="quotaHistoryRangePreset === preset.value ? 'flat' : 'tonal'"
                    :prepend-icon="preset.icon"
                    @click="preset.value === 'custom' ? enableQuotaHistoryCustomRange() : applyQuotaHistoryPreset(preset.value)"
                  >
                    {{ preset.label }}
                  </VBtn>
                </div>

                <VRow class="mt-1">
                  <VCol cols="12" md="4">
                    <VTextField
                      v-model="quotaHistoryDraftSearchQuery"
                      label="Cari event / aktor / catatan"
                      placeholder="Contoh: pembelian, Abdullah, tunggakan"
                      prepend-inner-icon="tabler-search"
                      clearable
                      hide-details="auto"
                      @keyup.enter="applyQuotaHistoryFilters"
                      @click:clear="clearQuotaHistorySearch"
                    />
                  </VCol>
                  <VCol cols="12" sm="6" md="3">
                    <VTextField
                      id="quota-history-page-start-date"
                      :model-value="formatQuotaHistoryDate(quotaHistoryStartDate)"
                      label="Tanggal Mulai"
                      readonly
                      clearable
                      prepend-inner-icon="tabler-calendar"
                      @click:clear="clearQuotaHistoryStartDate"
                    />
                    <VMenu v-model="quotaHistoryStartDateMenuOpen" activator="#quota-history-page-start-date" :close-on-content-click="false">
                      <VDatePicker v-model="quotaHistoryStartDate" no-title color="primary" :max="new Date()" @update:model-value="handleQuotaHistoryStartDatePicked" />
                    </VMenu>
                  </VCol>
                  <VCol cols="12" sm="6" md="3">
                    <VTextField
                      id="quota-history-page-end-date"
                      :model-value="formatQuotaHistoryDate(quotaHistoryEndDate)"
                      label="Tanggal Akhir"
                      readonly
                      clearable
                      :disabled="!quotaHistoryStartDate"
                      prepend-inner-icon="tabler-calendar"
                      @click:clear="clearQuotaHistoryEndDate"
                    />
                    <VMenu v-model="quotaHistoryEndDateMenuOpen" activator="#quota-history-page-end-date" :close-on-content-click="false">
                      <VDatePicker v-model="quotaHistoryEndDate" no-title color="primary" :min="quotaHistoryStartDate || undefined" :max="new Date()" @update:model-value="handleQuotaHistoryEndDatePicked" />
                    </VMenu>
                  </VCol>
                  <VCol cols="12" md="2" class="d-flex align-end">
                    <VBtn block color="primary" prepend-icon="tabler-filter" :loading="quotaHistoryPending" @click="applyQuotaHistoryFilters">
                      Terapkan
                    </VBtn>
                  </VCol>
                </VRow>

                <div class="history-filter-meta mt-3">
                  <VChip size="small" color="primary" variant="tonal" prepend-icon="tabler-calendar">
                    {{ quotaHistoryActiveFilterLabel }}
                  </VChip>
                  <VChip v-if="quotaHistoryActiveSearchText" size="small" color="secondary" variant="tonal" prepend-icon="tabler-search">
                    Cari: {{ quotaHistoryActiveSearchText }}
                  </VChip>
                  <VChip size="small" color="default" variant="tonal" prepend-icon="tabler-database">
                    Maks {{ quotaHistoryRetentionDays }} hari tersimpan
                  </VChip>
                </div>
              </VCardText>
            </VCard>

            <VAlert v-if="quotaHistoryError" type="error" variant="tonal" density="compact" class="mb-4">
              {{ quotaHistoryError }}
            </VAlert>

            <VAlert
              v-else-if="quotaHistorySummary"
              type="info"
              variant="tonal"
              density="compact"
              icon="tabler-info-circle"
              class="mb-4"
            >
              Filter aktif: <strong>{{ quotaHistoryActiveFilterLabel }}</strong>
              • Rentang event hasil: <strong>{{ quotaHistorySummary.first_event_at_display || '-' }}</strong> sampai <strong>{{ quotaHistorySummary.last_event_at_display || '-' }}</strong>
              • Pemakaian: <strong>{{ quotaHistorySummary.usage_events }}</strong>
              • Pembelian: <strong>{{ quotaHistorySummary.purchase_events }}</strong>
              • Tunggakan: <strong>{{ quotaHistorySummary.debt_events }}</strong>
              • Kebijakan: <strong>{{ quotaHistorySummary.policy_events }}</strong>
            </VAlert>

            <div v-if="quotaHistoryPending" class="d-flex justify-center py-6">
              <VProgressCircular indeterminate color="primary" />
            </div>

            <template v-else>
              <VExpansionPanels v-if="quotaHistoryItems.length > 0" variant="accordion" class="quota-history-panels">
                <VExpansionPanel v-for="item in quotaHistoryItems" :key="item.id">
                  <VExpansionPanelTitle>
                    <div class="d-flex flex-column text-start">
                      <div class="d-flex align-center flex-wrap gap-2">
                        <VChip size="x-small" :color="getHistoryCategoryColor(item.category)" label>
                          {{ getHistoryCategoryLabel(item.category) }}
                        </VChip>
                        <span class="font-weight-medium">{{ item.title }}</span>
                      </div>
                      <div class="text-caption text-medium-emphasis mt-1">
                        {{ item.created_at_display || '-' }}
                      </div>
                    </div>
                  </VExpansionPanelTitle>

                  <VExpansionPanelText>
                    <div class="text-body-2">
                      {{ item.description }}
                    </div>

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
                        Tunggakan {{ item.deltas_display.debt_total }}
                      </VChip>
                      <VChip v-if="item.deltas_display.remaining_after" size="small" color="default" variant="tonal" label>
                        Quota {{ item.deltas_display.remaining_after }}
                      </VChip>
                    </div>

                    <VList v-if="item.highlights?.length" density="compact" class="quota-history-list mt-3">
                      <VListItem v-for="highlight in item.highlights.slice(0, 6)" :key="`${item.id}-${highlight}`" class="px-0">
                        <template #prepend>
                          <VIcon icon="tabler-chevron-right" size="16" />
                        </template>
                        <VListItemTitle class="text-body-2">
                          {{ highlight }}
                        </VListItemTitle>
                      </VListItem>
                    </VList>
                  </VExpansionPanelText>
                </VExpansionPanel>
              </VExpansionPanels>

              <div v-else class="text-center text-medium-emphasis py-6">
                Belum ada riwayat mutasi kuota.
              </div>
            </template>
          </VCardText>
        </VCard>

        <VDialog v-if="isHydrated" v-model="showDebtPaymentDialog" max-width="560px" scrim="grey-darken-3" eager>
          <VCard rounded="lg">
            <VCardTitle class="d-flex align-center py-3 px-4 bg-grey-lighten-4 border-b">
              <VIcon icon="tabler-credit-card" color="primary" start />
              <span class="text-h6 font-weight-medium">Pilih Metode Pembayaran</span>
              <VSpacer />
              <VBtn icon="tabler-x" flat size="small" variant="text" @click="closeDebtPaymentDialog" />
            </VCardTitle>

            <VCardText class="px-4 pt-4">
              <p v-if="selectedManualDebtItem" class="text-caption text-medium-emphasis mb-3">
                Hutang: <span class="font-weight-medium">{{ formatDebtDate(selectedManualDebtItem.debt_date) }}</span>
                <span class="mx-1">•</span>
                <span class="font-weight-medium">{{ formatQuota(selectedManualDebtItem.remaining_mb) }}</span>
              </p>
              <p v-else class="text-caption text-medium-emphasis mb-3">
                Nilai referensi tunggakan: <span class="font-weight-medium">{{ formatCurrency(debtEstimatedRp) }}</span>
              </p>

              <VRadioGroup v-model="selectedDebtMethod" class="mt-1 payment-method-group">
                <VRadio
                  v-for="item in availableDebtPaymentMethodItems"
                  :key="item.value"
                  :value="item.value"
                  class="payment-method-radio"
                >
                  <template #label>
                    <div class="d-flex align-center payment-method-label">
                      <VIcon :icon="item.icon" color="primary" />
                      <div class="payment-method-text">
                        <div class="text-body-1 font-weight-medium">
                          {{ item.title }}
                        </div>
                        <div class="text-caption text-medium-emphasis">
                          {{ item.subtitle }}
                        </div>
                      </div>
                    </div>
                  </template>
                </VRadio>
              </VRadioGroup>

              <VSelect
                v-if="selectedDebtMethod === 'va'"
                v-model="selectedDebtVaBank"
                class="mt-2"
                label="Pilih Bank VA"
                persistent-placeholder
                :items="availableDebtVaBankItems"
                item-title="title"
                item-value="value"
                variant="outlined"
                density="comfortable"
              />
            </VCardText>

            <VDivider />
            <VCardActions class="px-4 py-3 bg-grey-lighten-5">
              <VSpacer />
              <VBtn color="grey-darken-1" variant="text" @click="closeDebtPaymentDialog">
                Batal
              </VBtn>
              <VBtn color="primary" variant="flat" :loading="debtPaying" :disabled="debtPaying" @click="confirmDebtPayment">
                Lanjutkan Pembayaran
              </VBtn>
            </VCardActions>
          </VCard>
        </VDialog>

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
                      <span class="font-weight-bold">Jenis:</span>
                      <span>{{ item.package_name }}</span>
                    </div>

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
  min-width: 615px;
  width: 100%;
  table-layout: fixed;
}

.payment-method-label {
  gap: 14px;
  padding-block: 10px;
}

.payment-method-text {
  display: flex;
  flex-direction: column;
}

.history-summary-chips {
  align-items: flex-start;
}

.history-filter-card {
  border-radius: 18px;
}

.history-filter-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.history-filter-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.history-filter-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quota-history-panels {
  background: transparent;
}

.quota-history-list :deep(.v-list-item__prepend) {
  align-self: flex-start;
  margin-top: 2px;
}

:deep(.payment-method-radio .v-selection-control) {
  min-height: 56px;
}

@media (max-width: 600px) {
  .history-filter-card__header {
    flex-direction: column;
  }
}
</style>
