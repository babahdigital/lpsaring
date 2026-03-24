<script setup lang="ts">
import { navigateTo, useFetch, useNuxtApp } from '#app'
import { hexToRgb } from '@layouts/utils'
import { computed, defineAsyncComponent, h, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/store/auth'
import { useDisplay } from 'vuetify'
import { useTheme } from 'vuetify'
import { buildReliabilitySummary } from '~/utils/adminMetrics'

const API_ENDPOINT = '/admin/dashboard/stats'

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    console.error(`Gagal memuat VueApexCharts`, err)
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
  }),
)

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

// --- Tipe Data (Interface) ---
interface TransaksiTerakhir {
  id: string
  amount: number
  created_at: string
  package: { name: string }
  user: {
    full_name: string
    username?: string
    phone_number?: string
  } | null
}

interface PaketTerlaris {
  name: string
  count: number
}

interface DashboardStats {
  pendapatanHariIni: number
  pendapatanBulanIni: number
  pendaftarBaru: number
  penggunaAktif: number
  menungguPersetujuan?: number
  akanKadaluwarsa: number
  permintaanTertunda: number // <-- DITAMBAHKAN
  pendapatanKemarin?: number
  transaksiHariIni?: number
  kuotaTerjualMb?: number
  kuotaTerjual7HariMb?: number
  kuotaTerjualMingguLaluMb?: number
  kuotaPerHari?: number[]
  pendapatanPerHari?: number[]
  transaksiTerakhir: TransaksiTerakhir[]
  paketTerlaris: PaketTerlaris[]
  pendapatanMingguIni?: number
  pendapatanMingguLalu?: number
  transaksiMingguIni?: number
  transaksiMingguLalu?: number
}

interface BackupListResponse {
  items?: Array<unknown>
}

interface AdminMetricsResponse {
  metrics?: Record<string, number | null | undefined>
  reliability_signals?: {
    payment_idempotency_degraded?: boolean
    hotspot_sync_lock_degraded?: boolean
    policy_parity_degraded?: boolean
  }
}

type AccessParityMismatchKey =
  | 'binding_type'
  | 'missing_ip_binding'
  | 'address_list'
  | 'address_list_multi_status'
  | 'no_authorized_device'
  | 'no_resolvable_ip'
  | 'dhcp_lease_missing'

interface AccessParityResponse {
  summary?: {
    users?: number
    mismatches?: number
    mismatches_total?: number
    non_parity_mismatches?: number
    no_authorized_device_count?: number
    auto_fixable_items?: number
    mismatch_types?: Partial<Record<AccessParityMismatchKey, number>>
  }
}

// --- State & Fetching ---
const { $api } = useNuxtApp()
const authStore = useAuthStore()

const defaultStats: DashboardStats = {
  pendapatanHariIni: 0,
  pendapatanBulanIni: 0,
  pendaftarBaru: 0,
  penggunaAktif: 0,
  menungguPersetujuan: 0,
  akanKadaluwarsa: 0,
  permintaanTertunda: 0,
  pendapatanKemarin: 0,
  transaksiHariIni: 0,
  kuotaTerjualMb: 0,
  kuotaTerjual7HariMb: 0,
  kuotaTerjualMingguLaluMb: 0,
  transaksiTerakhir: [],
  paketTerlaris: [],
  kuotaPerHari: Array.from({ length: 7 }, () => 0),
  pendapatanPerHari: Array.from({ length: 30 }, () => 0),
  pendapatanMingguIni: 0,
  pendapatanMingguLalu: 0,
  transaksiMingguIni: 0,
  transaksiMingguLalu: 0,
}

const { data: stats, pending, error, refresh } = useFetch<DashboardStats>(API_ENDPOINT, {
  lazy: true,
  server: false,
  $fetch: $api,
})

const {
  data: adminMetrics,
  pending: metricsPending,
  refresh: refreshMetrics,
} = useFetch<AdminMetricsResponse>('/admin/metrics', {
  lazy: true,
  server: false,
  $fetch: $api,
})

const {
  data: accessParity,
  pending: parityPending,
  refresh: refreshParity,
} = useFetch<AccessParityResponse>('/admin/metrics/access-parity', {
  lazy: true,
  server: false,
  $fetch: $api,
})

const hasLoadedOnce = ref(false)
watch(pending, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })

const showInitialSkeleton = computed(() => pending.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => pending.value === true && hasLoadedOnce.value === true)
const currentMonthLabel = ref('-')

if (stats.value == null)
  stats.value = defaultStats

const vuetifyTheme = useTheme()
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)

// --- Data untuk Kartu Statistik Atas (Diperbarui) ---
const statistics = ref([
  { icon: 'tabler-mail-fast', color: 'info', title: 'Permintaan Tertunda', value: 0, to: '/admin/requests' },
  { icon: 'tabler-calendar-exclamation', color: 'warning', title: 'Akan Kadaluwarsa', value: 0, to: '/admin/users' },
  { icon: 'tabler-user-search', color: 'secondary', title: 'Menunggu Persetujuan', value: 0, to: '/admin/users' },
  { icon: 'tabler-database-export', color: 'primary', title: 'File Backup', value: 0 },
])
const displayedStatistics = computed(() => {
  if (authStore.isSuperAdmin === true)
    return statistics.value

  return statistics.value.filter(item => item.title !== 'File Backup')
})

const backupFileCount = ref(0)

async function fetchBackupFileCount() {
  try {
    const response = await $api<BackupListResponse>('/admin/backups', { method: 'GET' })
    backupFileCount.value = Array.isArray(response?.items) ? response.items.length : 0
  }
  catch {
    backupFileCount.value = 0
  }
}

watch(stats, (newStats) => {
  if (!newStats) {
    stats.value = defaultStats
    return
  }
  statistics.value[0].value = newStats.permintaanTertunda ?? 0
  statistics.value[1].value = newStats.akanKadaluwarsa ?? 0
  statistics.value[2].value = newStats.menungguPersetujuan ?? 0
  statistics.value[3].value = backupFileCount.value
})

watch(backupFileCount, (newCount) => {
  statistics.value[3].value = newCount
})

onMounted(async () => {
  currentMonthLabel.value = new Date().toLocaleString('id-ID', { month: 'long' })
  if (authStore.isSuperAdmin === true)
    await fetchBackupFileCount()
})

const reliabilitySummary = computed(() => buildReliabilitySummary(adminMetrics.value))

async function handleRefreshDashboard() {
  await Promise.all([
    refresh(),
    refreshMetrics(),
    refreshParity(),
    fetchBackupFileCount(),
  ])
}

const accessParitySummary = computed(() => ({
  users: accessParity.value?.summary?.users ?? 0,
  mismatches: accessParity.value?.summary?.mismatches ?? 0,
  mismatchesTotal: accessParity.value?.summary?.mismatches_total ?? 0,
  nonParityMismatches: accessParity.value?.summary?.non_parity_mismatches ?? 0,
  noAuthorizedDeviceCount: accessParity.value?.summary?.no_authorized_device_count ?? 0,
  autoFixableItems: accessParity.value?.summary?.auto_fixable_items ?? 0,
  mismatchTypes: accessParity.value?.summary?.mismatch_types ?? {},
}))
const accessParitySyncRate = computed(() => {
  const users = accessParitySummary.value.users
  if (users <= 0)
    return 100

  const syncedUsers = Math.max(0, users - accessParitySummary.value.mismatches)
  return Math.round((syncedUsers / users) * 100)
})
const operationalSummaryCards = computed(() => [
  {
    key: 'duplicate-webhook',
    title: 'Duplikat Pembayaran',
    stats: `${reliabilitySummary.value.duplicateWebhookCount}`,
    color: reliabilitySummary.value.duplicateWebhookCount > 0 ? 'warning' : 'success',
    icon: 'tabler-repeat',
  },
  {
    key: 'payment-idempotency',
    title: 'Idempotency Guard',
    stats: reliabilitySummary.value.paymentIdempotencyDegraded ? `${reliabilitySummary.value.paymentIdempotencyRedisUnavailableCount} Gangguan` : 'Stabil',
    color: reliabilitySummary.value.paymentIdempotencyDegraded ? 'error' : 'success',
    icon: 'tabler-shield-check',
  },
  {
    key: 'hotspot-sync-lock',
    title: 'Hotspot Sync Lock',
    stats: reliabilitySummary.value.hotspotSyncLockDegraded ? `${reliabilitySummary.value.hotspotSyncLockDegradedCount} Lock Miss` : 'Aktif',
    color: reliabilitySummary.value.hotspotSyncLockDegraded ? 'error' : 'success',
    icon: 'tabler-plug-connected',
  },
  {
    key: 'access-parity',
    title: 'Parity Akses',
    stats: accessParitySummary.value.mismatches > 0 ? `${accessParitySummary.value.mismatches} Mismatch` : `${accessParitySyncRate.value}% Sinkron`,
    color: accessParitySummary.value.mismatches > 0 ? 'error' : 'success',
    icon: 'tabler-router',
  },
])

const perbandinganPendapatanMingguan = computed(() => {
  const mingguIni = stats.value?.pendapatanMingguIni ?? 0
  const mingguLalu = stats.value?.pendapatanMingguLalu ?? 0
  if (mingguLalu === 0)
    return { persentase: mingguIni > 0 ? 100 : 0 }

  const selisih = mingguIni - mingguLalu
  const persentase = (selisih / mingguLalu) * 100

  return { persentase: Number.isFinite(persentase) ? persentase : 0 }
})

const perbandinganKuota = computed(() => {
  const totalMingguIni = stats.value?.kuotaTerjual7HariMb ?? stats.value?.kuotaTerjualMb ?? 0
  const totalMingguLalu = stats.value?.kuotaTerjualMingguLaluMb ?? 0
  if (totalMingguLalu === 0)
    return { persentase: totalMingguIni > 0 ? 100 : 0 }

  const selisih = totalMingguIni - totalMingguLalu
  const persentase = (selisih / totalMingguLalu) * 100

  return { persentase: Number.isFinite(persentase) ? persentase : 0 }
})

const weeklyRevenueSplit = computed(() => {
  const mingguIni = stats.value?.pendapatanMingguIni ?? 0
  const mingguLalu = stats.value?.pendapatanMingguLalu ?? 0
  const total = mingguIni + mingguLalu

  if (total <= 0)
    return 0

  return Math.round((mingguIni / total) * 100)
})

const monthlyRevenueHighlights = computed(() => [
  {
    key: 'new-users',
    label: 'Pendaftar Baru',
    value: `${stats.value?.pendaftarBaru ?? 0}`,
    icon: 'tabler-user-plus',
    color: 'success',
  },
  {
    key: 'active-users',
    label: 'User Aktif',
    value: `${stats.value?.penggunaAktif ?? 0}`,
    icon: 'tabler-users-group',
    color: 'primary',
  },
])

const topSellingPackage = computed(() => {
  const topPackage = stats.value?.paketTerlaris?.[0]

  return {
    name: topPackage?.name ?? 'Belum ada paket dominan',
    count: topPackage?.count ?? 0,
  }
})

const recentActivitySummary = computed(() => {
  const totalActivities = stats.value?.transaksiTerakhir?.length ?? 0

  if (totalActivities <= 0)
    return 'Belum ada transaksi terbaru'

  return `${Math.min(totalActivities, 3)} aktivitas terbaru`
})

const weeklyDateCategories = computed(() => {
  const dayShortMap = ['M', 'S', 'S', 'R', 'K', 'J', 'S']
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - 6)

  const entries = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)

    return {
      short: dayShortMap[date.getDay()],
      full: new Intl.DateTimeFormat('id-ID', {
        weekday: 'long',
        day: '2-digit',
        month: 'short',
      }).format(date),
    }
  })

  return entries
})

const monthlyDateCategories = computed(() => {
  const pointCount = stats.value?.pendapatanPerHari?.length ?? 30
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - (pointCount - 1))

  return Array.from({ length: pointCount }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)

    return {
      short: new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short' }).format(date),
      full: new Intl.DateTimeFormat('id-ID', {
        weekday: 'long',
        day: '2-digit',
        month: 'short',
      }).format(date),
    }
  })
})

// --- Konfigurasi Grafik ---
const kuotaChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value.colors
  const variableTheme = vuetifyTheme.current.value.variables
  const labelColor = `rgba(${hexToRgb(currentTheme['on-surface'])},${variableTheme['disabled-opacity']})`

  return {
    chart: { type: 'bar', parentHeightOffset: 0, toolbar: { show: false } },
    plotOptions: {
      bar: { barHeight: '60%', columnWidth: '38%', startingShape: 'rounded', endingShape: 'rounded', borderRadius: 4, distributed: true },
    },
    grid: { show: false, padding: { top: -30, bottom: 0, left: -10, right: -10 } },
    colors: [
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
      `rgba(${hexToRgb(currentTheme.primary)}, 1)`,
      `rgba(${hexToRgb(currentTheme.primary)},${variableTheme['dragged-opacity']})`,
    ],
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: weeklyDateCategories.value.map(item => item.short),
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { style: { colors: labelColor, fontSize: '13px', fontFamily: 'Public Sans' } },
    },
    yaxis: { labels: { show: false } },
    tooltip: {
      enabled: true,
      theme: 'dark',
      x: {
        formatter: (_: string, opts: any) => {
          const index = opts?.dataPointIndex ?? 0
          return weeklyDateCategories.value[index]?.full ?? ''
        },
      },
      y: {
        formatter: (val: number) => `${formatBytes(val)}`,
      },
    },
  }
})

const kuotaChartSeries = computed(() => [{
  name: 'Kuota',
  data: stats.value?.kuotaPerHari?.slice(-7) ?? [40, 65, 50, 45, 90, 55, 70],
}])

const pendapatanBulanIniChartOptions = computed(() => ({
  chart: { type: 'area', toolbar: { show: false }, sparkline: { enabled: true } },
  markers: { colors: 'transparent', strokeColors: 'transparent' },
  grid: { show: false },
  colors: [vuetifyTheme.current.value.colors.primary],
  fill: { type: 'gradient', gradient: { shadeIntensity: 0.8, opacityFrom: 0.6, opacityTo: 0.1 } },
  dataLabels: { enabled: false },
  stroke: { width: 2, curve: 'smooth' },
  xaxis: {
    show: false,
    categories: monthlyDateCategories.value.map(item => item.short),
    lines: { show: false },
    labels: { show: false },
    axisBorder: { show: false },
  },
  yaxis: { show: false },
  tooltip: {
    enabled: true,
    theme: 'dark',
    x: {
      formatter: (_: string, opts: any) => {
        const index = opts?.dataPointIndex ?? 0
        const dateText = monthlyDateCategories.value[index]?.full ?? ''
        const totalKuotaText = formatBytes(stats.value?.kuotaTerjualMb)
        return `${dateText} • Total Kuota: ${totalKuotaText}`
      },
    },
    y: {
      formatter: (val: number) => formatCurrency(val).replace(/^Rp\s/, 'Rp. '),
    },
  },
}))

const pendapatanBulanIniChartSeries = computed(() => [{
  name: 'Pendapatan',
  data: stats.value?.pendapatanPerHari ?? Array.from({ length: 30 }).fill(0),
}])

const paketTerlarisChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value
  const onSurfaceColor = currentTheme.colors['on-surface'] ?? currentTheme.colors.onSurface
  return {
    chart: { type: 'donut' },
    labels: stats.value?.paketTerlaris.map((p: PaketTerlaris) => p.name) ?? [],
    colors: [
      currentTheme.colors.primary,
      currentTheme.colors.success,
      currentTheme.colors.info,
      currentTheme.colors.warning,
      currentTheme.colors.secondary,
    ],
    stroke: { width: 0, colors: [currentTheme.colors.surface] },
    dataLabels: {
      enabled: true,
      formatter: (val: number, opts: any) => `${opts.w.globals.series[opts.seriesIndex]}x`,
      style: {
        fontSize: '12px',
        colors: [currentTheme.colors.surface],
        fontWeight: 'bold',
      },
      dropShadow: {
        enabled: false,
      },
    },
    legend: {
      position: 'bottom',
      offsetY: 20,
      markers: { offsetX: -3 },
      itemMargin: { horizontal: 10, vertical: 8 },
      labels: { colors: onSurfaceColor, useSeriesColors: false },
    },
    plotOptions: {
      pie: {
        donut: {
          size: '70%',
          labels: {
            show: true,
            value: {
              fontSize: '1.625rem',
              fontFamily: 'Public Sans',
              color: onSurfaceColor,
              fontWeight: 600,
              offsetY: -15,
              formatter: (val: string) => `${val}x`,
            },
            name: {
              fontSize: '0.9rem',
              fontFamily: 'Public Sans',
              color: onSurfaceColor,
              offsetY: 20,
            },
            total: {
              show: true,
              showAlways: true,
              label: 'Total',
              color: onSurfaceColor,
              formatter: (w: any) => `${w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0)}x`,
            },
          },
        },
      },
    },
    tooltip: {
      enabled: true,
      theme: 'dark',
      y: {
        formatter: (val: number) => `${val} penjualan`,
      },
    },
  }
})

const paketTerlarisChartSeries = computed(() => stats.value?.paketTerlaris.map((p: PaketTerlaris) => p.count) ?? [])

// --- Fungsi Helper ---
function handleCardClick(path?: string) {
  if (path) {
    navigateTo(path)
  }
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined)
    return 'Rp 0'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

function formatBytes(bytesInMb: number | null | undefined, decimals = 1) {
  if (bytesInMb === null || bytesInMb === undefined || bytesInMb === 0)
    return '0 MB'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['MB', 'GB', 'TB']
  let i = 0
  let size = bytesInMb
  while (size >= k && i < sizes.length - 1) {
    size /= k
    i++
  }
  return `${Number.parseFloat(size.toFixed(dm))} ${sizes[i]}`
}

function formatRelativeTime(dateString?: string): string {
  if (!dateString)
    return 'Baru saja'
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime()))
    return ''
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  let interval = seconds / 31536000
  if (interval > 1)
    return `${Math.floor(interval)} tahun lalu`
  interval = seconds / 2592000
  if (interval > 1)
    return `${Math.floor(interval)} bulan lalu`
  interval = seconds / 86400
  if (interval > 1)
    return `${Math.floor(interval)} hari lalu`
  interval = seconds / 3600
  if (interval > 1)
    return `${Math.floor(interval)} jam lalu`
  interval = seconds / 60
  if (interval > 1)
    return `${Math.floor(interval)} menit lalu`
  return 'Baru saja'
}

function formatPhoneNumberForDisplay(phoneNumber?: string | null) {
  if (!phoneNumber)
    return 'No. Telp tidak ada'
  if (phoneNumber.startsWith('+62')) {
    const localNumber = `0${phoneNumber.substring(3)}`
    if (localNumber.length > 8) {
      return `${localNumber.substring(0, 4)}-xxxx-${localNumber.substring(localNumber.length - 4)}`
    }
    return localNumber
  }
  return phoneNumber
}

function getUserInitials(name?: string) {
  if (!name || name.trim() === '')
    return 'N/A'
  const words = name.split(' ').filter(Boolean)
  if (words.length >= 2)
    return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1 && words[0].length > 1)
    return (words[0][0] + words[0][1]).toUpperCase()
  return name.substring(0, 1).toUpperCase()
}

useHead({ title: 'Dashboard Admin' })
</script>

<template>
  <div>
    <VProgressLinear
      v-if="showSilentRefreshing"
      indeterminate
      color="primary"
      height="2"
      class="mb-4"
    />

    <VRow class="mb-6">
      <VCol
        v-for="(data, index) in displayedStatistics"
        :key="index"
        cols="12"
        md="3"
        sm="6"
      >
        <div
          class="dashboard-clickable-stat-card"
          :class="{ 'dashboard-clickable-stat-card--disabled': !data.to }"
          :role="data.to ? 'button' : undefined"
          :tabindex="data.to ? 0 : undefined"
          @click="handleCardClick(data.to)"
          @keydown.enter.prevent="handleCardClick(data.to)"
          @keydown.space.prevent="handleCardClick(data.to)"
        >
          <CardStatisticsHorizontal
            :title="data.title"
            :icon="data.icon"
            :color="data.color"
            :stats="String(data.value)"
          />
        </div>
      </VCol>
    </VRow>

    <VRow class="mb-4">
      <VCol
        v-for="item in operationalSummaryCards"
        :key="item.key"
        cols="12"
        md="3"
        sm="6"
      >
        <div
          class="dashboard-clickable-stat-card"
          :class="{ 'dashboard-clickable-stat-card--disabled': authStore.isSuperAdmin !== true }"
          :role="authStore.isSuperAdmin === true ? 'button' : undefined"
          :tabindex="authStore.isSuperAdmin === true ? 0 : undefined"
          @click="authStore.isSuperAdmin === true ? navigateTo('/admin/operations') : undefined"
          @keydown.enter.prevent="authStore.isSuperAdmin === true ? navigateTo('/admin/operations') : undefined"
          @keydown.space.prevent="authStore.isSuperAdmin === true ? navigateTo('/admin/operations') : undefined"
        >
          <CardStatisticsHorizontal
            :title="item.title"
            :icon="item.icon"
            :color="item.color"
            :stats="item.stats"
          />
        </div>
      </VCol>
    </VRow>

    <VRow
      class="mb-6"
      match-height
    >
      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100 dashboard-analytics-card">
          <VCardItem>
            <template #prepend>
              <VAvatar color="success" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-chart-line" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Pendapatan Mingguan</VCardTitle>
            <VCardSubtitle>7 hari vs minggu lalu</VCardSubtitle>
            <template #append>
              <VChip
                size="small"
                label
                :color="perbandinganPendapatanMingguan.persentase >= 0 ? 'success' : 'error'"
              >
                <span v-if="stats?.pendapatanMingguLalu === 0 && (stats?.pendapatanMingguIni ?? 0) > 0">BARU</span>
                <span v-else>{{ perbandinganPendapatanMingguan.persentase >= 0 ? '+' : '' }}{{ perbandinganPendapatanMingguan.persentase.toFixed(1) }}%</span>
              </VChip>
            </template>
          </VCardItem>
          <VCardText class="pt-2 dashboard-analytics-card__body dashboard-analytics-card__body--spread">
            <div class="dashboard-analytics-card__headline">
              <div class="dashboard-analytics-card__value">
                {{ formatCurrency(stats?.pendapatanMingguIni) }}
              </div>
              <div class="dashboard-analytics-card__caption">
                Total minggu berjalan.
              </div>
            </div>

            <div class="dashboard-analytics-card__salesOverview mt-5">
              <VRow no-gutters>
                <VCol cols="5">
                  <div class="dashboard-analytics-card__salesMetric py-2">
                    <div class="d-flex align-center mb-3">
                      <VAvatar color="info" variant="tonal" :size="24" rounded class="me-2">
                        <VIcon size="16" icon="tabler-calendar-check" />
                      </VAvatar>
                      <span class="dashboard-analytics-card__salesLabel dashboard-analytics-card__salesLabel--plain">Minggu Ini</span>
                    </div>
                    <div class="dashboard-analytics-card__comparisonValue mt-0">
                      {{ formatCurrency(stats?.pendapatanMingguIni) }}
                    </div>
                    <div class="dashboard-analytics-card__comparisonMeta">
                      {{ stats?.transaksiMingguIni ?? 0 }} transaksi
                    </div>
                  </div>
                </VCol>

                <VCol cols="2">
                  <div class="dashboard-analytics-card__salesDivider">
                    <VDivider vertical class="mx-auto" />
                    <VAvatar size="28" color="rgba(var(--v-theme-on-surface), var(--v-hover-opacity))" class="my-2">
                      <div class="text-overline text-disabled">
                        VS
                      </div>
                    </VAvatar>
                    <VDivider vertical class="mx-auto" />
                  </div>
                </VCol>

                <VCol cols="5">
                  <div class="dashboard-analytics-card__salesMetric dashboard-analytics-card__salesMetric--end py-2">
                    <div class="d-flex align-center justify-end mb-3">
                      <span class="dashboard-analytics-card__salesLabel dashboard-analytics-card__salesLabel--plain me-2">Minggu Lalu</span>
                      <VAvatar color="secondary" variant="tonal" :size="24" rounded>
                        <VIcon size="16" icon="tabler-calendar-stats" />
                      </VAvatar>
                    </div>
                    <div class="dashboard-analytics-card__comparisonValue mt-0">
                      {{ formatCurrency(stats?.pendapatanMingguLalu) }}
                    </div>
                    <div class="dashboard-analytics-card__comparisonMeta">
                      {{ stats?.transaksiMingguLalu ?? 0 }} transaksi
                    </div>
                  </div>
                </VCol>
              </VRow>
            </div>

            <div class="dashboard-analytics-card__salesProgress mt-5">
              <div class="d-flex align-center justify-space-between mb-2 text-caption text-medium-emphasis">
                <span>Kontribusi minggu ini</span>
                <span>{{ weeklyRevenueSplit }}%</span>
              </div>
              <VProgressLinear
                :model-value="weeklyRevenueSplit"
                color="info"
                height="8"
                bg-color="secondary"
                :rounded-bar="false"
                rounded
              />
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100 dashboard-analytics-card">
          <VCardItem class="pb-sm-5">
            <template #prepend>
              <VAvatar color="warning" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-chart-histogram" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Kuota Terjual</VCardTitle>
            <VCardSubtitle>Distribusi 7 hari terakhir</VCardSubtitle>
            <template #append>
              <VChip
                label
                size="small"
                :color="perbandinganKuota.persentase >= 0 ? 'success' : 'error'"
              >
                {{ perbandinganKuota.persentase >= 0 ? '+' : '' }}{{ perbandinganKuota.persentase.toFixed(1) }}%
              </VChip>
            </template>
          </VCardItem>
          <VCardText class="pt-sm-2">
            <div class="dashboard-analytics-card__headline dashboard-analytics-card__headline--compact">
              <div class="dashboard-analytics-card__value dashboard-analytics-card__value--xl">
                {{ formatBytes(stats?.kuotaTerjualMb) }}
              </div>
              <div class="dashboard-analytics-card__caption">
                Distribusi kuota 7 hari terakhir.
              </div>
            </div>

            <div class="dashboard-analytics-card__reportChart mt-6">
              <ClientOnly>
                <VueApexCharts
                  :options="kuotaChartOptions"
                  :series="kuotaChartSeries"
                  :height="178"
                />
                <template #fallback>
                  <div
                    class="d-flex align-center justify-center"
                    style="height: 178px;"
                  >
                    <VProgressCircular
                      indeterminate
                      color="primary"
                    />
                  </div>
                </template>
              </ClientOnly>
            </div>

            <div class="dashboard-analytics-card__reportFooter mt-5">
              <div class="dashboard-analytics-card__reportStat">
                <span>Minggu ini</span>
                <strong>{{ formatBytes(stats?.kuotaTerjual7HariMb ?? stats?.kuotaTerjualMb) }}</strong>
              </div>
              <div class="dashboard-analytics-card__reportStat">
                <span>Minggu lalu</span>
                <strong>{{ formatBytes(stats?.kuotaTerjualMingguLaluMb) }}</strong>
              </div>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100 dashboard-analytics-card dashboard-analytics-card--monthly">
          <VCardItem>
            <template #prepend>
              <VAvatar color="primary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-cash-banknote" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Pendapatan Bulan Ini</VCardTitle>
            <VCardSubtitle>Penjualan bulan {{ currentMonthLabel }}</VCardSubtitle>
            <template #append>
              <VChip size="small" color="primary" label variant="tonal">
                30 Hari
              </VChip>
            </template>
          </VCardItem>
          <VCardText class="pt-2 pb-0">
            <div class="dashboard-analytics-card__headline">
              <div class="dashboard-analytics-card__value">
                {{ formatCurrency(stats?.pendapatanBulanIni) }}
              </div>
              <div class="dashboard-analytics-card__caption">
                Baseline performa bulan berjalan.
              </div>
            </div>

            <div class="dashboard-analytics-card__miniGrid mt-4">
              <div v-for="item in monthlyRevenueHighlights" :key="item.key" class="dashboard-analytics-card__miniItem">
                <div class="d-flex align-center gap-2">
                  <VAvatar :color="item.color" variant="tonal" size="28" rounded>
                    <VIcon :icon="item.icon" size="16" />
                  </VAvatar>
                  <span class="dashboard-analytics-card__miniLabel">{{ item.label }}</span>
                </div>
                <div class="dashboard-analytics-card__miniValue">{{ item.value }}</div>
              </div>
            </div>

            <div class="dashboard-analytics-card__chartBlock mt-5">
              <ClientOnly>
                <VueApexCharts
                  :options="pendapatanBulanIniChartOptions"
                  :series="pendapatanBulanIniChartSeries"
                  :height="136"
                />
                <template #fallback>
                  <div
                    class="d-flex align-center justify-center"
                    style="height: 136px;"
                  >
                    <VProgressCircular
                      indeterminate
                      color="primary"
                    />
                  </div>
                </template>
              </ClientOnly>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VRow class="mb-4">
      <VCol
        cols="12"
        md="5"
      >
        <VCard class="h-100 dashboard-insight-card dashboard-top-package-card">
          <VCardItem>
            <template #prepend>
              <VAvatar color="secondary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-chart-donut" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Paket Terlaris</VCardTitle>
            <VCardSubtitle>Berdasarkan transaksi bulan ini</VCardSubtitle>
            <template #append>
              <VChip size="small" color="secondary" label variant="tonal">
                {{ topSellingPackage.count > 0 ? `${topSellingPackage.count} transaksi` : 'Menunggu data' }}
              </VChip>
            </template>
          </VCardItem>
          <VCardText class="pt-5 pb-6 dashboard-top-package-card__body">
            <ClientOnly>
              <VueApexCharts
                v-if="!showInitialSkeleton && paketTerlarisChartSeries.length > 0 && paketTerlarisChartSeries.some((s: number) => s > 0)"
                class="dashboard-top-package-card__chart"
                type="donut"
                height="350"
                :options="paketTerlarisChartOptions"
                :series="paketTerlarisChartSeries"
              />
              <div
                v-else-if="!showInitialSkeleton"
                class="d-flex flex-column align-center justify-center text-center dashboard-top-package-card__empty"
                style="height: 350px;"
              >
                <VIcon
                  icon="tabler-chart-pie-off"
                  size="50"
                  class="text-disabled mb-2"
                />
                <p class="text-disabled">
                  Belum ada data penjualan paket bulan ini.
                </p>
              </div>
              <div
                v-else
                class="d-flex align-center justify-center dashboard-top-package-card__empty"
                style="height: 350px;"
              >
                <VProgressCircular
                  indeterminate
                  color="primary"
                  size="64"
                />
              </div>
              <template #fallback>
                <div
                  class="d-flex align-center justify-center"
                  style="height: 350px;"
                >
                  Memuat komponen grafik...
                </div>
              </template>
            </ClientOnly>
          </VCardText>
        </VCard>
      </VCol>

      <VCol
        cols="12"
        md="7"
      >
        <VCard class="h-100 dashboard-insight-card">
          <VCardItem>
            <template #prepend>
              <VAvatar color="info" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-activity-heartbeat" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Aktivitas Terakhir</VCardTitle>
            <VCardSubtitle>{{ recentActivitySummary }}</VCardSubtitle>
            <template #append>
              <div class="d-flex align-center gap-2 flex-wrap justify-end">
                <VChip size="small" color="info" label variant="tonal">
                  Live feed
                </VChip>
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  color="default"
                  @click="handleRefreshDashboard"
                >
                  <VIcon
                    size="24"
                    icon="tabler-refresh"
                  />
                </VBtn>
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <VTimeline
              v-if="stats && stats.transaksiTerakhir.length > 0"
              side="end"
              align="start"
              line-inset="8"
              truncate-line="start"
              density="compact"
            >
              <VTimelineItem
                v-for="transaksi in stats.transaksiTerakhir.slice(0, 3)"
                :key="transaksi.id"
                dot-color="success"
                size="x-small"
              >
                <div class="d-flex justify-space-between align-center flex-wrap mb-2">
                  <div class="app-timeline-title">
                    Pembelian {{ transaksi.package.name }}
                  </div>
                  <span class="app-timeline-meta">{{ formatRelativeTime(transaksi.created_at) }}</span>
                </div>
                <div class="app-timeline-text mt-1 mb-3">
                  Transaksi sebesar {{ formatCurrency(transaksi.amount) }} telah berhasil.
                </div>
                <div class="d-flex justify-space-between align-center flex-wrap">
                  <div class="d-flex align-center mt-2">
                    <VAvatar
                      size="32"
                      class="me-2"
                      color="primary"
                      variant="tonal"
                    >
                      <span class="text-sm font-weight-medium">{{ getUserInitials(transaksi.user?.full_name) }}</span>
                    </VAvatar>
                    <div class="d-flex flex-column">
                      <p class="text-sm font-weight-medium text-medium-emphasis mb-0">
                        {{ transaksi.user?.full_name ?? 'Pengguna Dihapus' }}
                      </p>
                      <span class="text-sm">{{ formatPhoneNumberForDisplay(transaksi.user?.phone_number) }}</span>
                    </div>
                  </div>
                </div>
              </VTimelineItem>
            </VTimeline>
            <div
              v-else-if="!showInitialSkeleton"
              class="d-flex flex-column align-center justify-center text-center"
              style="min-height: 300px;"
            >
              <VIcon
                icon="tabler-file-off"
                size="50"
                class="text-disabled mb-2"
              />
              <p class="text-disabled">
                Belum ada aktivitas transaksi.
              </p>
            </div>
            <div
              v-else
              class="d-flex align-center justify-center"
              style="min-height: 300px;"
            >
              <VProgressCircular
                indeterminate
                color="primary"
                size="64"
              />
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

  </div>
</template>

<style lang="scss">
@use "@core/scss/template/libs/apex-chart.scss";
@use "@core/scss/base/mixins" as mixins;

.dashboard-clickable-stat-card {
  cursor: pointer;
  border-radius: 6px;
  transition: transform 0.12s ease-out;

  &:hover {
    transform: translateY(-2px);
    @include mixins.elevation(4);
  }
}

.dashboard-clickable-stat-card--disabled {
  cursor: default;

  &:hover {
    transform: none;
    box-shadow: none;
  }
}

.dashboard-analytics-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.04);
}

.dashboard-insight-card {
  height: 100%;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.04);
}

.dashboard-top-package-card__body {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 100%;
}

.dashboard-top-package-card__chart {
  display: block;
  padding-bottom: 27px;
}

.dashboard-top-package-card__empty {
  padding-bottom: 27px;
}

.dashboard-top-package-card :deep(.apexcharts-legend) {
  margin-top: 20px !important;
}

.dashboard-analytics-card__headline {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dashboard-analytics-card__headline--compact {
  gap: 8px;
}

.dashboard-analytics-card__value {
  font-size: clamp(1.8rem, 2vw, 2.2rem);
  font-weight: 700;
  line-height: 1.08;
  color: rgba(var(--v-theme-on-surface), 0.94);
}

.dashboard-analytics-card__value--xl {
  font-size: clamp(2rem, 2.3vw, 2.5rem);
}

.dashboard-analytics-card__caption {
  font-size: 0.84rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.dashboard-analytics-card__body {
  display: flex;
  flex-direction: column;
}

.dashboard-analytics-card__body--spread {
  height: 100%;
  justify-content: space-between;
}

.dashboard-analytics-card__salesOverview {
  min-height: 168px;
}

.dashboard-analytics-card__salesMetric {
  min-width: 0;
}

.dashboard-analytics-card__salesMetric--end {
  text-align: right;
}

.dashboard-analytics-card__salesLabel {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.dashboard-analytics-card__salesLabel--plain {
  text-transform: none;
  letter-spacing: 0;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.dashboard-analytics-card__salesDivider {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.dashboard-analytics-card__salesProgress {
  padding-top: 2px;
}

.dashboard-analytics-card__comparisonValue {
  margin-top: 14px;
  font-size: 1.02rem;
  font-weight: 700;
}

.dashboard-analytics-card__comparisonMeta {
  margin-top: 6px;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.dashboard-analytics-card__reportChart {
  min-height: 178px;
}

.dashboard-analytics-card__reportFooter {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding-top: 18px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.dashboard-analytics-card__reportStat {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.84rem;
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.dashboard-analytics-card__reportStat strong {
  font-size: 0.88rem;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.dashboard-analytics-card__miniGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.dashboard-analytics-card__miniItem {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.05);
}

.dashboard-analytics-card__miniLabel {
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.dashboard-analytics-card__miniValue {
  font-size: 1rem;
  font-weight: 700;
}

.dashboard-analytics-card__chartBlock {
  padding-top: 4px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

/*
 * Jangan paksa semua series-group tampil.
 * ApexCharts menyembunyikan group yang tidak aktif (display:none).
 * Override display:flex menyebabkan tooltip jadi redundant/duplikat.
 */
.apexcharts-tooltip-series-group {
  align-items: center !important;
}

.apexcharts-tooltip-series-group.apexcharts-active {
  display: flex !important;
}

.apexcharts-tooltip-series-group:not(.apexcharts-active) {
  display: none !important;
}

.apexcharts-tooltip-marker {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  align-self: center !important;
}

@media (max-width: 959px) {
  .dashboard-analytics-card__miniGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-analytics-card__salesOverview {
    min-height: auto;
  }

  .dashboard-analytics-card__salesMetric--end {
    text-align: left;
  }

  .dashboard-top-package-card__chart,
  .dashboard-top-package-card__empty {
    padding-bottom: 20px;
  }

  .dashboard-top-package-card :deep(.apexcharts-legend) {
    margin-top: 16px !important;
  }
}

@media (max-width: 600px) {
  .dashboard-analytics-card__miniGrid {
    grid-template-columns: 1fr;
  }

  .dashboard-analytics-card__reportFooter {
    grid-template-columns: 1fr;
  }

  .dashboard-analytics-card__body--spread {
    height: auto;
  }

  .dashboard-top-package-card__chart,
  .dashboard-top-package-card__empty {
    padding-bottom: 12px;
  }

  .dashboard-top-package-card :deep(.apexcharts-legend) {
    margin-top: 12px !important;
  }
}

</style>
