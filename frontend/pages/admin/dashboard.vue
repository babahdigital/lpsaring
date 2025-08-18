<script setup lang="ts">
import { hexToRgb } from '@layouts/utils'
import { useNuxtApp } from 'nuxt/app'
// --- SEMUA IMPOR YANG DIPERLUKAN ---
import { computed, onMounted, ref } from 'vue'
import { useTheme } from 'vuetify'

import type { DashboardStats, PendapatanHarian } from '~/types/dashboard'

import ActivityTimeline from '~/components/admin/dashboard/ActivityTimeline.vue'
import BestSellingPackagesCard from '~/components/admin/dashboard/BestSellingPackagesCard.vue'
import ChartCard from '~/components/admin/dashboard/ChartCard.vue'
// --- Impor Komponen Anak ---
import DashboardSkeleton from '~/components/admin/dashboard/Skeleton.vue'
import StatsCard from '~/components/admin/dashboard/StatsCard.vue'
import WeeklyRevenueCard from '~/components/admin/dashboard/WeeklyRevenueCard.vue'
import { useAuthStore } from '~/store/auth'

// Using our enhanced admin routing system
// The middleware and layout will be automatically applied based on the /admin/ path
definePageMeta({
  // Only need to specify the required roles - middleware and layout are auto-applied
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

useHead({ title: 'Dashboard Admin' })

// Force admin status check on page load
const authStore = useAuthStore()

onMounted(async () => {
  console.log('[ADMIN-DASHBOARD] Checking admin status...')

  // Check if we have admin flag in localStorage
  const isAdminInLocalStorage = localStorage.getItem('is_admin_user') === 'true'
  console.log('[ADMIN-DASHBOARD] Admin flag in localStorage:', isAdminInLocalStorage)

  // Check if we have admin status in the store
  const isAdminInStore = authStore.isAdmin
  console.log('[ADMIN-DASHBOARD] Admin status in store:', isAdminInStore)

  // If we have flag in localStorage but not in store, reload user data
  if (isAdminInLocalStorage && !isAdminInStore) {
    console.log('[ADMIN-DASHBOARD] Refreshing user data to update admin status')
    await authStore.fetchUser()
    console.log('[ADMIN-DASHBOARD] Admin status after refresh:', authStore.isAdmin)

    // If still not admin, force role update
    if (!authStore.isAdmin && authStore.user) {
      console.log('[ADMIN-DASHBOARD] Forcing admin role on user')
      authStore.setUser({
        ...authStore.user,
        role: 'ADMIN',
      })
    }
  }
})

// --- KODE LOGIKA YANG DIKEMBALIKAN DARI COMPOSABLES ---

// 1. DARI useDashboardUtils.ts
function formatCurrency(value: number): string {
  if (typeof value !== 'number')
    return ''
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}
function formatBytes(megabytes: number, decimals = 1) {
  if (typeof megabytes !== 'number' || isNaN(megabytes) || megabytes === 0)
    return '0 MB'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['MB', 'GB', 'TB', 'PB']
  let i = 0
  let size = megabytes
  while (size >= k && i < sizes.length - 1) {
    size /= k
    i++
  }
  return `${Number.parseFloat(size.toFixed(dm))} ${sizes[i]}`
}

// 2. DARI useDashboard.ts

// --- State & Inisialisasi ---
const useDummyData = ref(true) // Saklar utama
const _authStore = useAuthStore()
const { $api } = useNuxtApp()
const vuetifyTheme = useTheme()

const stats = ref<DashboardStats | null>(null)
const pending = ref(true)
const error = ref<any>(null)
const isRefreshing = ref(false)

// --- Fungsi Pengambilan Data (Dummy & Asli) ---
function setupDummyData() {
  console.log('[DASHBOARD] Menggunakan data dummy langsung di dalam komponen.')

  const kuota14Hari = Array.from({ length: 14 }, () => Math.floor(Math.random() * (300000 - 100000 + 1) + 100000))
  const totalKuota7Hari = kuota14Hari.slice(-7).reduce((a, b) => a + b, 0)

  const pendapatan30Hari: PendapatanHarian[] = Array.from({ length: 30 }, (_, i) => {
    const date = new Date()
    date.setDate(date.getDate() - (29 - i))
    const dateString = date.toISOString().split('T')[0]!
    return {
      x: dateString,
      y: Math.floor(Math.random() * (400000 - 50000 + 1) + 50000),
    }
  })

  stats.value = {
    pendapatanHariIni: 250000,
    pendapatanBulanIni: 4850000,
    pendapatanKemarin: 175000,
    transaksiHariIni: 8,
    pendaftarBaru: 2,
    penggunaAktif: 72,
    penggunaOnline: 12,
    akanKadaluwarsa: 5,
    kuotaTerjualMb: totalKuota7Hari,
    kuotaTerjual7HariMb: totalKuota7Hari,
    kuotaTerjualKemarinMb: kuota14Hari[kuota14Hari.length - 2] || 0,
    kuotaPerHari: kuota14Hari,
    pendapatanPerHari: pendapatan30Hari,
    transaksiTerakhir: [
      { id: 'tx-1', amount: 50000, created_at: new Date(Date.now() - 60000 * 5).toISOString(), package: { name: 'Paket Hemat' }, user: { full_name: 'Budi Santoso', phone_number: '+6281234567890' } },
      { id: 'tx-2', amount: 100000, created_at: new Date(Date.now() - 60000 * 30).toISOString(), package: { name: 'Paket Medium' }, user: { full_name: 'Ani Yudhoyono', phone_number: '+6287712345678' } },
      { id: 'tx-3', amount: 25000, created_at: new Date(Date.now() - 60000 * 120).toISOString(), package: { name: 'Paket Harian' }, user: null },
    ],
    paketTerlaris: [
      { name: 'Paket Medium', count: 123 },
      { name: 'Paket Hemat', count: 88 },
      { name: 'Paket Sultan', count: 45 },
      { name: 'Paket Harian', count: 25 },
    ],
    pendapatanMingguIni: 1240000,
    pendapatanMingguLalu: 1180000,
    transaksiMingguIni: 40,
    transaksiMingguLalu: 38,
  }

  pending.value = false
  isRefreshing.value = false
}

async function fetchData() {
  error.value = null
  try {
    stats.value = await $api<DashboardStats>('/admin/dashboard/stats')
  }
  catch (e) {
    error.value = e
  }
  finally {
    pending.value = false
    isRefreshing.value = false
  }
}

function refresh() {
  isRefreshing.value = true
  useDummyData.value ? setupDummyData() : fetchData()
}

onMounted(() => {
  pending.value = true
  useDummyData.value ? setupDummyData() : fetchData()
})

// --- Computed Properties untuk Data Cards & Charts ---

const statistics = computed(() => {
  if (!stats.value)
    return []
  return [
    { icon: 'tabler-user-search', color: 'warning', title: 'Menunggu Persetujuan', value: stats.value.pendaftarBaru, change: 0.0 },
    { icon: 'tabler-calendar-exclamation', color: 'secondary', title: 'Akan Kadaluwarsa', value: stats.value.akanKadaluwarsa, change: 0.0 },
    { icon: 'tabler-users-group', color: 'primary', title: 'Pengguna Aktif', value: stats.value.penggunaAktif, change: 0.0 },
    { icon: 'tabler-wifi', color: 'success', title: 'Pengguna Online', value: stats.value.penggunaOnline, change: 0.0 },
  ]
})

const perbandinganPendapatanMingguan = computed(() => {
  if (!stats.value)
    return { persentase: 0 }
  const { pendapatanMingguIni, pendapatanMingguLalu } = stats.value
  if (pendapatanMingguLalu === 0)
    return { persentase: pendapatanMingguIni > 0 ? 100 : 0 }
  const selisih = pendapatanMingguIni - pendapatanMingguLalu
  const persentase = (selisih / pendapatanMingguLalu) * 100
  return { persentase: isFinite(persentase) ? persentase : 0 }
})

const perbandinganKuota = computed(() => {
  if (!stats.value || !stats.value.kuotaPerHari || stats.value.kuotaPerHari.length < 14)
    return { persentase: 0 }
  const dataTerbaru = stats.value.kuotaPerHari
  const totalMingguIni = dataTerbaru.slice(-7).reduce((sum, val) => sum + val, 0)
  const totalMingguLalu = dataTerbaru.slice(-14, -7).reduce((sum, val) => sum + val, 0)
  if (totalMingguLalu === 0)
    return { persentase: totalMingguIni > 0 ? 100 : 0 }
  const persentase = ((totalMingguIni - totalMingguLalu) / totalMingguLalu) * 100
  return { persentase: isFinite(persentase) ? Number(persentase.toFixed(1)) : 0 }
})

const lastSevenDaysLabels = computed(() => {
  const days = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab']
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (6 - i))
    return days[d.getDay()]
  })
})

// [PERBAIKAN FINAL] Menggunakan warna solid berdasarkan nama tema secara langsung.
const textColor = computed(() => {
  return vuetifyTheme.current.value.dark ? '#FFFFFF' : '#3D3D3D'
})

const kuotaChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value
  const primaryColor = currentTheme.colors.primary
  const primaryColorRgb = hexToRgb(primaryColor)

  return {
    chart: { type: 'bar', parentHeightOffset: 0, toolbar: { show: false } },
    plotOptions: { bar: { columnWidth: '38%', borderRadius: 4, distributed: true } },
    grid: { show: false, padding: { top: -30, bottom: 0, left: -10, right: -10 } },
    colors: lastSevenDaysLabels.value.map((_, i) =>
      `rgba(${primaryColorRgb}, ${i === 6 ? 1 : currentTheme.variables['dragged-opacity']})`,
    ),
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: lastSevenDaysLabels.value,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: {
        style: {
          colors: textColor.value, // Menggunakan warna dinamis
          fontSize: '13px',
          fontFamily: 'Public Sans',
        },
      },
    },
    yaxis: { labels: { show: false } },
    tooltip: { theme: vuetifyTheme.name.value, y: { formatter: (val: number) => formatBytes(val, 1) } },
  }
})

const kuotaChartSeries = computed(() => stats.value?.kuotaPerHari ? [{ name: 'Kuota', data: stats.value.kuotaPerHari.slice(-7) }] : [])

const pendapatanBulanIniChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value.colors
  return {
    chart: { type: 'area', toolbar: { show: false }, sparkline: { enabled: true } },
    markers: { colors: 'transparent', strokeColors: 'transparent' },
    grid: { show: false },
    colors: [currentTheme.primary],
    fill: { type: 'gradient', gradient: { shadeIntensity: 0.8, opacityFrom: 0.6, opacityTo: 0.1 } },
    dataLabels: { enabled: false },
    stroke: { width: 2, curve: 'smooth' },
    xaxis: { type: 'datetime', labels: { show: false }, axisBorder: { show: false }, axisTicks: { show: false } },
    yaxis: { show: false },
    tooltip: { theme: vuetifyTheme.name.value, x: { format: 'dd MMMM<x_bin_615>' }, y: { formatter: (val: number) => formatCurrency(val) } },
  }
})

const pendapatanBulanIniChartSeries = computed(() => stats.value?.pendapatanPerHari ? [{ name: 'Pendapatan', data: stats.value.pendapatanPerHari }] : [])

const paketTerlarisChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value

  return {
    chart: { type: 'donut' },
    labels: stats.value?.paketTerlaris.map(p => p.name) ?? [],
    colors: [currentTheme.colors.primary, currentTheme.colors.success, currentTheme.colors.info, currentTheme.colors.warning, currentTheme.colors.secondary],
    stroke: { width: 0 },
    dataLabels: { enabled: true, formatter: (val: number, opts: any) => `${opts.w.globals.series[opts.seriesIndex]}x`, style: { fontSize: '12px', colors: [currentTheme.colors.surface], fontWeight: 'bold' }, dropShadow: { enabled: false } },
    legend: { position: 'bottom', markers: { offsetX: -3 }, itemMargin: { horizontal: 10 }, labels: { colors: textColor.value, useSeriesColors: false } },
    plotOptions: {
      pie: {
        donut: {
          size: '70%',
          labels: {
            show: true,
            value: {
              fontSize: '1.75rem',
              fontFamily: 'Public Sans',
              fontWeight: 600,
              color: textColor.value, // Warna untuk angka total (misal: 281)
              formatter: (val: string) => val,
            },
            name: {
              show: false,
            },
            total: {
              show: true,
              showAlways: true,
              label: 'Terjual',
              fontSize: '0.9rem',
              fontFamily: 'Public Sans',
              color: textColor.value, // Warna untuk label (misal: "Terjual")
              formatter: (w: any) => {
                const total = w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0)
                return `${total}`
              },
            },
          },
        },
      },
    },
    tooltip: { theme: vuetifyTheme.name.value, y: { formatter: (val: number) => `${val} penjualan` } },
  }
})

const paketTerlarisChartSeries = computed(() => stats.value?.paketTerlaris.map(p => p.count) ?? [])
</script>

<template>
  <div>
    <div v-if="pending && !isRefreshing">
      <DashboardSkeleton />
    </div>

    <div
      v-else-if="error"
      class="text-center pa-10"
    >
      <VIcon
        icon="tabler-alert-triangle"
        size="64"
        color="error"
      />
      <p class="text-h6 mt-4">
        Gagal Memuat Data Dashboard
      </p>
      <p class="text-body-1 mt-2 mb-6">
        Terjadi kesalahan saat mengambil data. Silakan coba lagi.
      </p>
      <pre
        v-if="error.data"
        class="error-pre"
      >{{ JSON.stringify(error.data, null, 2) }}</pre>
      <VBtn
        color="primary"
        class="mt-4"
        prepend-icon="tabler-reload"
        :loading="isRefreshing"
        @click="refresh"
      >
        Coba Lagi
      </VBtn>
    </div>

    <div v-else-if="stats">
      <StatsCard :statistics="statistics" />

      <VRow
        class="mb-4"
        match-height
      >
        <VCol
          cols="12"
          md="4"
        >
          <WeeklyRevenueCard
            :stats="stats"
            :perbandingan="perbandinganPendapatanMingguan"
          />
        </VCol>

        <VCol
          cols="12"
          md="4"
        >
          <ChartCard
            type="kuota"
            title="Kuota Terjual"
            subtitle="Laporan Mingguan"
            :value="formatBytes(stats.kuotaTerjual7HariMb)"
            :change="perbandinganKuota.persentase"
            :options="kuotaChartOptions"
            :series="kuotaChartSeries"
          />
        </VCol>

        <VCol
          cols="12"
          md="4"
        >
          <ChartCard
            type="pendapatan"
            title="Pendapatan Bulan Ini"
            :value="formatCurrency(stats.pendapatanBulanIni)"
            :options="pendapatanBulanIniChartOptions"
            :series="pendapatanBulanIniChartSeries"
          />
        </VCol>
      </VRow>

      <VRow>
        <VCol
          cols="12"
          md="5"
        >
          <BestSellingPackagesCard
            :options="paketTerlarisChartOptions"
            :series="paketTerlarisChartSeries"
          />
        </VCol>

        <VCol
          cols="12"
          md="7"
        >
          <ActivityTimeline
            :transactions="stats.transaksiTerakhir"
            :is-refreshing="isRefreshing"
            :on-refresh="refresh"
          />
        </VCol>
      </VRow>
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/libs/apex-chart.scss";

.error-pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  text-align: left;
  max-width: 600px;
  margin: 0 auto;
}
</style>
