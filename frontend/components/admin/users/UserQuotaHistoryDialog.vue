<script lang="ts" setup>
import type { QuotaHistoryFilters, QuotaHistoryItem, QuotaHistoryResponse, QuotaHistorySummary } from '~/types/user'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '@/composables/useSnackbar'

interface UserLite {
  id: string
  full_name: string
  phone_number: string
}

type HistoryRangePreset = 'today' | '3d' | '7d' | '30d' | 'custom'
type FixedHistoryRangePreset = Exclude<HistoryRangePreset, 'custom'>

interface HistoryPresetOption {
  value: HistoryRangePreset
  label: string
  icon: string
}

const props = defineProps<{ modelValue: boolean, user: UserLite | null }>()
const emit = defineEmits(['update:modelValue'])

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()

const DEFAULT_ITEMS_PER_PAGE = 50
const MAX_FILTER_DAYS = 90
const DEFAULT_RANGE_PRESET: FixedHistoryRangePreset = '30d'
const presetOptions: HistoryPresetOption[] = [
  { value: 'today', label: 'Hari Ini', icon: 'tabler-calendar' },
  { value: '3d', label: '3 Hari', icon: 'tabler-calendar' },
  { value: '7d', label: '1 Minggu', icon: 'tabler-calendar' },
  { value: '30d', label: '1 Bulan', icon: 'tabler-calendar' },
  { value: 'custom', label: 'Kustom', icon: 'tabler-filter' },
]

const loading = ref(false)
const items = ref<QuotaHistoryItem[]>([])
const summary = ref<QuotaHistorySummary | null>(null)
const filters = ref<QuotaHistoryFilters | null>(null)
const page = ref(1)
const totalItems = ref(0)
const itemsPerPage = ref(DEFAULT_ITEMS_PER_PAGE)
const rangePreset = ref<HistoryRangePreset>(DEFAULT_RANGE_PRESET)
const searchQuery = ref('')
const draftSearchQuery = ref('')
const startDate = ref<Date | null>(null)
const endDate = ref<Date | null>(null)
const isStartDateMenuOpen = ref(false)
const isEndDateMenuOpen = ref(false)
const isMobile = computed(() => smAndDown.value)
const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / itemsPerPage.value)))
const shouldShowPagination = computed(() => totalItems.value > itemsPerPage.value)
const visibleStart = computed(() => {
  if (items.value.length === 0)
    return 0

  return ((page.value - 1) * itemsPerPage.value) + 1
})
const visibleEnd = computed(() => {
  if (items.value.length === 0)
    return 0

  return Math.min(totalItems.value, visibleStart.value + items.value.length - 1)
})
const paginationLabel = computed(() => {
  if (items.value.length === 0)
    return 'Belum ada event.'

  return `Menampilkan ${visibleStart.value}-${visibleEnd.value} dari ${totalItems.value} event`
})
const activeFilterLabel = computed(() => filters.value?.label || formatDateRangeLabel(startDate.value, endDate.value))
const activeSearchText = computed(() => {
  const serverSearch = String(filters.value?.search ?? '').trim()
  return serverSearch !== '' ? serverSearch : searchQuery.value
})
const retentionDays = computed(() => Number(filters.value?.retention_days ?? MAX_FILTER_DAYS))

function close() {
  emit('update:modelValue', false)
}

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

function formatDate(value: Date | null): string {
  return value !== null
    ? value.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' })
    : ''
}

function formatDateRangeLabel(start: Date | null, end: Date | null): string {
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
    return formatDate(effectiveStart)

  return `${formatDate(effectiveStart)} - ${formatDate(effectiveEnd)}`
}

function inferPresetFromDates(start: Date | null, end: Date | null): HistoryRangePreset {
  const effectiveStart = start ?? end
  const effectiveEnd = end ?? start
  if (effectiveStart === null || effectiveEnd === null)
    return DEFAULT_RANGE_PRESET

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

function createPresetRange(preset: FixedHistoryRangePreset): { start: Date, end: Date } {
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

function setPresetRange(preset: FixedHistoryRangePreset) {
  const range = createPresetRange(preset)
  startDate.value = range.start
  endDate.value = range.end
  rangePreset.value = preset
}

function syncFiltersFromResponse(nextFilters?: QuotaHistoryFilters | null) {
  filters.value = nextFilters ?? null
  if (!nextFilters)
    return

  const nextStart = parseYmd(nextFilters.start_date)
  const nextEnd = parseYmd(nextFilters.end_date)
  if (nextStart !== null)
    startDate.value = nextStart
  if (nextEnd !== null)
    endDate.value = nextEnd

  searchQuery.value = String(nextFilters.search ?? '').trim()
  draftSearchQuery.value = searchQuery.value
  rangePreset.value = inferPresetFromDates(startDate.value, endDate.value)
}

function buildHistoryParams(options?: { includePagination?: boolean }) {
  const params: Record<string, string | number | undefined> = {
    startDate: startDate.value ? toYmd(startDate.value) : undefined,
    endDate: endDate.value ? toYmd(endDate.value) : undefined,
    search: searchQuery.value || undefined,
  }

  if (options?.includePagination !== false) {
    params.page = page.value
    params.itemsPerPage = itemsPerPage.value
  }

  return params
}

function buildPdfQueryString(): string {
  const query = new URLSearchParams({ format: 'pdf' })
  const params = buildHistoryParams({ includePagination: false })

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '')
      query.set(key, String(value))
  }

  return query.toString()
}

function categoryColor(category?: string | null): string {
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

function categoryLabel(category?: string | null): string {
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

function formatQuotaSummary(value?: number | null): string {
  const numericValue = Number(value ?? 0)

  if (!Number.isFinite(numericValue) || numericValue <= 0)
    return '0 KB'
  if (numericValue < 1)
    return `${Math.round(numericValue * 1024).toLocaleString('id-ID')} KB`
  if (numericValue >= 1024)
    return `${(numericValue / 1024).toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} GB`

  return `${numericValue.toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} MB`
}

function normalizeSelectedRange(): boolean {
  let normalizedStart = startDate.value ? cloneDate(startDate.value) : null
  let normalizedEnd = endDate.value ? cloneDate(endDate.value) : null

  if (normalizedStart === null && normalizedEnd === null) {
    setPresetRange(DEFAULT_RANGE_PRESET)
    normalizedStart = startDate.value ? cloneDate(startDate.value) : null
    normalizedEnd = endDate.value ? cloneDate(endDate.value) : null
  }

  if (normalizedStart === null && normalizedEnd !== null)
    normalizedStart = cloneDate(normalizedEnd)
  if (normalizedEnd === null && normalizedStart !== null)
    normalizedEnd = cloneDate(normalizedStart)

  if (normalizedStart === null || normalizedEnd === null)
    return false

  if (normalizedStart.getTime() > normalizedEnd.getTime()) {
    showSnackbar({ type: 'warning', title: 'Filter Tanggal', text: 'Tanggal akhir tidak boleh sebelum tanggal mulai.' })
    return false
  }

  const totalDays = Math.floor((normalizedEnd.getTime() - normalizedStart.getTime()) / 86_400_000) + 1
  if (totalDays > MAX_FILTER_DAYS) {
    showSnackbar({ type: 'warning', title: 'Filter Tanggal', text: `Rentang maksimal ${MAX_FILTER_DAYS} hari.` })
    return false
  }

  startDate.value = normalizedStart
  endDate.value = normalizedEnd
  return true
}

function openPdf() {
  if (!props.user)
    return

  window.open(`/api/admin/users/${props.user.id}/quota-history/export?${buildPdfQueryString()}`, '_blank', 'noopener')
}

async function fetchHistory() {
  if (!props.user || !normalizeSelectedRange())
    return

  loading.value = true
  items.value = []
  summary.value = null
  totalItems.value = 0
  try {
    const resp = await $api<QuotaHistoryResponse>(`/admin/users/${props.user.id}/quota-history`, {
      params: buildHistoryParams(),
    })
    items.value = Array.isArray(resp.items) ? resp.items : []
    summary.value = resp.summary ?? null
    totalItems.value = Number(resp.totalItems ?? items.value.length)
    itemsPerPage.value = Number(resp.itemsPerPage ?? DEFAULT_ITEMS_PER_PAGE)
    page.value = Number(resp.page ?? page.value)
    syncFiltersFromResponse(resp.filters ?? null)
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Riwayat Kuota', text: error?.data?.message || 'Gagal memuat riwayat mutasi kuota.' })
  }
  finally {
    loading.value = false
  }
}

async function applyFilters() {
  if (loading.value)
    return

  if (!normalizeSelectedRange())
    return

  searchQuery.value = draftSearchQuery.value.trim()
  page.value = 1
  await fetchHistory()
}

async function resetFilters(shouldFetch = true) {
  filters.value = null
  summary.value = null
  searchQuery.value = ''
  draftSearchQuery.value = ''
  page.value = 1
  totalItems.value = 0
  itemsPerPage.value = DEFAULT_ITEMS_PER_PAGE
  setPresetRange(DEFAULT_RANGE_PRESET)

  if (shouldFetch && props.modelValue)
    await fetchHistory()
}

async function applyPreset(preset: FixedHistoryRangePreset) {
  if (loading.value)
    return

  setPresetRange(preset)
  searchQuery.value = draftSearchQuery.value.trim()
  page.value = 1
  await fetchHistory()
}

function enableCustomRange() {
  rangePreset.value = 'custom'
  if (startDate.value === null && endDate.value === null)
    setPresetRange(DEFAULT_RANGE_PRESET)
}

function handleStartDatePicked(value: unknown) {
  startDate.value = normalizePickerDate(value)
  rangePreset.value = 'custom'
  if (startDate.value && endDate.value && startDate.value.getTime() > endDate.value.getTime())
    endDate.value = cloneDate(startDate.value)
  isStartDateMenuOpen.value = false
}

function handleEndDatePicked(value: unknown) {
  endDate.value = normalizePickerDate(value)
  rangePreset.value = 'custom'
  if (startDate.value && endDate.value && endDate.value.getTime() < startDate.value.getTime())
    startDate.value = cloneDate(endDate.value)
  isEndDateMenuOpen.value = false
}

async function clearStartDate() {
  startDate.value = null
  rangePreset.value = 'custom'
  if (props.modelValue && searchQuery.value === '' && endDate.value === null)
    await resetFilters()
}

async function clearEndDate() {
  endDate.value = null
  rangePreset.value = 'custom'
  if (props.modelValue && searchQuery.value === '' && startDate.value === null)
    await resetFilters()
}

async function clearSearch() {
  draftSearchQuery.value = ''
  if (searchQuery.value !== '') {
    searchQuery.value = ''
    page.value = 1
    await fetchHistory()
  }
}

function changePage(nextPage: number) {
  if (loading.value)
    return

  page.value = nextPage
  fetchHistory()
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen)
      void resetFilters()
  },
)

watch(
  () => props.user?.id,
  () => {
    if (props.modelValue)
      void resetFilters()
  },
)
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    :fullscreen="isMobile"
    :max-width="isMobile ? undefined : 1180"
    persistent
    @update:model-value="close"
  >
    <VCard v-if="props.user" class="history-dialog-card">
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

      <AppPerfectScrollbar class="history-dialog__scroll" :native-scroll="isMobile">
        <div class="history-dialog__content">
        <div class="history-summary-chips d-flex flex-wrap gap-2 mb-4">
          <VChip size="small" label color="info" variant="tonal">
            {{ props.user.full_name }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            {{ props.user.phone_number }}
          </VChip>
          <VChip v-if="summary" size="small" label color="primary" variant="tonal">
            Event: {{ visibleStart }}-{{ visibleEnd }} / {{ totalItems }}
          </VChip>
          <VChip v-if="summary" size="small" label color="success" variant="tonal">
            Beli bersih: {{ formatQuotaSummary(summary.total_net_purchased_mb) }}
          </VChip>
          <VChip v-if="summary" size="small" label color="warning" variant="tonal">
            Pakai bersih: {{ formatQuotaSummary(summary.total_net_used_mb) }}
          </VChip>
          <VChip size="small" label color="secondary" variant="tonal">
            Periode: {{ activeFilterLabel }}
          </VChip>
          <VChip v-if="activeSearchText" size="small" label color="secondary" variant="tonal">
            Cari: {{ activeSearchText }}
          </VChip>
          <VChip size="small" label color="default" variant="tonal">
            Retensi: {{ retentionDays }} hari
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
                  Pilih periode harian, 3 hari, mingguan, atau bulanan. Data tersimpan maksimal {{ retentionDays }} hari.
                </div>
              </div>
              <VBtn size="small" variant="text" color="secondary" prepend-icon="tabler-filter-off" @click="resetFilters()">
                Reset
              </VBtn>
            </div>

            <div class="history-filter-presets mt-4">
              <VBtn
                v-for="preset in presetOptions"
                :key="preset.value"
                size="small"
                :color="rangePreset === preset.value ? 'primary' : 'default'"
                :variant="rangePreset === preset.value ? 'flat' : 'tonal'"
                :prepend-icon="preset.icon"
                @click="preset.value === 'custom' ? enableCustomRange() : applyPreset(preset.value)"
              >
                {{ preset.label }}
              </VBtn>
            </div>

            <VRow class="mt-1">
              <VCol cols="12" md="4">
                <VTextField
                  v-model="draftSearchQuery"
                  label="Cari event / aktor / catatan"
                  placeholder="Contoh: pembelian, Admin, tunggakan"
                  prepend-inner-icon="tabler-search"
                  clearable
                  hide-details="auto"
                  @keyup.enter="applyFilters"
                  @click:clear="clearSearch"
                />
              </VCol>
              <VCol cols="12" sm="6" md="3">
                <VTextField
                  id="quota-history-start-date"
                  :model-value="formatDate(startDate)"
                  label="Tanggal Mulai"
                  readonly
                  clearable
                  prepend-inner-icon="tabler-calendar"
                  @click:clear="clearStartDate"
                />
                <VMenu v-model="isStartDateMenuOpen" activator="#quota-history-start-date" :close-on-content-click="false">
                  <VDatePicker v-model="startDate" no-title color="primary" :max="new Date()" @update:model-value="handleStartDatePicked" />
                </VMenu>
              </VCol>
              <VCol cols="12" sm="6" md="3">
                <VTextField
                  id="quota-history-end-date"
                  :model-value="formatDate(endDate)"
                  label="Tanggal Akhir"
                  readonly
                  clearable
                  :disabled="!startDate"
                  prepend-inner-icon="tabler-calendar"
                  @click:clear="clearEndDate"
                />
                <VMenu v-model="isEndDateMenuOpen" activator="#quota-history-end-date" :close-on-content-click="false">
                  <VDatePicker v-model="endDate" no-title color="primary" :min="startDate || undefined" :max="new Date()" @update:model-value="handleEndDatePicked" />
                </VMenu>
              </VCol>
              <VCol cols="12" md="2" class="d-flex align-end">
                <VBtn block color="primary" prepend-icon="tabler-filter" :loading="loading" @click="applyFilters">
                  Terapkan
                </VBtn>
              </VCol>
            </VRow>

            <div class="history-filter-meta mt-3">
              <VChip size="small" color="primary" variant="tonal" prepend-icon="tabler-calendar">
                {{ activeFilterLabel }}
              </VChip>
              <VChip v-if="activeSearchText" size="small" color="secondary" variant="tonal" prepend-icon="tabler-search">
                Cari: {{ activeSearchText }}
              </VChip>
              <VChip size="small" color="default" variant="tonal" prepend-icon="tabler-database">
                Maks {{ retentionDays }} hari tersimpan
              </VChip>
            </div>
          </VCardText>
        </VCard>

        <VAlert
          v-if="summary"
          type="info"
          variant="tonal"
          density="compact"
          icon="tabler-info-circle"
          class="mb-4"
        >
          Filter aktif: <strong>{{ activeFilterLabel }}</strong>
          • Rentang event hasil: <strong>{{ summary.first_event_at_display || '-' }}</strong> sampai <strong>{{ summary.last_event_at_display || '-' }}</strong>
          • Periode ini pemakaian: <strong>{{ summary.usage_events }}</strong>
          • Pembelian: <strong>{{ summary.purchase_events }}</strong>
          • Tunggakan: <strong>{{ summary.debt_events }}</strong>
          • Kebijakan: <strong>{{ summary.policy_events }}</strong>
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
                  Tunggakan {{ item.deltas_display.debt_total }}
                </VChip>
                <VChip v-if="item.deltas_display.remaining_after" size="small" color="default" variant="tonal" label>
                  Quota {{ item.deltas_display.remaining_after }}
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

        <div v-else class="history-table-shell">
          <VTable density="compact" class="history-table">
            <thead>
              <tr>
                <th class="history-table__time">Waktu</th>
                <th class="history-table__event">Event</th>
                <th class="history-table__change">Perubahan</th>
                <th class="history-table__quota">Quota</th>
                <th class="history-table__detail">Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id">
                <td class="history-table__time align-top">
                  <div class="text-no-wrap">{{ item.created_at_display || '-' }}</div>
                </td>
                <td class="history-table__event align-top">
                  <div class="font-weight-medium">{{ item.title }}</div>
                  <VChip size="x-small" :color="categoryColor(item.category)" label class="mt-2">
                    {{ categoryLabel(item.category) }}
                  </VChip>
                </td>
                <td class="history-table__change align-top">
                  <div v-if="item.deltas_display.purchased || item.deltas_display.used || item.deltas_display.debt_total" class="history-change-list">
                    <div v-if="item.deltas_display.purchased" class="history-change-list__item text-no-wrap">
                      Beli {{ item.deltas_display.purchased }}
                    </div>
                    <div v-if="item.deltas_display.used" class="history-change-list__item text-no-wrap">
                      Pakai {{ item.deltas_display.used }}
                    </div>
                    <div v-if="item.deltas_display.debt_total" class="history-change-list__item text-no-wrap">
                      Tunggakan {{ item.deltas_display.debt_total }}
                    </div>
                  </div>
                  <div v-else class="text-medium-emphasis">-</div>
                </td>
                <td class="history-table__quota align-top">
                  <div class="history-table__quota-value text-no-wrap">
                    {{ item.deltas_display.remaining_after || '-' }}
                  </div>
                </td>
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

        <div v-if="shouldShowPagination" class="history-pagination">
          <div class="text-caption text-medium-emphasis">
            {{ paginationLabel }}
          </div>
          <VPagination
            :model-value="page"
            :length="totalPages"
            :total-visible="isMobile ? 5 : 7"
            rounded="circle"
            density="comfortable"
            @update:model-value="changePage"
          />
        </div>
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

.history-dialog-card {
  overflow: hidden;
}

.history-dialog__scroll {
  max-height: 72vh;
}

.history-dialog__content {
  padding: 20px;
  padding-bottom: 28px;
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

.history-table-shell {
  margin-top: 4px;
  position: relative;
  isolation: isolate;
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.08);
}

.history-table :deep(.v-table__wrapper) {
  overflow: visible;
  background: transparent;
}

.history-table :deep(table) {
  min-width: 1040px;
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: transparent;
}

.history-table {
  min-width: 1040px;
}

.history-table :deep(thead),
.history-table :deep(thead tr) {
  background: rgb(var(--v-theme-surface));
}

.history-table :deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 4;
  background-color: rgb(var(--v-theme-surface));
  background-image: linear-gradient(rgb(var(--v-theme-surface)), rgb(var(--v-theme-surface)));
  background-clip: padding-box;
  box-shadow: inset 0 -1px rgba(var(--v-theme-on-surface), 0.08), 0 10px 18px rgba(var(--v-theme-on-surface), 0.04);
  transform: translateZ(0);
}

.history-table :deep(thead th:first-child) {
  border-top-left-radius: 16px;
}

.history-table :deep(thead th:last-child) {
  border-top-right-radius: 16px;
}

.history-table :deep(tbody tr:nth-child(even)) {
  background: rgba(var(--v-theme-on-surface), 0.015);
}

.history-table__time {
  min-width: 152px;
}

.history-table__event {
  min-width: 250px;
}

.history-table__change {
  min-width: 158px;
}

.history-table__quota {
  min-width: 118px;
}

.history-table__quota-value {
  font-weight: 600;
}

.history-table__detail {
  min-width: 360px;
  width: 100%;
}

.history-change-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-change-list__item {
  line-height: 1.35;
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

.history-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.history-dialog__scroll :deep(.ps__rail-x),
.history-dialog__scroll :deep(.ps__rail-y) {
  opacity: 1 !important;
  background: rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 999px;
}

.history-dialog__scroll :deep(.ps__rail-x) {
  height: 10px;
  left: 16px !important;
  right: 16px !important;
  bottom: 10px !important;
}

.history-dialog__scroll :deep(.ps__thumb-x),
.history-dialog__scroll :deep(.ps__thumb-y) {
  background: rgba(var(--v-theme-primary), 0.55);
  border-radius: 999px;
}

.history-dialog__scroll :deep(.ps__thumb-x) {
  height: 10px;
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
    max-height: calc(100vh - 152px);
  }

  .history-dialog__content {
    min-width: 0;
    padding: 16px;
    padding-bottom: 24px;
  }

  .history-filter-card__header {
    flex-direction: column;
  }

  .history-mobile-card__header {
    flex-direction: column;
  }

  .history-pagination {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>