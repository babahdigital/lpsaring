<script setup lang="ts">
import type { MonthlyUsageResponse, UserQuotaResponse, WeeklyUsageResponse } from '~/types/user'
import { useCookie, useFetch } from '#app'
import { useDebounceFn } from '@vueuse/core'
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '~/store/auth'
import { usePromoStore } from '~/store/promo' // Import promo store

// Impor komponen PromoAnnouncement DIHAPUS, diganti dengan sistem global di app.vue
// const PromoAnnouncement = defineAsyncComponent(() => import('~/components/promo/PromoAnnouncement.vue'))
// Ganti import WeeklyUsageChart biasa dengan dua opsi
const WeeklyUsageChart = defineAsyncComponent(() => import('~/components/charts/WeeklyUsageChart.vue'))
const WeeklyUsageChartUnlimited = defineAsyncComponent(() => import('~/components/charts/WeeklyUsageChartUnlimited.vue'))
const MonthlyUsageChart = defineAsyncComponent(() => import('~/components/charts/MonthlyUsageChart.vue'))

const authToken = useCookie<string | null>('auth_token')
const authStore = useAuthStore()
const promoStore = usePromoStore() // Inisialisasi promo store
const pageTitle = 'Dashboard Pengguna'

// --- TAMBAHAN BARU ---
// State untuk menampilkan notifikasi promo di dashboard
const showPromoWarning = ref(false) // Default false, akan diatur oleh watcher
const promoWarningMessage = computed(() => {
  if (promoStore.activePromo) {
    if (promoStore.activePromo.event_type === 'BONUS_REGISTRATION') {
      const gbValue = promoStore.activePromo.bonus_value_mb ? (promoStore.activePromo.bonus_value_mb / 1024) : 0
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

function getApiUrl(endpoint: string): string {
  const clientBaseUrl = '/api'
  return `${clientBaseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`
}

// Opsi fetch umum
const commonFetchOptions = computed(() => ({
  headers: { Authorization: `Bearer ${authToken.value}` },
  server: false,
}))

// Fetch data kuota
const quotaApiUrl = computed(() => !authToken.value ? null : getApiUrl('/users/me/quota'))
const { data: quotaData, pending: quotaPending, error: quotaError, refresh: refreshQuotaRaw } = useFetch<UserQuotaResponse>(
  quotaApiUrl,
  { ...commonFetchOptions.value, key: 'userQuotaData', default: () => ({ success: false, total_quota_purchased_mb: 0, total_quota_used_mb: 0, remaining_mb: 0, hotspot_username: '...', last_sync_time: null, is_unlimited_user: false }), immediate: false, watch: false },
)

// Fetch data penggunaan mingguan
const weeklyUsageApiUrl = computed(() => !authToken.value ? null : getApiUrl('/users/me/weekly-usage'))
const { data: weeklyUsageData, pending: weeklyUsagePending, error: weeklyUsageError, refresh: refreshWeeklyUsageRaw } = useFetch<WeeklyUsageResponse>(
  weeklyUsageApiUrl,
  { ...commonFetchOptions.value, key: 'weeklyUsageData', default: () => ({ success: false, weekly_data: [] }), immediate: false, watch: false },
)

// Fetch data penggunaan bulanan
const monthlyUsageApiUrl = computed(() => !authToken.value ? null : getApiUrl('/users/me/monthly-usage'))
const { data: monthlyUsageData, pending: monthlyChartPending, error: monthlyChartError, refresh: refreshMonthlyUsageRaw } = useFetch<MonthlyUsageResponse>(
  monthlyUsageApiUrl,
  { ...commonFetchOptions.value, key: 'monthlyUsageData', default: () => ({ success: false, monthly_data: [] }), immediate: false, watch: false },
)

const fetchesInitiated = ref(false)
const minSkeletonTimePassed = ref(false)
const dashboardRenderKey = ref(0)

const isFetching = computed(() => {
  return quotaPending.value || weeklyUsagePending.value || monthlyChartPending.value
})

const shouldShowSkeleton = computed(() => {
  return fetchesInitiated.value && (isFetching.value || !minSkeletonTimePassed.value)
})

const hasError = computed(() => {
  return !!quotaError.value || !!weeklyUsageError.value || !!monthlyChartError.value
})

const showErrorAlert = ref(true)

type RefresherFunction = () => Promise<void> | void

function createRefresher(rawRefresher: RefresherFunction | globalThis.Ref<unknown>): RefresherFunction {
  return async () => {
    if (typeof rawRefresher !== 'function')
      return
    if (!authToken.value)
      return
    showErrorAlert.value = true
    return rawRefresher()
  }
}

const refreshQuota = createRefresher(refreshQuotaRaw)
const refreshWeeklyUsage = createRefresher(refreshWeeklyUsageRaw)
const refreshMonthlyUsage = createRefresher(refreshMonthlyUsageRaw)

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
    ])
  }
  catch (_e) {
    console.error('Dashboard: Error saat Promise.allSettled untuk pengambilan data:', _e)
  }
}

async function initialFetch() {
  if (authToken.value) {
    preFetchActions()
    await performFetches()
  }
  else {
    fetchesInitiated.value = true
    minSkeletonTimePassed.value = true
  }
}

onMounted(() => {
  initialFetch()
})

watch(isFetching, (newValue, oldValue) => {
  if (fetchesInitiated.value && oldValue === true && newValue === false) {
    nextTick(() => {
      dashboardRenderKey.value++
    })
  }
})

watch(authToken, (newToken, oldToken) => {
  if (newToken && newToken !== oldToken) {
    initialFetch()
  }
  else if (!newToken && oldToken) {
    quotaData.value = { success: false, total_quota_purchased_mb: 0, total_quota_used_mb: 0, remaining_mb: 0, hotspot_username: '...', last_sync_time: null, is_unlimited_user: false }
    weeklyUsageData.value = { success: false, weekly_data: [] }
    monthlyUsageData.value = { success: false, monthly_data: [] }
    fetchesInitiated.value = false
    showErrorAlert.value = false
    dashboardRenderKey.value++
  }
})

function formatDateTime(dateTimeString: string | null | undefined): string {
  if (!dateTimeString)
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
  if (!username)
    return 'Tidak Tersedia'
  return username.startsWith('+62') ? `0${username.substring(3)}` : username
}

async function refreshAllDataLogic() {
  if (!authToken.value)
    return

  preFetchActions()
  await performFetches()
}

const refreshAllData = useDebounceFn(refreshAllDataLogic, 500, { maxWait: 2000 })
useHead({ title: 'Dashboard User' })
</script>

<template>
  <VContainer fluid class="dashboard-page-container vuexy-dashboard-container pa-4 pa-md-6">
    <VRow>
      <VCol cols="12">
        <h1 class="text-h5 mb-4 vuexy-page-title">
          {{ pageTitle }}
        </h1>
      </VCol>
    </VRow>

    <div>
      <!-- Menampilkan notifikasi promo/peringatan di dashboard -->
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
                  {{ quotaError.message || 'Tidak ada pesan error spesifik.' }}
                </p>
                <pre v-if="quotaError.data?.message" class="error-server-message">{{ quotaError.data.message }}</pre>
              </div>
              <div v-if="weeklyUsageError" class="mt-2 error-detail-section">
                <p class="font-weight-medium text-body-2">
                  Detail Error Mingguan:
                </p>
                <p class="text-caption">
                  {{ weeklyUsageError.message || 'Tidak ada pesan error spesifik.' }}
                </p>
                <pre v-if="weeklyUsageError.data?.message" class="error-server-message">{{ weeklyUsageError.data.message }}</pre>
              </div>
              <div v-if="monthlyChartError" class="mt-2 error-detail-section">
                <p class="font-weight-medium text-body-2">
                  Detail Error Bulanan:
                </p>
                <p class="text-caption">
                  {{ monthlyChartError.message || 'Tidak ada pesan error spesifik.' }}
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
                        <span class="text-body-2 font-weight-medium text-medium-emphasis text-truncate" :title="quotaData?.last_sync_time ? formatDateTime(quotaData.last_sync_time) : 'N/A'">
                          {{ quotaData?.last_sync_time ? formatDateTime(quotaData.last_sync_time) : 'N/A' }}
                        </span>
                      </VCardText>
                    </VCard>
                  </VCol>
                </VRow>

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
              </VCol>

              <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
                <MonthlyUsageChart
                  :monthly-data="monthlyUsageData"
                  :parent-loading="isFetching"
                  :parent-error="monthlyChartError"
                  :dashboard-render-key="dashboardRenderKey"
                  class="dashboard-chart-card"
                />
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
.match-height > [class*='col-'] > .dashboard-chart-card > :deep(.v-card) {
    height: 100%;
    display: flex;
    flex-direction: column;
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
    padding: 1rem;
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

.vuexy-card .v-card-text {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
}
</style>
