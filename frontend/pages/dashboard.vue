// pages/dashboard.vue

<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core'
import { useFetch } from 'nuxt/app'
import {
  computed,
  nextTick,
  onMounted,
  ref,
  watch,
} from 'vue'

import type {
  MonthlyUsageResponse,
  User,
  WeeklyUsageResponse,
} from '~/types/user'

import { useDeviceNotification } from '~/composables/useDeviceNotification'
import { useAuthStore } from '~/store/auth'
import { usePromoStore } from '~/store/promo'
import { ApprovalStatus, UserRole } from '~/types/enums'
import { relativeLabel } from '~/utils/useRelativeTime'

/* -------------------- Store & variabel dasar -------------------- */
const authStore = useAuthStore()
const promoStore = usePromoStore()
const { startDeviceNotificationWatcher } = useDeviceNotification()
const pageTitle = 'Dashboard Pengguna'
const dashboardRenderKey = ref(0)

/* -------------------- Promo banner -------------------- */
const showPromoWarning = ref(false)
const promoWarningMessage = computed(() => {
  if (!promoStore.activePromo)
    return ''
  const promo = promoStore.activePromo
  if (promo.event_type === 'BONUS_REGISTRATION') {
    const gb = promo.bonus_value_mb! / 1024
    const gbLabel = Number.isInteger(gb) ? gb : gb.toFixed(2)
    return `Ada promo bonus registrasi! Dapatkan ${gbLabel} GB kuota gratis.`
  }
  if (promo.event_type === 'GENERAL_ANNOUNCEMENT') {
    return `Ada pengumuman baru: “${promo.name}”. Cek segera!`
  }
  return ''
})

watch(() => promoStore.activePromo, (newVal) => { showPromoWarning.value = !!(newVal && !promoStore.isPromoDialogVisible) }, { immediate: true })

/* -------------------- Helper fetch options -------------------- */
function baseFetchOpts(key: string) {
  return computed(() => ({
    key,
    server: false,
    headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : undefined,
  }))
}

/* -------------------- Fetch-fetch data ... -------------------- */
const { data: quotaData, pending: quotaPending, error: quotaError, refresh: refreshQuota } = useFetch<User>('/api/dashboard/quota', {
  ...baseFetchOpts('userQuotaData').value,
  default: (): User => ({
    id: '',
    phone_number: '',
    full_name: '…',
    role: UserRole.USER,
    approval_status: ApprovalStatus.PENDING_APPROVAL,
    is_active: false,
    is_blocked: false,
    blok: null,
    kamar: null,
    total_quota_purchased_mb: 0,
    total_quota_used_mb: 0,
    is_unlimited_user: false,
    quota_expiry_date: null,
    created_at: '',
    updated_at: '',
    approved_at: null,
    last_login_at: null,
    device_brand: null,
    device_model: null,
    client_ip: null,
    client_mac: null,
    last_login_mac: null,
    blocking_reason: null,
  }),
})

const { data: weeklyUsageData, pending: weeklyUsagePending, error: weeklyUsageError, refresh: refreshWeeklyUsage } = useFetch<WeeklyUsageResponse>('/api/dashboard/weekly-usage', {
  ...baseFetchOpts('weeklyUsageData').value,
  default: (): WeeklyUsageResponse => ({ success: false, data: [] }),
})

const { data: monthlyUsageData, pending: monthlyChartPending, error: monthlyChartError, refresh: refreshMonthlyUsage } = useFetch<MonthlyUsageResponse>('/api/dashboard/monthly-usage', {
  ...baseFetchOpts('monthlyUsageData').value,
  default: (): MonthlyUsageResponse => ({ success: false, data: [] }),
})

/* -------------------- Dan seterusnya ... -------------------- */
const lastSyncLabel = computed(() => {
  const iso = quotaData.value?.last_sync_time
  return iso ? relativeLabel(iso) : '—'
})

const fetchesInitiated = ref(false)
const minSkeletonTimePassed = ref(false)
const isFetching = computed(() => quotaPending.value || weeklyUsagePending.value || monthlyChartPending.value)
const shouldShowSkeleton = computed(() => fetchesInitiated.value && (isFetching.value || !minSkeletonTimePassed.value))
const hasError = computed(() => !!quotaError.value || !!weeklyUsageError.value || !!monthlyChartError.value)
const showErrorAlert = ref(true)

async function performAllFetches() {
  if (!authStore.token)
    return
  fetchesInitiated.value = true
  minSkeletonTimePassed.value = false
  showErrorAlert.value = true
  setTimeout(() => (minSkeletonTimePassed.value = true), 700)
  await Promise.allSettled([refreshQuota(), refreshWeeklyUsage(), refreshMonthlyUsage()])
}

const refreshAllData = useDebounceFn(performAllFetches, 500, { maxWait: 2000 })

onMounted(() => {
  // Lakukan fetch data untuk komponen-komponen di dashboard
  performAllFetches()

  // --- [PERBAIKAN UTAMA] ---
  // Logika sinkronisasi dan notifikasi perangkat dipindahkan ke sini.
  // Ini memastikan alur otorisasi perangkat HANYA dimulai di dashboard.
  if (authStore.isLoggedIn && !authStore.isAdmin) {
    console.log('[DASHBOARD] Memulai alur pengecekan perangkat...')

    // 1. Mulai watcher untuk menampilkan popup jika state 'isNewDeviceDetected' berubah.
    startDeviceNotificationWatcher()

    // 2. Lakukan pengecekan sinkronisasi perangkat saat dashboard pertama kali dimuat.
    // ✅ SEMPURNAKAN: Gunakan mode 'force' di dashboard untuk memastikan sinkronisasi
    // dilakukan bahkan jika ada throttling, karena ini adalah tempat yang tepat 
    // untuk menampilkan popup otorisasi perangkat jika diperlukan
    authStore.syncDevice({ allowAuthorizationFlow: true, force: true })
  }
})

watch(isFetching, (val, old) => {
  if (fetchesInitiated.value && old && !val) {
    nextTick(() => dashboardRenderKey.value++)
  }
})

watch(() => authStore.token, (newTok, oldTok) => {
  if (newTok && newTok !== oldTok)
    performAllFetches()
  if (!newTok && oldTok) {
    quotaData.value = {
      id: '',
      phone_number: '',
      full_name: '…',
      role: UserRole.USER,
      approval_status: ApprovalStatus.PENDING_APPROVAL,
      is_active: false,
      is_blocked: false,
      blok: null,
      kamar: null,
      total_quota_purchased_mb: 0,
      total_quota_used_mb: 0,
      is_unlimited_user: false,
      quota_expiry_date: null,
      created_at: '',
      updated_at: '',
      approved_at: null,
      last_login_at: null,
      device_brand: null,
      device_model: null,
      client_ip: null,
      client_mac: null,
      last_login_mac: null,
      blocking_reason: null,
    }
    weeklyUsageData.value = { success: false, data: [] }
    monthlyUsageData.value = { success: false, data: [] }
    fetchesInitiated.value = false
    showErrorAlert.value = false
    dashboardRenderKey.value++
  }
})

function formatDateTime(s: string | null | undefined) {
  if (!s)
    return 'N/A'
  const d = new Date(s)
  if (Number.isNaN(d.getTime()))
    return 'Tanggal Invalid'
  return new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Makassar', timeZoneName: 'shortOffset' }).format(d).replace('GMT+8', 'WITA')
}

function formatUsername(u?: string | null) {
  return !u ? 'Tidak Tersedia' : u.startsWith('+62') ? `0${u.slice(3)}` : u
}

useHead({ title: 'Dashboard User' })
</script>

<template>
  <VContainer
    fluid
    class="dashboard-page-container vuexy-dashboard-container pa-4 pa-md-6"
  >
    <VRow>
      <VCol cols="12">
        <h1 class="text-h5 mb-4 vuexy-page-title">
          {{ pageTitle }}
        </h1>
      </VCol>
    </VRow>

    <VAlert v-if="showPromoWarning" type="warning" variant="tonal" class="mb-6" closable @update:model-value="showPromoWarning = false">
      {{ promoWarningMessage }}
    </VAlert>

    <template v-if="shouldShowSkeleton">
      <VRow class="match-height">
        <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
          <VSkeletonLoader type="image" height="150px" class="vuexy-skeleton-card" />
          <VSkeletonLoader type="image" height="300px" class="vuexy-skeleton-card" />
        </VCol>
        <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
          <VSkeletonLoader type="image" height="460px" class="vuexy-skeleton-card" />
        </VCol>
      </VRow>
    </template>

    <template v-else>
      <div v-if="hasError && showErrorAlert" class="mb-6 dashboard-error-alert-container">
        <VAlert type="error" density="comfortable" variant="tonal" color="error" prominent border="start" closable class="vuexy-alert" @update:model-value="showErrorAlert = false">
          <template #title>
            <div class="d-flex align-center">
              <VIcon start icon="tabler-alert-triangle" size="24" />
              <h6 class="text-h6">
                Gagal Memuat Data Dashboard
              </h6>
            </div>
          </template>
          <p class="text-body-2">
            Beberapa komponen mungkin tidak tampil dengan benar. Silakan coba muat ulang.
          </p>
          <div v-if="quotaError" class="mt-2 error-detail-section">
            <p class="font-weight-medium text-body-2">
              Error Data Kuota:
            </p>
            <pre class="error-server-message">{{ quotaError.message }}</pre>
          </div>
          <div v-if="weeklyUsageError" class="mt-2 error-detail-section">
            <p class="font-weight-medium text-body-2">
              Error Data Mingguan:
            </p>
            <pre class="error-server-message">{{ weeklyUsageError.message }}</pre>
          </div>
          <div v-if="monthlyChartError" class="mt-2 error-detail-section">
            <p class="font-weight-medium text-body-2">
              Error Data Bulanan:
            </p>
            <pre class="error-server-message">{{ monthlyChartError.message }}</pre>
          </div>
          <div class="mt-4">
            <VBtn color="error" variant="outlined" prepend-icon="tabler-refresh" size="small" @click="refreshAllData">
              Coba Lagi Semua Data
            </VBtn>
          </div>
        </VAlert>
      </div>

      <div :key="dashboardRenderKey">
        <VRow class="match-height">
          <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
            <VCard class="vuexy-card">
              <VCardItem class="vuexy-card-header">
                <VCardTitle class="vuexy-card-title">
                  <VIcon icon="tabler-info-circle" class="me-2" />Informasi Akun
                </VCardTitle>
              </VCardItem>
              <VDivider />
              <VCardText class="d-flex align-center py-3 px-4">
                <VIcon icon="tabler-wifi" size="20" class="me-3" />
                <span class="text-body-2 flex-grow-1">Username</span>
                <span class="text-body-2 font-weight-medium text-truncate" :title="formatUsername(quotaData?.hotspot_username)">{{ formatUsername(quotaData?.hotspot_username) }}</span>
              </VCardText>
              <VCardText class="d-flex align-center py-3 px-4">
                <VIcon icon="tabler-clock-check" size="20" class="me-3" />
                <span class="text-body-2 flex-grow-1">Sinkronisasi</span>
                <span class="text-body-2 font-weight-medium text-medium-emphasis text-truncate" :title="formatDateTime(quotaData?.last_sync_time)">{{ lastSyncLabel }}</span>
              </VCardText>
            </VCard>
            <template v-if="quotaData?.is_unlimited_user">
              <WeeklyUsageChartUnlimited :weekly-usage-data="weeklyUsageData" :parent-loading="isFetching" :parent-error="weeklyUsageError" :dashboard-render-key="dashboardRenderKey" class="dashboard-chart-card" @refresh="refreshAllData" />
            </template>
            <template v-else>
              <WeeklyUsageChart :quota-data="quotaData" :weekly-usage-data="weeklyUsageData" :parent-loading="isFetching" :parent-error="quotaError || weeklyUsageError" :dashboard-render-key="dashboardRenderKey" class="dashboard-chart-card" @refresh="refreshAllData" />
            </template>
          </VCol>

          <VCol cols="12" md="6" class="d-flex flex-column chart-column ga-4">
            <MonthlyUsageChart :monthly-data="monthlyUsageData" :parent-loading="monthlyChartPending" :parent-error="monthlyChartError" :dashboard-render-key="dashboardRenderKey" class="dashboard-chart-card" @refresh="refreshMonthlyUsage" />
          </VCol>
        </VRow>

        <VRow class="mt-6">
          <VCol cols="12">
            <VExpansionPanels>
              <VExpansionPanel>
                <VExpansionPanelTitle><VIcon icon="tabler-bug" class="me-2" />Lihat Data Mentah Dashboard (Debug)</VExpansionPanelTitle>
                <VExpansionPanelText>
                  <VRow>
                    <VCol cols="12" md="4">
                      <VCard variant="outlined" class="debug-card">
                        <VCardTitle>/api/dashboard/quota</VCardTitle>
                        <VCardText><pre>{{ JSON.stringify(quotaData, null, 2) }}</pre></VCardText>
                      </VCard>
                    </VCol>
                    <VCol cols="12" md="4">
                      <VCard variant="outlined" class="debug-card">
                        <VCardTitle>/api/dashboard/weekly-usage</VCardTitle>
                        <VCardText><pre>{{ JSON.stringify(weeklyUsageData, null, 2) }}</pre></VCardText>
                      </VCard>
                    </VCol>
                    <VCol cols="12" md="4">
                      <VCard variant="outlined" class="debug-card">
                        <VCardTitle>/api/dashboard/monthly-usage</VCardTitle>
                        <VCardText><pre>{{ JSON.stringify(monthlyUsageData, null, 2) }}</pre></VCardText>
                      </VCard>
                    </VCol>
                  </VRow>
                </VExpansionPanelText>
              </VExpansionPanel>
            </VExpansionPanels>
          </VCol>
        </VRow>
      </div>
    </template>
  </VContainer>
</template>

<style scoped>
/* Style tidak berubah, dipertahankan seperti aslinya */
.vuexy-dashboard-container {
  /* Let layout handle max-width based on content-width setting */
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
.dashboard-chart-card > :deep(.v-card) {
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
  padding: 0.5rem 0.75rem;
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
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-top: 0.25rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-family: monospace;
}
.ga-4 {
  gap: 1.5rem;
}
.debug-card pre {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  padding: 1rem;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}
@media (max-width: 959.98px) {
  .chart-column {
    min-height: auto;
  }
  .ga-4 {
    gap: 1rem;
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
}
</style>
