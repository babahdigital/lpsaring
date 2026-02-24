<script setup lang="ts">
import type { MonthlyUsageResponse, UserQuotaResponse, WeeklyUsageResponse } from '~/types/user'
import { useNuxtApp } from '#app'
import { useDebounceFn } from '@vueuse/core'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { usePromoStore } from '~/store/promo' // Import promo store
import { useApiFetch } from '~/composables/useApiFetch'
import { useAuthStore } from '~/store/auth'
import { useDisplay } from 'vuetify'
import { useDebtSettlementPayment } from '~/composables/useDebtSettlementPayment'
import { useSettingsStore } from '~/store/settings'

// Impor komponen PromoAnnouncement DIHAPUS, diganti dengan sistem global di app.vue
// const PromoAnnouncement = defineAsyncComponent(() => import('~/components/promo/PromoAnnouncement.vue'))
// Ganti import WeeklyUsageChart biasa dengan dua opsi
const WeeklyUsageChart = defineAsyncComponent(() => import('~/components/charts/WeeklyUsageChart.vue'))
const WeeklyUsageChartUnlimited = defineAsyncComponent(() => import('~/components/charts/WeeklyUsageChartUnlimited.vue'))
const MonthlyUsageChart = defineAsyncComponent(() => import('~/components/charts/MonthlyUsageChart.vue'))
const DeviceManagerCard = defineAsyncComponent(() => import('~/components/akun/DeviceManagerCard.vue'))

const promoStore = usePromoStore() // Inisialisasi promo store
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const display = useDisplay()

const deviceDialog = ref(false)
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
  const methods = coreApiEnabledMethods.value
  selectedDebtMethod.value = methods.includes(selectedDebtMethod.value) ? selectedDebtMethod.value : (methods[0] ?? 'qris')
  const banks = coreApiEnabledVaBanks.value
  selectedDebtVaBank.value = banks.includes(selectedDebtVaBank.value)
    ? selectedDebtVaBank.value
    : (banks.includes('bni') ? 'bni' : (banks[0] ?? 'bni'))
  showDebtPaymentDialog.value = true
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
  showDebtPaymentDialog.value = false
  void payDebt(body as any)
}

const chartReady = ref(false)
const chartDelayMs = computed(() => (display.smAndDown.value ? 1200 : 400))
let chartTimer: ReturnType<typeof setTimeout> | null = null

// --- TAMBAHAN BARU ---
// State untuk menampilkan notifikasi promo di dashboard
const showPromoWarning = ref(false) // Default false, akan diatur oleh watcher
const promoWarningMessage = computed(() => {
  if (promoStore.activePromo) {
    if (promoStore.activePromo.event_type === 'BONUS_REGISTRATION') {
      const bonusMb = promoStore.activePromo.bonus_value_mb ?? 0
      const gbValue = bonusMb > 0 ? (bonusMb / 1024) : 0
      const displayGb = gbValue % 1 === 0 ? gbValue : gbValue.toFixed(2)
      return `Ada promo bonus registrasi aktif! Dapatkan ${displayGb} GB kuota gratis.`
    }
    else if (promoStore.activePromo.event_type === 'GENERAL_ANNOUNCEMENT') {
      return `Ada pengumuman baru: "${promoStore.activePromo.name}". Cek segera!`
    }
  }
  return ''
})

// Watcher untuk mendeteksi promo aktif dari store dan menampilkan peringatan
watch(() => promoStore.activePromo, (newPromo) => {
  if (newPromo && !promoStore.isPromoDialogVisible) { // Tampilkan warning hanya jika dialog global tidak terlihat
    showPromoWarning.value = true
  }
  else {
    showPromoWarning.value = false
  }
}, { immediate: true }) // Jalankan segera saat komponen dimuat
// --- AKHIR TAMBAHAN BARU ---

// Fetch data kuota
const quotaApiUrl = computed(() => (authStore.isLoggedIn ? '/users/me/quota' : ''))
const { data: quotaData, pending: quotaPending, error: quotaError, refresh: refreshQuotaRaw } = useApiFetch<UserQuotaResponse>(
  quotaApiUrl,
  { server: false, key: 'userQuotaData', default: () => ({ success: false, total_quota_purchased_mb: 0, total_quota_used_mb: 0, remaining_mb: 0, quota_debt_auto_mb: 0, quota_debt_manual_mb: 0, quota_debt_total_mb: 0, quota_debt_total_estimated_rp: 0, hotspot_username: '...', last_sync_time: null, is_unlimited_user: false, quota_expiry_date: null }), immediate: false, watch: false },
)

// Fetch data penggunaan mingguan
const weeklyUsageApiUrl = computed(() => (authStore.isLoggedIn ? '/users/me/weekly-usage' : ''))
const { data: weeklyUsageData, pending: weeklyUsagePending, error: weeklyUsageError, refresh: refreshWeeklyUsageRaw } = useApiFetch<WeeklyUsageResponse>(
  weeklyUsageApiUrl,
  { server: false, key: 'weeklyUsageData', default: () => ({ success: false, weekly_data: [], period: { start_date: '', end_date: '' } }), immediate: false, watch: false },
)

// Fetch data penggunaan bulanan
const monthlyUsageApiUrl = computed(() => (authStore.isLoggedIn ? '/users/me/monthly-usage' : ''))
const { data: monthlyUsageData, pending: monthlyChartPending, error: monthlyChartError, refresh: refreshMonthlyUsageRaw } = useApiFetch<MonthlyUsageResponse>(
  monthlyUsageApiUrl,
  { server: false, key: 'monthlyUsageData', default: () => ({ success: false, monthly_data: [] }), immediate: false, watch: false },
)

interface WeeklySpendingResponse {
  categories: string[]
  series: Array<{ name: string; data: number[] }>
  total_this_week: number
}

const weeklySpendingApiUrl = computed(() => (authStore.isLoggedIn ? '/users/me/weekly-spending' : ''))
const { data: weeklySpendingData, pending: weeklySpendingPending, error: weeklySpendingError, refresh: refreshWeeklySpendingRaw } = useApiFetch<WeeklySpendingResponse>(
  weeklySpendingApiUrl,
  { server: false, key: 'weeklySpendingData', default: () => ({ categories: [], series: [{ name: 'Pengeluaran', data: [] }], total_this_week: 0 }), immediate: false, watch: false },
)

const fetchesInitiated = ref(false)
const minSkeletonTimePassed = ref(false)
const dashboardRenderKey = ref(0)
const hasLoadedOnce = ref(false)
const isRefreshingSilent = ref(false)

const isFetching = computed(() => {
  return quotaPending.value || weeklyUsagePending.value || monthlyChartPending.value || weeklySpendingPending.value
})

const shouldShowSkeleton = computed(() => {
  return fetchesInitiated.value && hasLoadedOnce.value === false && (isFetching.value || !minSkeletonTimePassed.value)
})

const hasError = computed(() => {
  return !!quotaError.value || !!weeklyUsageError.value || !!monthlyChartError.value || !!weeklySpendingError.value
})

const showErrorAlert = ref(true)

type RefresherFunction = () => Promise<void> | void

function createRefresher(rawRefresher: RefresherFunction | globalThis.Ref<unknown>): RefresherFunction {
  return async () => {
    if (typeof rawRefresher !== 'function')
      return
    if (!authStore.isLoggedIn)
      return
    showErrorAlert.value = true
    return rawRefresher()
  }
}

const refreshQuota = createRefresher(refreshQuotaRaw)
const refreshWeeklyUsage = createRefresher(refreshWeeklyUsageRaw)
const refreshMonthlyUsage = createRefresher(refreshMonthlyUsageRaw)
const refreshWeeklySpending = createRefresher(refreshWeeklySpendingRaw)

function preFetchActions() {
  fetchesInitiated.value = true
  minSkeletonTimePassed.value = false
  showErrorAlert.value = true
  setTimeout(() => {
    minSkeletonTimePassed.value = true
  }, 700)
}

async function performFetches() {
  try {
    await Promise.allSettled([
      refreshQuota(),
      refreshWeeklyUsage(),
      refreshMonthlyUsage(),
      refreshWeeklySpending(),
    ])
  }
  catch (_e) {
    console.error('Dashboard: Error saat Promise.allSettled untuk pengambilan data:', _e)
  }
}

async function initialFetch() {
  if (authStore.isLoggedIn) {
    preFetchActions()
    await performFetches()
    hasLoadedOnce.value = true
  }
  else {
    fetchesInitiated.value = true
    minSkeletonTimePassed.value = true
    hasLoadedOnce.value = true
  }
}

const deviceBindAttempted = ref(false)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)

async function tryBindCurrentDevice() {
  if (!authStore.isLoggedIn)
    return
  if (deviceBindAttempted.value)
    return
  deviceBindAttempted.value = true
  try {
    const { $api } = useNuxtApp()
    await $api('/users/me/devices/bind-current', { method: 'POST' })
  }
  catch {
    // Best-effort: bila gagal (mis. IP publik/proxy), jangan mengganggu UI.
  }
}

onMounted(() => {
  initialFetch()
  tryBindCurrentDevice()
  chartTimer = setTimeout(() => {
    chartReady.value = true
  }, chartDelayMs.value)
  if (authStore.isLoggedIn && pollingTimer.value == null) {
    pollingTimer.value = setInterval(() => {
      refreshAllData()
    }, 60_000)
  }
})

onUnmounted(() => {
  if (pollingTimer.value != null)
    clearInterval(pollingTimer.value)
  pollingTimer.value = null
  if (chartTimer != null)
    clearTimeout(chartTimer)
  chartTimer = null
})

watch(isFetching, (newValue, oldValue) => {
  if (fetchesInitiated.value && oldValue === true && newValue === false) {
    hasLoadedOnce.value = true
    nextTick(() => {
      dashboardRenderKey.value++
    })
  }
})

watch(() => authStore.isLoggedIn, (isLoggedIn, wasLoggedIn) => {
  if (isLoggedIn && !wasLoggedIn) {
    initialFetch()
    tryBindCurrentDevice()
    if (pollingTimer.value == null) {
      pollingTimer.value = setInterval(() => {
        refreshAllData()
      }, 60_000)
    }
  }
  else if (!isLoggedIn && wasLoggedIn) {
    quotaData.value = { success: false, total_quota_purchased_mb: 0, total_quota_used_mb: 0, remaining_mb: 0, quota_debt_auto_mb: 0, quota_debt_manual_mb: 0, quota_debt_total_mb: 0, quota_debt_total_estimated_rp: 0, hotspot_username: '...', last_sync_time: null, is_unlimited_user: false, quota_expiry_date: null }
    weeklyUsageData.value = { success: false, weekly_data: [], period: { start_date: '', end_date: '' } }
    monthlyUsageData.value = { success: false, monthly_data: [] }
    fetchesInitiated.value = false
    hasLoadedOnce.value = false
    showErrorAlert.value = false
    dashboardRenderKey.value++
    if (pollingTimer.value != null)
      clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
})

function formatDateTime(dateTimeString: string | null | undefined): string {
  if (dateTimeString == null)
    return 'N/A'
  try {
    const date = new Date(dateTimeString)
    if (Number.isNaN(date.getTime()))
      return 'Tanggal Invalid'

    return new Intl.DateTimeFormat('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: 'Asia/Makassar',
      hour12: false,
      timeZoneName: 'shortOffset',
    }).format(date).replace('GMT+8', 'WITA')
  }
  catch {
    return 'Error Format'
  }
}

function formatUsername(username: string | null | undefined): string {
  if (username == null)
    return 'Tidak Tersedia'
  return username.startsWith('+62') ? `0${username.substring(3)}` : username
}

function formatQuota(mbValue: number | null | undefined): string {
  const mb = Number(mbValue ?? 0)
  if (!Number.isFinite(mb) || mb <= 0)
    return '0 MB'
  if (mb < 1) {
    const kb = mb * 1024
    return `${Math.round(kb).toLocaleString('id-ID')} KB`
  }
  if (mb >= 1024) {
    const gb = mb / 1024
    const gbRounded = Math.round(gb * 100) / 100
    return `${gbRounded.toLocaleString('id-ID', { maximumFractionDigits: 2 })} GB`
  }
  return `${Math.round(mb).toLocaleString('id-ID')} MB`
}

function formatQuotaParts(mbValue: number | null | undefined): { value: string; unit: 'KB' | 'MB' | 'GB' } {
  const mb = Number(mbValue ?? 0)
  if (!Number.isFinite(mb) || mb <= 0)
    return { value: '0', unit: 'MB' }
  if (mb < 1) {
    const kb = Math.round(mb * 1024)
    return { value: kb.toLocaleString('id-ID'), unit: 'KB' }
  }
  if (mb >= 1024) {
    const gb = mb / 1024
    const gbRounded = Math.round(gb * 100) / 100
    return { value: gbRounded.toLocaleString('id-ID', { maximumFractionDigits: 2 }), unit: 'GB' }
  }
  return { value: Math.round(mb).toLocaleString('id-ID'), unit: 'MB' }
}

const debtAutoMb = computed(() => Number(quotaData.value?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(quotaData.value?.quota_debt_manual_mb ?? 0))
const debtTotalMb = computed(() => Number(quotaData.value?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))

const debtEstimatedRp = computed(() => Number(quotaData.value?.quota_debt_total_estimated_rp ?? 0))

function formatRp(amount: number | null | undefined): string {
  const v = Number(amount ?? 0)
  if (!Number.isFinite(v) || v <= 0)
    return 'Rp 0'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(v)
}

const weeklyUsedMb = computed(() => {
  const points = weeklyUsageData.value?.weekly_data
  if (!Array.isArray(points))
    return 0
  return points.reduce((acc, n) => acc + Number(n || 0), 0)
})

const avgDailyUsedMb = computed(() => {
  const total = Number(weeklyUsedMb.value || 0)
  if (!Number.isFinite(total) || total <= 0)
    return 0
  return Math.round((total / 7) * 100) / 100
})

const totalSpendingThisWeek = computed(() => {
  const v = Number((weeklySpendingData.value as any)?.total_this_week ?? 0)
  if (!Number.isFinite(v) || v <= 0)
    return 0
  return v
})

const debtTotalParts = computed(() => {
  const isUnlimited = quotaData.value?.is_unlimited_user === true
  if (isUnlimited)
    return { value: '0', unit: 'MB' as const }
  return formatQuotaParts(debtTotalMb.value)
})

const debtPctOfPurchased = computed(() => {
  const isUnlimited = quotaData.value?.is_unlimited_user === true
  if (isUnlimited)
    return 0
  const purchased = Number(quotaData.value?.total_quota_purchased_mb ?? 0)
  const debt = Number(debtTotalMb.value ?? 0)
  if (purchased <= 0 || debt <= 0)
    return 0
  const pct = (debt / purchased) * 100
  return Math.max(0, Math.min(999, Math.round(pct * 10) / 10))
})

const timeSpendingsChip = computed(() => {
  const isUnlimited = quotaData.value?.is_unlimited_user === true
  if (isUnlimited)
    return { label: 'Unlimited', color: 'success' as const }

  const debt = Number(debtTotalMb.value ?? 0)
  if (debt <= 0)
    return { label: '0%', color: 'success' as const }

  const pct = debtPctOfPurchased.value
  const label = `+${pct.toLocaleString('id-ID', { maximumFractionDigits: 1 })}%`
  const color = pct >= 50 ? ('error' as const) : (pct >= 20 ? ('warning' as const) : ('success' as const))
  return { label, color }
})

async function refreshAllDataLogic() {
  if (!authStore.isLoggedIn)
    return

  // Silent refresh: jangan tampilkan skeleton lagi jika data sudah pernah tampil.
  if (hasLoadedOnce.value)
    isRefreshingSilent.value = true
  showErrorAlert.value = true
  try {
    await performFetches()
  }
  finally {
    isRefreshingSilent.value = false
  }
}

const refreshAllData = useDebounceFn(refreshAllDataLogic, 500, { maxWait: 2000 })
useHead({ title: 'Dashboard User' })
</script>

<template>
  <VContainer fluid class="dashboard-page-container vuexy-dashboard-container pa-4 pa-md-6">
    <VRow>
      <VCol cols="12" class="d-flex align-center justify-end flex-wrap gap-2">
        <VBtn
          variant="tonal"
          size="small"
          prepend-icon="tabler-device-mobile"
          @click="deviceDialog = true"
        >
          Kelola Perangkat
        </VBtn>
      </VCol>
    </VRow>

    <VDialog v-model="deviceDialog" max-width="900" scrollable>
      <div class="pa-4">
        <DeviceManagerCard />
      </div>
    </VDialog>

    <div>
      <VProgressLinear
        v-if="isRefreshingSilent"
        indeterminate
        color="primary"
        height="2"
        class="mb-4"
      />

      <VAlert
        v-if="showPromoWarning"
        type="warning"
        variant="tonal"
        class="mb-6"
        closable
        @update:model-value="showPromoWarning = false"
      >
        {{ promoWarningMessage }}
      </VAlert>

      <ClientOnly>
        <div v-if="shouldShowSkeleton">
          <VRow class="match-height">
            <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
              <VRow>
                <VCol cols="12" sm="6">
                  <VSkeletonLoader type="card-avatar, subtitle, text" class="vuexy-skeleton-card" />
                </VCol>
                <VCol cols="12" sm="6">
                  <VSkeletonLoader type="card-avatar, subtitle, text" class="vuexy-skeleton-card" />
                </VCol>
              </VRow>
              <VSkeletonLoader type="image" height="300px" class="vuexy-skeleton-card" />
            </VCol>
            <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
              <VSkeletonLoader type="image" height="460px" class="vuexy-skeleton-card" />
            </VCol>
          </VRow>
        </div>

        <div v-else>
          <div v-if="hasError && showErrorAlert" class="mb-6 dashboard-error-alert-container">
            <VAlert
              type="error"
              density="comfortable"
              variant="tonal"
              color="error"
              prominent
              border="start"
              closable
              class="vuexy-alert"
              @update:model-value="showErrorAlert = false"
            >
              <template #title>
                <div class="d-flex align-center">
                  <VIcon start icon="tabler-alert-triangle" size="24" />
                  <h6 class="text-h6">
                    Terjadi Kesalahan Pemuatan Data
                  </h6>
                </div>
              </template>

              <div v-if="quotaError" class="mt-2 error-detail-section">
                <p class="font-weight-medium text-body-2">
                  Detail Error Kuota:
                </p>
                <p class="text-caption">
                  {{ (quotaError.message && quotaError.message.length > 0) ? quotaError.message : 'Tidak ada pesan error spesifik.' }}
                </p>
                <pre v-if="quotaError.data?.message" class="error-server-message">{{ quotaError.data.message }}</pre>
              </div>
              <div v-if="weeklyUsageError" class="mt-2 error-detail-section">
                <p class="font-weight-medium text-body-2">
                  Detail Error Mingguan:
                </p>
                <p class="text-caption">
                  {{ (weeklyUsageError.message && weeklyUsageError.message.length > 0) ? weeklyUsageError.message : 'Tidak ada pesan error spesifik.' }}
                </p>
                <pre v-if="weeklyUsageError.data?.message" class="error-server-message">{{ weeklyUsageError.data.message }}</pre>
              </div>
              <div v-if="monthlyChartError" class="mt-2 error-detail-section">
                <p class="font-weight-medium text-body-2">
                  Detail Error Bulanan:
                </p>
                <p class="text-caption">
                  {{ (monthlyChartError.message && monthlyChartError.message.length > 0) ? monthlyChartError.message : 'Tidak ada pesan error spesifik.' }}
                </p>
                <pre v-if="monthlyChartError.data?.message" class="error-server-message">{{ monthlyChartError.data.message }}</pre>
              </div>

              <template #actions>
                <VBtn color="error" variant="outlined" prepend-icon="tabler-refresh" size="small" @click="refreshAllData">
                  Coba Lagi Semua Data
                </VBtn>
              </template>
            </VAlert>
          </div>

          <div v-if="!hasError || !showErrorAlert" :key="dashboardRenderKey">
            <!-- Ringkasan 7 Hari (gaya Statistics seperti Vuexy ecommerce dashboard) -->
            <VCard class="vuexy-card mb-4" title="Ringkasan 7 Hari Terakhir">
              <VCardText>
                <VRow>
                  <VCol cols="12" sm="6" md="3">
                    <div class="d-flex align-center gap-4 mt-md-9 mt-0">
                      <VAvatar color="primary" variant="tonal" rounded size="40">
                        <VIcon icon="tabler-calendar-stats" />
                      </VAvatar>
                      <div class="d-flex flex-column">
                        <h5 class="text-h5">
                          {{ quotaData?.is_unlimited_user ? 'Unlimited' : formatQuota(weeklyUsedMb) }}
                        </h5>
                        <div class="text-sm">Terpakai (7 hari)</div>
                      </div>
                    </div>
                  </VCol>

                  <VCol cols="12" sm="6" md="3">
                    <div class="d-flex align-center gap-4 mt-md-9 mt-0">
                      <VAvatar color="info" variant="tonal" rounded size="40">
                        <VIcon icon="tabler-chart-bar" />
                      </VAvatar>
                      <div class="d-flex flex-column">
                        <h5 class="text-h5">
                          {{ quotaData?.is_unlimited_user ? 'Unlimited' : formatQuota(avgDailyUsedMb) }}
                        </h5>
                        <div class="text-sm">Rata-rata / hari</div>
                      </div>
                    </div>
                  </VCol>

                  <VCol cols="12" sm="6" md="3">
                    <div class="d-flex align-center gap-4 mt-md-9 mt-0">
                      <VAvatar color="success" variant="tonal" rounded size="40">
                        <VIcon icon="tabler-cash" />
                      </VAvatar>
                      <div class="d-flex flex-column">
                        <h5 class="text-h5">
                          {{ formatRp(totalSpendingThisWeek) }}
                        </h5>
                        <div class="text-sm">Pengeluaran (7 hari)</div>
                      </div>
                    </div>
                  </VCol>

                  <VCol cols="12" sm="6" md="3">
                    <div class="d-flex align-center gap-4 mt-md-9 mt-0">
                      <VAvatar color="warning" variant="tonal" rounded size="40">
                        <VIcon icon="tabler-battery" />
                      </VAvatar>
                      <div class="d-flex flex-column">
                        <h5 class="text-h5">
                          {{ quotaData?.is_unlimited_user ? 'Unlimited' : formatQuota(quotaData?.remaining_mb) }}
                        </h5>
                        <div class="text-sm">Kuota tersisa</div>
                      </div>
                    </div>
                  </VCol>
                </VRow>
              </VCardText>
            </VCard>

            <VRow class="match-height">
              <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
                <VRow class="fixed-height-cards">
                  <VCol cols="12" sm="6">
                    <VCard class="d-flex flex-column vuexy-card h-100">
                      <VCardItem class="vuexy-card-header">
                        <VCardTitle class="vuexy-card-title">
                          <VIcon icon="tabler-info-circle" class="me-2" />Informasi
                        </VCardTitle>
                      </VCardItem>
                      <VDivider />
                      <VCardText class="d-flex align-center py-3 px-4">
                        <VIcon icon="tabler-wifi" size="20" class="me-3" />
                        <span class="text-body-2 flex-grow-1">Username</span>
                        <span class="text-body-2 font-weight-medium text-truncate" :title="formatUsername(quotaData?.hotspot_username)">
                          {{ formatUsername(quotaData?.hotspot_username) }}
                        </span>
                      </VCardText>
                    </VCard>
                  </VCol>
                  <VCol cols="12" sm="6">
                    <VCard class="d-flex flex-column vuexy-card h-100">
                      <VCardItem class="vuexy-card-header">
                        <VCardTitle class="vuexy-card-title">
                          <VIcon icon="tabler-clock-check" class="me-2" />Sinkronisasi
                        </VCardTitle>
                      </VCardItem>
                      <VDivider />
                      <VCardText class="d-flex align-center py-3 px-4">
                        <VIcon icon="tabler-clock-check" size="20" class="me-3" />
                        <span class="text-body-2 flex-grow-1">Terakhir</span>
                        <span class="text-body-2 font-weight-medium text-medium-emphasis text-truncate" :title="quotaData?.last_sync_time != null ? formatDateTime(quotaData.last_sync_time) : 'N/A'">
                          {{ quotaData?.last_sync_time != null ? formatDateTime(quotaData.last_sync_time) : 'N/A' }}
                        </span>
                      </VCardText>
                    </VCard>
                  </VCol>
                </VRow>

                <VCard class="d-flex flex-column vuexy-card">
                  <VCardText class="py-5">
                    <div class="d-flex flex-column ps-3">
                      <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-4">
                        <div class="d-flex align-center flex-wrap ga-2">
                          <h5 class="text-h5 mb-0 text-no-wrap">
                            Tunggakan Kuota
                          </h5>

                          <VChip
                            size="x-small"
                            label
                            variant="tonal"
                            color="primary"
                          >
                            {{ quotaData?.is_unlimited_user ? 'Rp 0' : formatRp(debtEstimatedRp) }}
                          </VChip>

                          <VChip
                            :color="timeSpendingsChip.color"
                            label
                            size="small"
                          >
                            {{ timeSpendingsChip.label }}
                          </VChip>
                        </div>

                        <VBtn
                          v-if="!quotaData?.is_unlimited_user && debtTotalMb > 0 && debtEstimatedRp > 0"
                          size="small"
                          color="warning"
                          variant="flat"
                          prepend-icon="tabler-credit-card"
                          :loading="debtPaying"
                          :disabled="debtPaying"
                          @click="handleDebtPayClick()"
                        >
                          Lunasi
                        </VBtn>
                      </div>

                      <VList class="debt-card-list" density="compact">
                        <VListItem class="py-2">
                          <template #prepend>
                            <VAvatar color="primary" variant="tonal" rounded size="38" class="me-1">
                              <VIcon icon="tabler-cash" size="22" />
                            </VAvatar>
                          </template>
                          <VListItemTitle class="me-2">Estimasi</VListItemTitle>
                          <template #append>
                            <span class="text-body-1 font-weight-medium">
                              {{ quotaData?.is_unlimited_user ? 'Rp 0' : formatRp(debtEstimatedRp) }}
                            </span>
                          </template>
                        </VListItem>

                        <VDivider class="my-0" />

                        <VListItem v-if="!quotaData?.is_unlimited_user && debtTotalMb > 0" class="py-2">
                          <template #prepend>
                            <VAvatar color="info" variant="tonal" rounded size="38" class="me-1">
                              <VIcon icon="tabler-robot" size="22" />
                            </VAvatar>
                          </template>
                          <VListItemTitle class="me-2">Tunggakan otomatis</VListItemTitle>
                          <template #append>
                            <span class="text-body-1 font-weight-medium">
                              {{ formatQuota(debtAutoMb) }}
                            </span>
                          </template>
                        </VListItem>

                        <VDivider v-if="!quotaData?.is_unlimited_user && debtManualMb > 0" class="my-0" />

                        <VListItem v-if="!quotaData?.is_unlimited_user && debtManualMb > 0" class="py-2">
                          <template #prepend>
                            <VAvatar color="secondary" variant="tonal" rounded size="38" class="me-1">
                              <VIcon icon="tabler-hand-stop" size="22" />
                            </VAvatar>
                          </template>
                          <VListItemTitle class="me-2">Tunggakan manual</VListItemTitle>
                          <template #append>
                            <span class="text-body-1 font-weight-medium">
                              {{ formatQuota(debtManualMb) }}
                            </span>
                          </template>
                        </VListItem>
                      </VList>
                    </div>
                  </VCardText>
                </VCard>

                <template v-if="chartReady">
                  <template v-if="quotaData?.is_unlimited_user">
                    <WeeklyUsageChartUnlimited
                      :weekly-usage-data="weeklyUsageData"
                      :parent-loading="isFetching"
                      :parent-error="weeklyUsageError"
                      :dashboard-render-key="dashboardRenderKey"
                      class="dashboard-chart-card"
                      @refresh="refreshAllData"
                    />
                  </template>
                  <template v-else>
                    <WeeklyUsageChart
                      :quota-data="quotaData"
                      :weekly-usage-data="weeklyUsageData"
                      :parent-loading="isFetching"
                      :parent-error="quotaError || weeklyUsageError"
                      :dashboard-render-key="dashboardRenderKey"
                      class="dashboard-chart-card"
                      @refresh="refreshAllData"
                    />
                  </template>
                </template>
                <template v-else>
                  <VSkeletonLoader type="image" height="300px" class="vuexy-skeleton-card" />
                </template>
              </VCol>

              <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
                <template v-if="chartReady">
                  <MonthlyUsageChart
                    :monthly-data="monthlyUsageData"
                    :parent-loading="isFetching"
                    :parent-error="monthlyChartError"
                    :dashboard-render-key="dashboardRenderKey"
                    class="dashboard-chart-card"
                  />
                </template>
                <template v-else>
                  <VSkeletonLoader type="image" height="460px" class="vuexy-skeleton-card" />
                </template>
              </VCol>
            </VRow>

          </div>
        </div>

        <template #fallback>
          <div class="fill-height d-flex align-center justify-center" style="min-height: 80vh;">
            <VProgressCircular indeterminate color="primary" size="64" />
            <p class="ml-4 text-body-1">
              Memuat komponen dashboard...
            </p>
          </div>
        </template>
      </ClientOnly>
    </div>

    <VDialog v-model="showDebtPaymentDialog" max-width="420">
      <VCard rounded="lg">
        <VCardTitle class="d-flex align-center py-3 px-4 bg-grey-lighten-4 border-b">
          <VIcon icon="tabler-credit-card" color="primary" start />
          <span class="text-h6 font-weight-medium">Pilih Metode Pembayaran</span>
          <VSpacer />
          <VBtn icon="tabler-x" flat size="small" variant="text" @click="showDebtPaymentDialog = false" />
        </VCardTitle>

        <VCardText class="px-4 pt-4">
          <p class="text-caption text-medium-emphasis mb-3">
            Tunggakan: <span class="font-weight-medium">{{ formatRp(debtEstimatedRp) }}</span>
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
          <VBtn color="grey-darken-1" variant="text" @click="showDebtPaymentDialog = false">
            Batal
          </VBtn>
          <VBtn color="primary" variant="flat" :loading="debtPaying" :disabled="debtPaying" @click="confirmDebtPayment">
            Lanjutkan Pembayaran
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </VContainer>
</template>

<style scoped>
.vuexy-dashboard-container {
  max-width: 1440px;
  margin-left: auto;
  margin-right: auto;
}

.vuexy-page-title {
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
  font-weight: 600;
}

.match-height > [class*='col-'] {
  display: flex;
  flex-direction: column;
}

.match-height > [class*='col-'] > .v-card,
.match-height > [class*='col-'] > .dashboard-chart-card {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.payment-method-label {
  gap: 14px;
  padding-block: 10px;
}

.payment-method-text {
  display: flex;
  flex-direction: column;
}

:deep(.payment-method-radio .v-selection-control) {
  min-height: 56px;
}
.match-height > [class*='col-'] > .dashboard-chart-card > :deep(.v-card) {
    height: 100%;
    display: flex;
    flex-direction: column;
  overflow: visible;
}

.chart-column {
  min-height: 460px;
}

.dashboard-chart-card {
  flex: 1 1 auto;
  min-width: 300px;
  position: relative;
}

.vuexy-card {
  border-radius: 0.75rem;
  box-shadow: 0 2px 10px 0 rgba(var(--v-shadow-key-umbra-color), 0.1);
  transition: box-shadow 0.25s ease-in-out;
}

.vuexy-card:hover {
  box-shadow: 0 4px 25px 0 rgba(var(--v-shadow-key-umbra-color), 0.15);
}

.vuexy-card-header {
  background: rgba(var(--v-theme-primary), 0.05);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: 1rem;
  padding-bottom: 1rem;
}

.vuexy-card-title {
  color: rgba(var(--v-theme-primary), 1);
  font-weight: 600;
  letter-spacing: 0.15px;
  font-size: 1.125rem;
  display: flex;
  align-items: center;
}

.vuexy-skeleton-card {
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: var(--v-card-border-radius, 0.75rem);
}

.v-list-item {
  min-height: 38px;
}
.v-list-item__append .font-weight-medium,
.v-list-item__append .font-weight-bold {
  white-space: nowrap;
}

.v-list.v-list--density-compact {
  padding-block: 0.25rem;
}
.v-list-item.px-4 {
  padding-inline: 1rem !important;
}

.dashboard-error-alert-container {
  width: 100%;
  max-width: 900px;
  margin-left: auto;
  margin-right: auto;
}

.vuexy-alert {
  border-radius: 0.75rem;
}

.vuexy-alert .error-detail-section {
  margin-top: 0.5rem;
  padding: 0.75rem;
  background-color: rgba(var(--v-theme-error), 0.08);
  border-radius: 6px;
  border: 1px solid rgba(var(--v-theme-error), 0.15);
}
.vuexy-alert .error-server-message {
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 70px;
  overflow-y: auto;
  background-color: rgba(var(--v-theme-on-surface), 0.05);
  padding: 0.375rem 0.75rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-top: 0.25rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-family: monospace;
}

.ga-4 {
  gap: 1.5rem;
}

.card-list {
  --v-card-list-gap: 1.5rem;
}

@media (max-width: 959.98px) {
  .chart-column {
    min-height: auto;
  }
  .ga-4 {
    gap: 1rem;
  }
  .fixed-height-cards {
    min-height: 100px;
  }
}

@media (max-width: 599.98px) {
  .dashboard-page-container {
    padding: 0.75rem;
  }
  .vuexy-dashboard-container {
    max-width: 100%;
  }
  .dashboard-chart-card {
    min-width: 0;
  }
  .ga-4 {
    gap: 0.75rem;
  }
  .text-h5.vuexy-page-title {
    font-size: 1.25rem !important;
  }
  .vuexy-card-title {
    font-size: 1rem;
  }
  .dashboard-error-alert-container {
    max-width: 100%;
  }
  .fixed-height-cards {
    min-height: auto;
  }
}

.fixed-height-cards {
  min-height: auto;
  margin-bottom: 0.5rem;
}

.vuexy-card {
  height: 100%;
}
</style>
