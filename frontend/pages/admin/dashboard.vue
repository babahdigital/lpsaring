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

const ACCESS_PARITY_MISMATCH_META: Record<AccessParityMismatchKey, { label: string, color: string }> = {
  binding_type: { label: 'Binding tidak sesuai', color: 'error' },
  missing_ip_binding: { label: 'IP binding belum tersedia', color: 'error' },
  address_list: { label: 'Address-list belum sinkron', color: 'error' },
  address_list_multi_status: { label: 'Address-list multi-status', color: 'warning' },
  no_authorized_device: { label: 'Perangkat belum terdaftar', color: 'default' },
  no_resolvable_ip: { label: 'IP belum terbaca', color: 'warning' },
  dhcp_lease_missing: { label: 'Lease DHCP belum tersedia', color: 'info' },
}

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

const reliabilityCards = computed(() => [
  {
    key: 'duplicate-webhook',
    title: 'Duplikat Notifikasi Pembayaran',
    value: `${reliabilitySummary.value.duplicateWebhookCount}`,
    status: reliabilitySummary.value.duplicateWebhookCount > 0 ? 'Terkendali' : 'Stabil',
    color: reliabilitySummary.value.duplicateWebhookCount > 0 ? 'info' : 'success',
    icon: 'tabler-repeat',
    caption: reliabilitySummary.value.duplicateWebhookCount > 0
      ? 'Notifikasi ganda dari payment gateway terdeteksi dan sudah ditangani otomatis oleh sistem.'
      : 'Tidak ada notifikasi ganda yang memerlukan penanganan tambahan.',
  },
  {
    key: 'payment-idempotency',
    title: 'Proteksi Transaksi Ganda',
    value: reliabilitySummary.value.paymentIdempotencyDegraded ? `${reliabilitySummary.value.paymentIdempotencyRedisUnavailableCount} gangguan` : 'Redis aktif',
    status: reliabilitySummary.value.paymentIdempotencyDegraded ? 'Perlu perhatian' : 'Stabil',
    color: reliabilitySummary.value.paymentIdempotencyDegraded ? 'error' : 'success',
    icon: 'tabler-shield-check',
    caption: reliabilitySummary.value.paymentIdempotencyDegraded
      ? `Redis tidak tersedia ${reliabilitySummary.value.paymentIdempotencyRedisUnavailableCount} kali sehingga proteksi idempotensi melemah.`
      : 'Redis tersedia sehingga potensi transaksi duplikat tetap dapat diblokir secara konsisten.',
  },
  {
    key: 'hotspot-sync-lock',
    title: 'Sinkronisasi Hotspot',
    value: reliabilitySummary.value.hotspotSyncLockDegraded ? `${reliabilitySummary.value.hotspotSyncLockDegradedCount} lock miss` : 'Lock aktif',
    status: reliabilitySummary.value.hotspotSyncLockDegraded ? 'Perlu perhatian' : 'Stabil',
    color: reliabilitySummary.value.hotspotSyncLockDegraded ? 'error' : 'success',
    icon: 'tabler-plug-connected',
    caption: reliabilitySummary.value.hotspotSyncLockDegraded
      ? `Lock sinkronisasi gagal ${reliabilitySummary.value.hotspotSyncLockDegradedCount} kali sehingga sebagian proses berjalan tanpa proteksi eksklusif.`
      : 'Lock sinkronisasi aktif dan konflik proses tidak terdeteksi pada periode pemantauan.',
  },
  {
    key: 'policy-parity',
    title: 'Konsistensi Akses Router',
    value: reliabilitySummary.value.policyParityDegraded ? `${reliabilitySummary.value.policyParityMismatchCount} mismatch` : 'Sinkron',
    status: reliabilitySummary.value.policyParityDegraded ? 'Perlu perhatian' : 'Stabil',
    color: reliabilitySummary.value.policyParityDegraded ? 'error' : 'success',
    icon: 'tabler-router',
    caption: reliabilitySummary.value.policyParityDegraded
      ? 'Status aplikasi dan MikroTik belum sepenuhnya selaras. Detail mismatch tersedia pada panel pemeriksaan.'
      : 'Status aplikasi dan MikroTik sinkron untuk kebijakan akses utama.',
  },
])

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
const accessParityDhcpDriftCount = computed(() => accessParitySummary.value.mismatchTypes.dhcp_lease_missing ?? 0)
const accessParitySyncRate = computed(() => {
  const users = accessParitySummary.value.users
  if (users <= 0)
    return 100

  const syncedUsers = Math.max(0, users - accessParitySummary.value.mismatches)
  return Math.round((syncedUsers / users) * 100)
})
const accessParityOverviewCards = computed(() => [
  {
    key: 'mismatch',
    title: 'Mismatch Akses',
    value: `${accessParitySummary.value.mismatches}`,
    subtitle: `/ ${accessParitySummary.value.users} user`,
    color: accessParitySummary.value.mismatches > 0 ? 'error' : 'success',
    icon: accessParitySummary.value.mismatches > 0 ? 'tabler-alert-circle' : 'tabler-circle-check',
    caption: accessParitySummary.value.mismatches > 0 ? 'Mismatch yang berdampak langsung pada kebijakan akses router.' : 'Seluruh akses inti sudah sinkron.',
  },
  {
    key: 'dhcp',
    title: 'Drift DHCP',
    value: `${accessParityDhcpDriftCount.value}`,
    subtitle: 'lease terpantau',
    color: accessParityDhcpDriftCount.value > 0 ? 'info' : 'success',
    icon: 'tabler-route-2',
    caption: accessParityDhcpDriftCount.value > 0 ? 'Ada lease DHCP yang belum sepenuhnya sesuai dengan state akses router.' : 'Lease DHCP konsisten dengan status akses saat ini.',
  },
  {
    key: 'onboarding',
    title: 'Belum Login Perangkat',
    value: `${accessParitySummary.value.noAuthorizedDeviceCount}`,
    subtitle: 'user onboarding',
    color: accessParitySummary.value.noAuthorizedDeviceCount > 0 ? 'warning' : 'success',
    icon: 'tabler-device-mobile-off',
    caption: accessParitySummary.value.noAuthorizedDeviceCount > 0 ? 'Pengguna sudah terdaftar namun belum pernah login dari perangkat pertama.' : 'Seluruh pengguna aktif telah memiliki perangkat awal yang terdaftar.',
  },
  {
    key: 'autofix',
    title: 'Auto-Heal Terdeteksi',
    value: `${accessParitySummary.value.autoFixableItems}`,
    subtitle: 'item non-kritis',
    color: accessParitySummary.value.autoFixableItems > 0 ? 'primary' : 'secondary',
    icon: 'tabler-refresh-alert',
    caption: accessParitySummary.value.autoFixableItems > 0 ? 'Drift yang aman ditangani akan dibersihkan otomatis oleh parity guard berkala.' : 'Tidak ada drift auto-heal yang menunggu dibersihkan.',
  },
])
const accessParityMismatchTypeCards = computed(() => {
  return Object.entries(accessParitySummary.value.mismatchTypes)
    .filter(([, count]) => Number(count ?? 0) > 0)
    .sort(([, left], [, right]) => Number(right ?? 0) - Number(left ?? 0))
    .slice(0, 4)
    .map(([key, count]) => {
      const meta = getParityMismatchMeta(key as AccessParityMismatchKey)
      return {
        key,
        label: meta.label,
        color: meta.color,
        count: Number(count ?? 0),
      }
    })
})
const accessParityContextMessage = computed(() => {
  const fragments: string[] = []
  const hasParityItems = accessParitySummary.value.mismatches > 0
  const hasNonParityItems = accessParityDhcpDriftCount.value > 0 || accessParitySummary.value.noAuthorizedDeviceCount > 0

  if (accessParitySummary.value.noAuthorizedDeviceCount > 0) {
    fragments.push(`${accessParitySummary.value.noAuthorizedDeviceCount} user belum login dari perangkat pertama.`)
  }

  if (accessParityDhcpDriftCount.value > 0) {
    fragments.push(`${accessParityDhcpDriftCount.value} drift DHCP terdeteksi.`)
  }

  if (fragments.length === 0) {
    if (hasParityItems)
      return 'Konsistensi akses inti dipantau otomatis dan masih ada mismatch yang mempengaruhi kebijakan router.'

    return 'Panel ringkasan hanya menonjolkan kondisi yang mempengaruhi akses inti. Detail teknis dipantau lewat worker dan log operasi.'
  }

  if (hasParityItems && hasNonParityItems)
    return `Mismatch akses inti dan drift non-kritis sama-sama terdeteksi. ${fragments.join(' ')} Auto-remediation tetap berjalan di background.`

  if (hasNonParityItems)
    return `Akses inti tetap sinkron. ${fragments.join(' ')} Item ini dipantau sebagai sinyal operasional, bukan tindakan manual harian.`

  return `Mismatch akses terdeteksi. ${fragments.join(' ')}`
})

function getParityMismatchMeta(mismatch: AccessParityMismatchKey): { label: string, color: string } {
  return ACCESS_PARITY_MISMATCH_META[mismatch] ?? { label: mismatch, color: 'default' }
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

    <VRow
      class="mb-4"
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
            <VCardSubtitle>Performa 7 hari dibanding minggu sebelumnya</VCardSubtitle>
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
          <VCardText class="pt-2">
            <div class="dashboard-analytics-card__headline">
              <div class="dashboard-analytics-card__value">
                {{ formatCurrency(stats?.pendapatanMingguIni) }}
              </div>
              <div class="dashboard-analytics-card__caption">
                Total pendapatan minggu aktif.
              </div>
            </div>

            <div class="dashboard-analytics-card__comparison mt-5">
              <div class="dashboard-analytics-card__comparisonItem">
                <div class="dashboard-analytics-card__comparisonLabel">
                  <VAvatar color="info" variant="tonal" :size="24" rounded class="me-2">
                    <VIcon size="16" icon="tabler-calendar-check" />
                  </VAvatar>
                  Minggu Ini
                </div>
                <div class="dashboard-analytics-card__comparisonValue">
                  {{ formatCurrency(stats?.pendapatanMingguIni) }}
                </div>
                <div class="dashboard-analytics-card__comparisonMeta">
                  {{ stats?.transaksiMingguIni ?? 0 }} transaksi
                </div>
              </div>

              <div class="dashboard-analytics-card__comparisonItem dashboard-analytics-card__comparisonItem--end">
                <div class="dashboard-analytics-card__comparisonLabel dashboard-analytics-card__comparisonLabel--end">
                  Minggu Lalu
                  <VAvatar color="secondary" variant="tonal" :size="24" rounded class="ms-2">
                    <VIcon size="16" icon="tabler-calendar-stats" />
                  </VAvatar>
                </div>
                <div class="dashboard-analytics-card__comparisonValue">
                  {{ formatCurrency(stats?.pendapatanMingguLalu) }}
                </div>
                <div class="dashboard-analytics-card__comparisonMeta">
                  {{ stats?.transaksiMingguLalu ?? 0 }} transaksi
                </div>
              </div>
            </div>

            <VProgressLinear
              class="mt-5"
              :model-value="weeklyRevenueSplit"
              color="info"
              height="10"
              bg-color="secondary"
              :rounded-bar="false"
              rounded
            />
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
            <VCardSubtitle>Akumulasi distribusi kuota dalam 7 hari terakhir</VCardSubtitle>
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
            <VRow>
              <VCol
                cols="12"
                sm="5"
                class="d-flex flex-column align-self-end"
              >
                <div class="dashboard-analytics-card__headline dashboard-analytics-card__headline--compact">
                  <div class="dashboard-analytics-card__value dashboard-analytics-card__value--xl">
                    {{ formatBytes(stats?.kuotaTerjualMb) }}
                  </div>
                  <div class="dashboard-analytics-card__caption">
                    Total kuota yang terjual pada jendela mingguan.
                  </div>
                </div>

                <div class="dashboard-analytics-card__statList mt-4">
                  <div class="dashboard-analytics-card__statRow">
                    <span>Minggu ini</span>
                    <strong>{{ formatBytes(stats?.kuotaTerjual7HariMb ?? stats?.kuotaTerjualMb) }}</strong>
                  </div>
                  <div class="dashboard-analytics-card__statRow">
                    <span>Minggu lalu</span>
                    <strong>{{ formatBytes(stats?.kuotaTerjualMingguLaluMb) }}</strong>
                  </div>
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
        <VCard class="h-100 dashboard-analytics-card dashboard-analytics-card--monthly">
          <VCardItem>
            <template #prepend>
              <VAvatar color="primary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-cash-banknote" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Pendapatan Bulan Ini</VCardTitle>
            <VCardSubtitle>Total penjualan bulan {{ currentMonthLabel }}</VCardSubtitle>
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
                Tren ini menjadi baseline untuk evaluasi performa paket dan akuisisi.
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
            <template #prepend>
              <VAvatar color="secondary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-chart-donut" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Paket Terlaris</VCardTitle>
            <VCardSubtitle>Berdasarkan jumlah penjualan bulan ini</VCardSubtitle>
            <template #append>
              <VChip size="small" color="secondary" label variant="tonal">
                {{ topSellingPackage.count > 0 ? `${topSellingPackage.count} transaksi` : 'Menunggu data' }}
              </VChip>
            </template>
          </VCardItem>
          <VCardText style="padding-bottom: 30px; padding-top: 25px;">
            <div class="dashboard-analytics-card__packageHighlight mb-4">
              <div class="dashboard-analytics-card__packageLabel">
                Paket dominan saat ini
              </div>
              <div class="dashboard-analytics-card__packageValue">
                {{ topSellingPackage.name }}
              </div>
            </div>
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
            <div class="reliability-section">
              <div class="reliability-section__hero">
                <div>
                  <div class="text-h6 font-weight-bold">
                    {{ overallReliabilityHealthy ? 'Semua jalur proteksi berjalan stabil' : 'Ada sinyal yang perlu perhatian operasional' }}
                  </div>
                  <div class="text-body-2 text-medium-emphasis mt-1">
                    Ringkasan ini menjaga fokus pada reliabilitas transaksi, lock sinkronisasi, dan konsistensi kebijakan akses router.
                  </div>
                </div>
                <div class="reliability-section__summary">
                  <div class="reliability-section__summaryLabel">
                    Status utama
                  </div>
                  <div class="reliability-section__summaryValue">
                    {{ reliabilityCards.filter(item => item.color === 'error').length }}
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    sinyal membutuhkan perhatian
                  </div>
                </div>
              </div>

              <div class="reliability-grid mt-4">
                <div v-for="item in reliabilityCards" :key="item.key" class="reliability-card">
                  <div class="reliability-card__head">
                    <div class="d-flex align-center gap-3 min-w-0">
                      <VAvatar size="40" :color="item.color" variant="tonal">
                        <VIcon :icon="item.icon" size="20" />
                      </VAvatar>
                      <div class="min-w-0">
                        <div class="reliability-card__title">{{ item.title }}</div>
                        <div class="reliability-card__status">
                          <VChip size="x-small" :color="item.color" label variant="tonal">
                            {{ item.status }}
                          </VChip>
                        </div>
                      </div>
                    </div>
                    <div class="reliability-card__value">{{ item.value }}</div>
                  </div>
                  <div class="reliability-card__caption mt-3">
                    {{ item.caption }}
                  </div>
                </div>
              </div>
            </div>
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

            <div class="access-parity">
              <div class="access-parity__hero">
                <div class="access-parity__heroCopy">
                  <div class="access-parity__eyebrow">
                    Monitor otomatis
                  </div>
                  <div class="access-parity__heroTitle">
                    {{ accessParitySyncRate }}% akses inti sinkron
                  </div>
                  <div class="text-body-2 text-medium-emphasis mt-1">
                    Parity guard menjaga sinkronisasi akses router secara berkala. Dashboard hanya menampilkan ringkasan yang relevan untuk pemantauan harian.
                  </div>
                </div>
                <div class="d-flex align-center gap-2 flex-wrap justify-end">
                  <VChip
                    size="small"
                    :color="accessParitySummary.mismatches > 0 ? 'error' : 'success'"
                    label
                    variant="tonal"
                  >
                    {{ accessParitySummary.mismatches > 0 ? `${accessParitySummary.mismatches} mismatch inti` : 'Auto-heal aktif' }}
                  </VChip>
                  <VBtn
                    v-if="authStore.isSuperAdmin === true"
                    size="small"
                    color="info"
                    variant="tonal"
                    @click="navigateTo('/admin/operations')"
                  >
                    Buka Operasional
                  </VBtn>
                </div>
              </div>

              <VProgressLinear
                class="mt-4"
                color="success"
                bg-color="error"
                rounded
                height="10"
                :model-value="accessParitySyncRate"
              />

              <div class="access-parity__overviewGrid mt-4">
                <div v-for="item in accessParityOverviewCards" :key="item.key" class="access-parity__overviewCard">
                  <div class="access-parity__overviewHead">
                    <VAvatar size="38" :color="item.color" variant="tonal">
                      <VIcon :icon="item.icon" size="18" />
                    </VAvatar>
                    <div class="access-parity__overviewMeta">
                      <div class="access-parity__overviewTitle">{{ item.title }}</div>
                      <div class="access-parity__overviewSubtitle">{{ item.subtitle }}</div>
                    </div>
                  </div>
                  <div class="access-parity__overviewValue">{{ item.value }}</div>
                  <div class="access-parity__overviewCaption">{{ item.caption }}</div>
                </div>
              </div>

              <div v-if="accessParityMismatchTypeCards.length > 0" class="access-parity__mismatchTypes mt-4">
                <div class="text-caption text-uppercase text-medium-emphasis font-weight-bold mb-2">
                  Sinyal dominan yang sedang dipantau
                </div>
                <div class="access-parity__mismatchTypeGrid">
                  <div v-for="item in accessParityMismatchTypeCards" :key="item.key" class="access-parity__mismatchTypeCard">
                    <VChip size="x-small" :color="item.color" label variant="tonal">
                      {{ item.label }}
                    </VChip>
                    <div class="access-parity__mismatchTypeValue">{{ item.count }}</div>
                  </div>
                </div>
              </div>
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

.dashboard-analytics-card__comparison {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.dashboard-analytics-card__comparisonItem {
  padding: 14px;
  border-radius: 16px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.05);
}

.dashboard-analytics-card__comparisonItem--end {
  text-align: right;
}

.dashboard-analytics-card__comparisonLabel {
  display: flex;
  align-items: center;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.dashboard-analytics-card__comparisonLabel--end {
  justify-content: flex-end;
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

.dashboard-analytics-card__statList {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dashboard-analytics-card__statRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-block-end: 10px;
  border-block-end: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
  font-size: 0.84rem;
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.dashboard-analytics-card__statRow:last-child {
  padding-block-end: 0;
  border-block-end: 0;
}

.dashboard-analytics-card__statRow strong {
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
  border-radius: 16px;
  background: rgba(var(--v-theme-on-surface), 0.03);
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

.dashboard-analytics-card__packageHighlight {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(var(--v-theme-secondary), 0.08);
}

.dashboard-analytics-card__packageLabel {
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.dashboard-analytics-card__packageValue {
  margin-top: 6px;
  font-size: 1.08rem;
  font-weight: 700;
  line-height: 1.35;
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

.reliability-section {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.reliability-section__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(var(--v-theme-primary), 0.08) 0%, rgba(var(--v-theme-surface), 0.92) 100%);
}

.reliability-section__summary {
  min-inline-size: 120px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(var(--v-theme-surface), 0.92);
  text-align: right;
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.06);
}

.reliability-section__summaryLabel {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.reliability-section__summaryValue {
  font-size: 1.8rem;
  font-weight: 800;
  line-height: 1;
}

.reliability-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.reliability-card {
  padding: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 18px;
  background: rgba(var(--v-theme-surface), 0.9);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.04);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.reliability-card:hover {
  transform: translateY(-2px);
  border-color: rgba(var(--v-theme-primary), 0.18);
  box-shadow: 0 22px 40px rgba(15, 23, 42, 0.06);
}

.reliability-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.reliability-card__title {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.reliability-card__status {
  margin-top: 6px;
}

.reliability-card__value {
  font-size: 1.08rem;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}

.reliability-card__caption {
  font-size: 0.82rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.access-parity {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.access-parity__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(var(--v-theme-info), 0.08) 0%, rgba(var(--v-theme-surface), 0.94) 100%);
}

.access-parity__heroCopy {
  min-width: 0;
}

.access-parity__eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-info), 0.92);
}

.access-parity__heroTitle {
  font-size: 1.16rem;
  font-weight: 700;
  line-height: 1.2;
  margin-top: 6px;
}

.access-parity__overviewGrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.access-parity__overviewCard {
  padding: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 18px;
  background: rgba(var(--v-theme-surface), 0.9);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.04);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.access-parity__overviewCard:hover {
  transform: translateY(-2px);
  border-color: rgba(var(--v-theme-primary), 0.18);
  box-shadow: 0 22px 40px rgba(15, 23, 42, 0.06);
}

.access-parity__overviewHead {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.access-parity__overviewMeta {
  min-width: 0;
}

.access-parity__overviewTitle {
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.access-parity__overviewSubtitle {
  margin-top: 4px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.access-parity__overviewValue {
  margin-top: 14px;
  font-size: 1.42rem;
  font-weight: 700;
  line-height: 1.1;
}

.access-parity__overviewCaption {
  margin-top: 8px;
  font-size: 0.82rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.access-parity__mismatchTypes {
  padding: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 18px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.access-parity__mismatchTypeGrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.access-parity__mismatchTypeCard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(var(--v-theme-surface), 0.92);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.05);
}

.access-parity__mismatchTypeValue {
  font-size: 1rem;
  font-weight: 700;
}

@media (max-width: 959px) {
  .dashboard-analytics-card__comparison,
  .dashboard-analytics-card__miniGrid,
  .reliability-grid,
  .access-parity__overviewGrid,
  .access-parity__mismatchTypeGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .reliability-section__hero,
  .access-parity__hero {
    flex-direction: column;
  }

  .reliability-section__summary {
    width: 100%;
  }

  .reliability-grid,
  .dashboard-analytics-card__comparison,
  .dashboard-analytics-card__miniGrid,
  .access-parity__overviewGrid,
  .access-parity__mismatchTypeGrid {
    grid-template-columns: 1fr;
  }

  .dashboard-analytics-card__comparisonItem--end {
    text-align: left;
  }

  .dashboard-analytics-card__comparisonLabel--end {
    justify-content: flex-start;
  }

  .access-parity__hero {
    padding: 16px;
  }
}

</style>
