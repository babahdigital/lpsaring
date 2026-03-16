<script setup lang="ts">
import { useFetch, useNuxtApp } from '#app'
import { hexToRgb } from '@layouts/utils'
import { computed, defineAsyncComponent, h, onMounted, ref, watch } from 'vue'
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

interface AccessParityItem {
  user_id: string
  phone_number: string
  mac?: string | null
  ip?: string | null
  app_status: string
  expected_status?: string
  expected_binding_type: string
  actual_binding_type?: string | null
  address_list_statuses: string[]
  mismatches: AccessParityMismatchKey[]
  auto_fixable?: boolean
  parity_relevant?: boolean
}

interface AccessParityResponse {
  items?: AccessParityItem[]
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

interface AccessParityFixResponse {
  message?: string
  user_id?: string
  mac?: string | null
  resolved_ip?: string | null
  expected_binding_type?: string
  binding_updated?: boolean
  dhcp_synced?: boolean
  address_list_synced?: boolean
  auto_selected_mac?: boolean
  warnings?: string[]
}

// --- State & Fetching ---
const { $api } = useNuxtApp()

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

// --- Data untuk Kartu Statistik Atas (Diperbarui) ---
const statistics = ref([
  { icon: 'tabler-mail-fast', color: 'info', title: 'Permintaan Tertunda', value: 0, to: '/admin/requests' },
  { icon: 'tabler-calendar-exclamation', color: 'warning', title: 'Akan Kadaluwarsa', value: 0, to: '/admin/users' },
  { icon: 'tabler-user-search', color: 'secondary', title: 'Menunggu Persetujuan', value: 0, to: '/admin/users' },
  { icon: 'tabler-database-export', color: 'primary', title: 'File Backup', value: 0 },
])

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
  await fetchBackupFileCount()
})

const reliabilitySummary = computed(() => buildReliabilitySummary(adminMetrics.value))

const ACCESS_PARITY_MISMATCH_META: Record<AccessParityMismatchKey, { label: string, color: string }> = {
  binding_type: { label: 'binding_type', color: 'error' },
  missing_ip_binding: { label: 'missing_ip_binding', color: 'error' },
  address_list: { label: 'address_list', color: 'error' },
  address_list_multi_status: { label: 'address_list_multi_status', color: 'warning' },
  no_authorized_device: { label: 'belum_setup_perangkat', color: 'default' },
  no_resolvable_ip: { label: 'ip_belum_terbaca', color: 'warning' },
  dhcp_lease_missing: { label: 'dhcp_lease_missing', color: 'info' },
}

const ACTIONABLE_PARITY_MISMATCHES = new Set<AccessParityMismatchKey>([
  'binding_type',
  'missing_ip_binding',
  'address_list',
  'address_list_multi_status',
  'no_resolvable_ip',
])

const reliabilitySignalItems = computed(() => [
  {
    key: 'payment-idempotency',
    label: 'Payment Idempotency',
    degraded: reliabilitySummary.value.paymentIdempotencyDegraded,
    detail: `Redis unavailable: ${reliabilitySummary.value.paymentIdempotencyRedisUnavailableCount}`,
  },
  {
    key: 'hotspot-sync-lock',
    label: 'Hotspot Sync Lock',
    degraded: reliabilitySummary.value.hotspotSyncLockDegraded,
    detail: `Lock degraded: ${reliabilitySummary.value.hotspotSyncLockDegradedCount}`,
  },
  {
    key: 'policy-parity',
    label: 'Policy Parity',
    degraded: reliabilitySummary.value.policyParityDegraded,
    detail: `Mismatch parity: ${reliabilitySummary.value.policyParityMismatchCount} (onboarding gap dikecualikan)`,
  },
])

const overallReliabilityHealthy = computed(() => {
  return reliabilitySignalItems.value.every(item => item.degraded === false)
})

async function handleRefreshDashboard() {
  await Promise.all([
    refresh(),
    refreshMetrics(),
    refreshParity(),
    fetchBackupFileCount(),
  ])
}

const accessParityItems = computed(() => accessParity.value?.items ?? [])
const accessParitySummary = computed(() => ({
  users: accessParity.value?.summary?.users ?? 0,
  mismatches: accessParity.value?.summary?.mismatches ?? 0,
  mismatchesTotal: accessParity.value?.summary?.mismatches_total ?? 0,
  nonParityMismatches: accessParity.value?.summary?.non_parity_mismatches ?? 0,
  noAuthorizedDeviceCount: accessParity.value?.summary?.no_authorized_device_count ?? 0,
  autoFixableItems: accessParity.value?.summary?.auto_fixable_items ?? 0,
  mismatchTypes: accessParity.value?.summary?.mismatch_types ?? {},
}))
const accessParityDhcpDriftCount = computed(() => accessParitySummary.value.mismatchTypes.dhcp_lease_missing ?? 0)
const accessParityContextMessage = computed(() => {
  const fragments: string[] = []

  if (accessParitySummary.value.noAuthorizedDeviceCount > 0) {
    fragments.push(`${accessParitySummary.value.noAuthorizedDeviceCount} user belum login dari perangkat pertama.`)
  }

  if (accessParityDhcpDriftCount.value > 0) {
    fragments.push(`${accessParityDhcpDriftCount.value} drift DHCP terdeteksi.`)
  }

  if (fragments.length === 0) {
    if (accessParitySummary.value.mismatches > 0)
      return 'Tabel di bawah fokus ke mismatch akses yang masih mempengaruhi sinkronisasi policy di router.'

    return 'Yang dihitung merah hanya mismatch akses yang benar-benar mempengaruhi policy router.'
  }

  return `Tabel di bawah fokus ke mismatch akses. ${fragments.join(' ')}`
})
const fixingParityByKey = ref<Record<string, boolean>>({})
const parityFixMessage = ref('')
const parityFixError = ref('')

function getParityKey(item: AccessParityItem): string {
  const macPart = item.mac || 'no-mac'
  return `${item.user_id}-${macPart}-${item.mismatches.join('_')}`
}

function getParityMismatchMeta(mismatch: AccessParityMismatchKey): { label: string, color: string } {
  return ACCESS_PARITY_MISMATCH_META[mismatch] ?? { label: mismatch, color: 'default' }
}

function hasActionableParityMismatch(item: AccessParityItem): boolean {
  return item.mismatches.some(mismatch => ACTIONABLE_PARITY_MISMATCHES.has(mismatch))
}

function getParityActionLabel(item: AccessParityItem): string {
  if (item.auto_fixable === false)
    return 'Manual'

  if (item.mismatches.includes('address_list') || item.mismatches.includes('address_list_multi_status'))
    return 'Sinkronkan'

  if (item.mismatches.includes('binding_type') || item.mismatches.includes('missing_ip_binding'))
    return 'Perbaiki akses'

  if (item.mismatches.includes('dhcp_lease_missing'))
    return hasActionableParityMismatch(item) ? 'Sinkronkan' : 'Pantau'

  return 'Periksa'
}

function buildParityFixMessage(item: AccessParityItem, result: AccessParityFixResponse): string {
  const appliedSteps: string[] = []
  const warnings = (result.warnings ?? []).filter(Boolean)

  if (result.binding_updated)
    appliedSteps.push('ip-binding')

  if (result.address_list_synced)
    appliedSteps.push('address-list')

  if (result.dhcp_synced)
    appliedSteps.push('DHCP static lease')

  const headline = result.message || `Sinkronisasi dijalankan untuk ${item.phone_number}`
  const stepsText = appliedSteps.length > 0 ? ` Langkah: ${appliedSteps.join(', ')}.` : ''
  const warningText = warnings.length > 0 ? ` Catatan: ${warnings.join(' ')}` : ''

  return `${headline}${stepsText}${warningText}`.trim()
}

async function handleFixParityItem(item: AccessParityItem) {
  if (item.auto_fixable === false)
    return

  const key = getParityKey(item)
  if (fixingParityByKey.value[key])
    return

  fixingParityByKey.value[key] = true
  parityFixMessage.value = ''
  parityFixError.value = ''

  try {
    const result = await $api<AccessParityFixResponse>('/admin/metrics/access-parity/fix', {
      method: 'POST',
      body: {
        user_id: item.user_id,
        mac: item.mac ?? null,
        ip: item.ip ?? null,
      },
    })
    parityFixMessage.value = buildParityFixMessage(item, result ?? {})
    await Promise.all([refreshParity(), refreshMetrics()])
  }
  catch (error) {
    const errMsg = (error as Error)?.message || 'Gagal eksekusi parity fix.'
    parityFixError.value = errMsg
  }
  finally {
    delete fixingParityByKey.value[key]
  }
}

// --- Logika Perbandingan ---
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
      markers: { offsetX: -3 },
      itemMargin: { horizontal: 10 },
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

    <VRow class="mb-4">
      <VCol
        v-for="(data, index) in statistics"
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

    <VRow
      class="mb-4"
      match-height
    >
      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100">
          <VCardItem>
            <VCardTitle>Pendapatan Mingguan</VCardTitle>
            <template #append>
              <div
                class="font-weight-medium"
                :class="perbandinganPendapatanMingguan.persentase >= 0 ? 'text-success' : 'text-error'"
              >
                <span v-if="stats?.pendapatanMingguLalu === 0 && (stats?.pendapatanMingguIni ?? 0) > 0">BARU</span>
                <span v-else>{{ perbandinganPendapatanMingguan.persentase >= 0 ? '+' : '' }}{{ perbandinganPendapatanMingguan.persentase.toFixed(1) }}%</span>
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <h4 class="text-h4 my-2">
              {{ formatCurrency(stats?.pendapatanMingguIni) }}
            </h4>
            <div class="text-body-2 text-disabled">
              Total pendapatan minggu ini
            </div>
          </VCardText>

          <VCardText>
            <VRow no-gutters>
              <VCol cols="5">
                <div class="d-flex align-center mb-3">
                  <VAvatar
                    color="info"
                    variant="tonal"
                    :size="24"
                    rounded
                    class="me-2"
                  >
                    <VIcon
                      size="18"
                      icon="tabler-calendar-check"
                    />
                  </VAvatar>
                  <span>Minggu Ini</span>
                </div>
                <h5 class="text-h5">
                  {{ formatCurrency(stats?.pendapatanMingguIni) }}
                </h5>
                <div class="text-body-2 text-disabled">
                  {{ stats?.transaksiMingguIni ?? 0 }} Transaksi
                </div>
              </VCol>

              <VCol cols="2">
                <div class="d-flex flex-column align-center justify-center h-100">
                  <VDivider
                    vertical
                    class="mx-auto"
                  />
                  <VAvatar
                    size="24"
                    color="rgba(var(--v-theme-on-surface), var(--v-hover-opacity))"
                    class="my-2"
                  >
                    <div class="text-overline text-disabled">
                      VS
                    </div>
                  </VAvatar>
                  <VDivider
                    vertical
                    class="mx-auto"
                  />
                </div>
              </VCol>

              <VCol
                cols="5"
                class="text-end"
              >
                <div class="d-flex align-center justify-end mb-3">
                  <span class="me-2">Minggu Lalu</span>
                  <VAvatar
                    color="secondary"
                    variant="tonal"
                    :size="24"
                    rounded
                  >
                    <VIcon
                      size="18"
                      icon="tabler-calendar-stats"
                    />
                  </VAvatar>
                </div>
                <h5 class="text-h5">
                  {{ formatCurrency(stats?.pendapatanMingguLalu) }}
                </h5>
                <div class="text-body-2 text-disabled">
                  {{ stats?.transaksiMingguLalu ?? 0 }} Transaksi
                </div>
              </VCol>
            </VRow>
            <div class="mt-6">
              <VProgressLinear
                :model-value="((stats?.pendapatanMingguIni ?? 0) + (stats?.pendapatanMingguLalu ?? 0)) > 0 ? ((stats?.pendapatanMingguIni ?? 0) / ((stats?.pendapatanMingguIni ?? 0) + (stats?.pendapatanMingguLalu ?? 0))) * 100 : 0"
                color="info"
                height="10"
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
        <VCard class="h-100">
          <VCardItem class="pb-sm-8">
            <VCardTitle>Kuota Terjual</VCardTitle>
            <VCardSubtitle>Laporan Mingguan</VCardSubtitle>
          </VCardItem>
          <VCardText class="pt-sm-4">
            <VRow>
              <VCol
                cols="12"
                sm="5"
                class="d-flex flex-column align-self-end"
              >
                <div class="d-flex align-center gap-2 mb-3 flex-wrap">
                  <h4 class="text-h2">
                    {{ formatBytes(stats?.kuotaTerjualMb) }}
                  </h4>
                  <VChip
                    label
                    size="small"
                    :color="perbandinganKuota.persentase >= 0 ? 'success' : 'error'"
                  >
                    {{ perbandinganKuota.persentase >= 0 ? '+' : '' }}{{ perbandinganKuota.persentase.toFixed(1) }}%
                  </VChip>
                </div>
              </VCol>

              <VCol
                cols="12"
                sm="7"
                class="mt-auto"
              >
                <ClientOnly>
                  <VueApexCharts
                    :options="kuotaChartOptions"
                    :series="kuotaChartSeries"
                    :height="150"
                  />
                  <template #fallback>
                    <div
                      class="d-flex align-center justify-center"
                      style="height: 150px;"
                    >
                      <VProgressCircular
                        indeterminate
                        color="primary"
                      />
                    </div>
                  </template>
                </ClientOnly>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>
      </VCol>

      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100">
          <VCardText>
            <h5 class="text-h5 mb-3">
              Pendapatan Bulan Ini
            </h5>
            <p class="mb-0">
              Total Penjualan Bulan {{ currentMonthLabel }}
            </p>
            <h4 class="text-h4">
              {{ formatCurrency(stats?.pendapatanBulanIni) }}
            </h4>
          </VCardText>
          <ClientOnly>
            <VueApexCharts
              :options="pendapatanBulanIniChartOptions"
              :series="pendapatanBulanIniChartSeries"
              :height="122"
            />
            <template #fallback>
              <div
                class="d-flex align-center justify-center"
                style="height: 122px;"
              >
                <VProgressCircular
                  indeterminate
                  color="primary"
                />
              </div>
            </template>
          </ClientOnly>
        </VCard>
      </VCol>
    </VRow>

    <VRow class="mb-4">
      <VCol
        cols="12"
        md="5"
      >
        <VCard>
          <VCardItem>
            <VCardTitle>Paket Terlaris</VCardTitle>
            <VCardSubtitle>Berdasarkan jumlah penjualan bulan ini</VCardSubtitle>
          </VCardItem>
          <VCardText style="padding-bottom: 30px; padding-top: 25px;">
            <ClientOnly>
              <VueApexCharts
                v-if="!showInitialSkeleton && paketTerlarisChartSeries.length > 0 && paketTerlarisChartSeries.some((s: number) => s > 0)"
                type="donut"
                height="350"
                :options="paketTerlarisChartOptions"
                :series="paketTerlarisChartSeries"
              />
              <div
                v-else-if="!showInitialSkeleton"
                class="d-flex flex-column align-center justify-center text-center"
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
                class="d-flex align-center justify-center"
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
        <VCard>
          <VCardItem>
            <VCardTitle>Aktivitas Terakhir</VCardTitle>
            <template #append>
              <div class="me-n2">
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

    <VRow>
      <VCol cols="12">
        <VCard>
          <VCardItem>
            <VCardTitle class="d-flex align-center gap-2 flex-wrap">
              <VIcon icon="tabler-activity-heartbeat" size="20" />
              Kesehatan Sistem
            </VCardTitle>
            <VCardSubtitle>Monitor keandalan pembayaran, sinkronisasi, dan routing akses</VCardSubtitle>
            <div class="mt-2">
              <VChip
                size="small"
                label
                :color="overallReliabilityHealthy ? 'success' : 'error'"
              >
                <VIcon :icon="overallReliabilityHealthy ? 'tabler-circle-check' : 'tabler-alert-triangle'" size="14" class="me-1" />
                {{ overallReliabilityHealthy ? 'Semua Normal' : 'Ada yang Perlu Perhatian' }}
              </VChip>
              <VChip
                v-if="metricsPending"
                size="small"
                label
                color="default"
                class="ms-2"
              >
                <VIcon icon="tabler-refresh" size="13" class="me-1" />
                Memperbarui...
              </VChip>
            </div>
          </VCardItem>
          <VCardText>
            <VRow>
              <!-- Duplikat Webhook Pembayaran -->
              <VCol cols="12" sm="6" md="3">
                <div class="reliability-metric-box rounded pa-3">
                  <div class="d-flex align-center gap-2 mb-2">
                    <VIcon
                      icon="tabler-repeat"
                      size="18"
                      :class="reliabilitySummary.duplicateWebhookCount > 0 ? 'text-info' : 'text-success'"
                    />
                    <span class="text-body-2 font-weight-medium">Duplikat Notifikasi Pembayaran</span>
                  </div>
                  <div class="d-flex align-center gap-2">
                    <span class="text-h6">{{ reliabilitySummary.duplicateWebhookCount }}</span>
                    <VChip
                      v-if="reliabilitySummary.duplicateWebhookCount === 0"
                      size="x-small"
                      color="success"
                      label
                      variant="tonal"
                    >
                      Tidak ada
                    </VChip>
                    <VChip
                      v-else
                      size="x-small"
                      color="info"
                      label
                      variant="tonal"
                    >
                      Ditangani
                    </VChip>
                  </div>
                  <div class="text-caption text-disabled mt-1">
                    Notifikasi ganda dari payment gateway — ditangani otomatis oleh sistem
                  </div>
                </div>
              </VCol>

              <!-- Proteksi Transaksi Ganda -->
              <VCol cols="12" sm="6" md="3">
                <div class="reliability-metric-box rounded pa-3">
                  <div class="d-flex align-center gap-2 mb-2">
                    <VIcon
                      icon="tabler-shield-check"
                      size="18"
                      :class="reliabilitySummary.paymentIdempotencyDegraded ? 'text-error' : 'text-success'"
                    />
                    <span class="text-body-2 font-weight-medium">Proteksi Transaksi Ganda</span>
                  </div>
                  <div class="d-flex align-center gap-2">
                    <VChip
                      size="small"
                      label
                      :color="reliabilitySummary.paymentIdempotencyDegraded ? 'error' : 'success'"
                    >
                      {{ reliabilitySummary.paymentIdempotencyDegraded ? 'Degraded' : 'Normal' }}
                    </VChip>
                  </div>
                  <div class="text-caption text-disabled mt-1">
                    Redis {{ reliabilitySummary.paymentIdempotencyDegraded ? `tidak tersedia ${reliabilitySummary.paymentIdempotencyRedisUnavailableCount}x — idempotency melemah` : 'tersedia — transaksi duplikat dicegah' }}
                  </div>
                </div>
              </VCol>

              <!-- Sinkronisasi Hotspot -->
              <VCol cols="12" sm="6" md="3">
                <div class="reliability-metric-box rounded pa-3">
                  <div class="d-flex align-center gap-2 mb-2">
                    <VIcon
                      icon="tabler-plug-connected"
                      size="18"
                      :class="reliabilitySummary.hotspotSyncLockDegraded ? 'text-error' : 'text-success'"
                    />
                    <span class="text-body-2 font-weight-medium">Sinkronisasi Hotspot</span>
                  </div>
                  <div class="d-flex align-center gap-2">
                    <VChip
                      size="small"
                      label
                      :color="reliabilitySummary.hotspotSyncLockDegraded ? 'error' : 'success'"
                    >
                      {{ reliabilitySummary.hotspotSyncLockDegraded ? 'Degraded' : 'Normal' }}
                    </VChip>
                  </div>
                  <div class="text-caption text-disabled mt-1">
                    {{ reliabilitySummary.hotspotSyncLockDegraded ? `Lock gagal ${reliabilitySummary.hotspotSyncLockDegradedCount}x — sync berjalan tanpa proteksi` : 'Lock aktif — tidak ada konflik sinkronisasi' }}
                  </div>
                </div>
              </VCol>

              <!-- Konsistensi Akses Router -->
              <VCol cols="12" sm="6" md="3">
                <div class="reliability-metric-box rounded pa-3">
                  <div class="d-flex align-center gap-2 mb-2">
                    <VIcon
                      icon="tabler-router"
                      size="18"
                      :class="reliabilitySummary.policyParityDegraded ? 'text-error' : 'text-success'"
                    />
                    <span class="text-body-2 font-weight-medium">Konsistensi Akses Router</span>
                  </div>
                  <div class="d-flex align-center gap-2">
                    <VChip
                      size="small"
                      label
                      :color="reliabilitySummary.policyParityDegraded ? 'error' : 'success'"
                    >
                      {{ reliabilitySummary.policyParityDegraded ? `${reliabilitySummary.policyParityMismatchCount} Mismatch` : 'Normal' }}
                    </VChip>
                  </div>
                  <div class="text-caption text-disabled mt-1">
                    {{ reliabilitySummary.policyParityDegraded ? 'Status app dan MikroTik tidak sinkron — lihat tabel di bawah' : 'Status app dan MikroTik sinkron' }}
                  </div>
                </div>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VRow class="mt-4">
      <VCol cols="12">
        <VCard>
          <VCardItem>
            <VCardTitle class="d-flex align-center gap-2 flex-wrap">
              <VIcon icon="tabler-shield-half-filled" size="20" />
              Konsistensi Akses (App vs MikroTik)
            </VCardTitle>
            <VCardSubtitle>Perbandingan status izin akses antara database aplikasi dan router MikroTik secara realtime</VCardSubtitle>
            <div class="mt-2 d-flex flex-wrap gap-2">
              <VChip
                size="small"
                label
                :color="accessParitySummary.mismatches > 0 ? 'error' : 'success'"
              >
                <VIcon :icon="accessParitySummary.mismatches > 0 ? 'tabler-alert-circle' : 'tabler-circle-check'" size="14" class="me-1" />
                {{ accessParitySummary.mismatches > 0 ? `${accessParitySummary.mismatches} mismatch akses` : 'Akses inti sinkron' }}
                <span class="ms-1 opacity-70">/ {{ accessParitySummary.users }} user</span>
              </VChip>
              <VChip
                v-if="accessParityDhcpDriftCount > 0"
                size="small"
                label
                color="info"
              >
                <VIcon icon="tabler-route-2" size="14" class="me-1" />
                {{ accessParityDhcpDriftCount }} drift DHCP
              </VChip>
              <VChip
                v-if="accessParitySummary.noAuthorizedDeviceCount > 0"
                size="small"
                label
                color="default"
              >
                <VIcon icon="tabler-device-mobile-off" size="14" class="me-1" />
                {{ accessParitySummary.noAuthorizedDeviceCount }} belum login perangkat
              </VChip>
              <VChip
                v-if="parityPending"
                size="small"
                label
                color="default"
              >
                <VIcon icon="tabler-refresh" size="13" class="me-1" />
                Memuat...
              </VChip>
            </div>
          </VCardItem>
          <VCardText>
            <VAlert
              v-if="!parityPending && accessParityContextMessage"
              type="info"
              variant="tonal"
              density="compact"
              class="mb-3"
              icon="tabler-info-circle"
            >
              {{ accessParityContextMessage }}
            </VAlert>

            <!-- Fix result messages -->
            <VAlert
              v-if="parityFixMessage"
              type="success"
              variant="tonal"
              density="compact"
              class="mb-3"
              closable
              @click:close="parityFixMessage = ''"
            >
              {{ parityFixMessage }}
            </VAlert>
            <VAlert
              v-if="parityFixError"
              type="error"
              variant="tonal"
              density="compact"
              class="mb-3"
              closable
              @click:close="parityFixError = ''"
            >
              {{ parityFixError }}
            </VAlert>

            <!-- Mismatch Table — horizontally scrollable on mobile -->
            <div style="overflow-x: auto;">
              <VTable density="compact" style="min-width: 680px;">
                <thead>
                  <tr>
                    <th>No. HP</th>
                    <th>MAC</th>
                    <th>IP</th>
                    <th>Status App / Target</th>
                    <th>Binding Exp / Aktual</th>
                    <th>Address-list</th>
                    <th>Masalah</th>
                    <th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in accessParityItems.slice(0, 20)" :key="getParityKey(item)">
                    <td>{{ item.phone_number }}</td>
                    <td class="text-caption">{{ item.mac || '-' }}</td>
                    <td>{{ item.ip || '-' }}</td>
                    <td>{{ item.app_status }} / {{ item.expected_status || '-' }}</td>
                    <td>{{ item.expected_binding_type }} / {{ item.actual_binding_type || '-' }}</td>
                    <td class="text-caption">{{ item.address_list_statuses.join(', ') || '-' }}</td>
                    <td>
                      <VChip
                        v-for="m in item.mismatches"
                        :key="m"
                        size="x-small"
                        :color="getParityMismatchMeta(m).color"
                        label
                        variant="tonal"
                        class="me-1"
                      >
                        {{ getParityMismatchMeta(m).label }}
                      </VChip>
                      <span v-if="item.mismatches.length === 0" class="text-disabled">-</span>
                    </td>
                    <td>
                      <VBtn
                        size="x-small"
                        :color="item.auto_fixable === false ? 'default' : 'primary'"
                        variant="tonal"
                        :loading="Boolean(fixingParityByKey[getParityKey(item)])"
                        :disabled="Boolean(fixingParityByKey[getParityKey(item)]) || item.auto_fixable === false"
                        @click="handleFixParityItem(item)"
                      >
                        {{ getParityActionLabel(item) }}
                      </VBtn>
                    </td>
                  </tr>
                  <tr v-if="accessParityItems.length === 0">
                    <td colspan="8" class="text-center text-disabled py-4">
                      <VIcon icon="tabler-circle-check" size="20" color="success" class="me-2" />
                      Semua perangkat aktif sudah sinkron dengan router.
                    </td>
                  </tr>
                </tbody>
              </VTable>
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

.reliability-metric-box {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  height: 100%;
  transition: border-color 0.2s;

  &:hover {
    border-color: rgba(var(--v-theme-primary), 0.4);
  }
}

</style>
