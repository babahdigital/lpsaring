// /composables/useDashboard.ts

import { useNuxtApp } from 'nuxt/app'
import { computed, nextTick, onMounted, ref, watchEffect } from 'vue'
import { useTheme } from 'vuetify'

import type { DashboardStats, PendapatanHarian } from '~/types/dashboard'

import { useDashboardUtils } from '~/composables/useDashboardUtils'
import { useAuthStore } from '~/store/auth'

function safeHexToRgb(hex: string): string {
  if (!hex)
    return '0,0,0'

  hex = hex.replace('#', '')

  if (hex.length === 3) {
    hex = hex[0]! + hex[0]! + hex[1]! + hex[1]! + hex[2]! + hex[2]!
  }

  const r = Number.parseInt(hex.substring(0, 2), 16)
  const g = Number.parseInt(hex.substring(2, 4), 16)
  const b = Number.parseInt(hex.substring(4, 6), 16)

  return `${r},${g},${b}`
}

function getOpacity(value: string | number | undefined, fallback: number): number {
  if (value === undefined || value === null)
    return fallback
  if (typeof value === 'number')
    return value

  const num = Number.parseFloat(value)
  return isNaN(num) ? fallback : num
}

export function useDashboard(useDummyData: globalThis.Ref<boolean>) {
  const authStore = useAuthStore()
  const { $api } = useNuxtApp()
  const vuetifyTheme = useTheme()
  const { formatBytes, formatCurrency } = useDashboardUtils()

  const stats = ref<DashboardStats | null>(null)
  const pending = ref(true)
  const error = ref<any>(null)
  const isRefreshing = ref(false)

  function setupDummyData() {
    console.log('[DASHBOARD] Menggunakan data dummy sinkron.')

    const kuota14Hari = Array.from({ length: 14 }, () => Math.floor(Math.random() * (300000 - 100000 + 1) + 100000))
    const totalKuota7Hari = kuota14Hari.slice(-7).reduce((a, b) => a + b, 0)

    const pendapatan30Hari: PendapatanHarian[] = Array.from({ length: 30 }, (_, i) => {
      const date = new Date()
      date.setDate(date.getDate() - (29 - i))
      return {
        x: date.toISOString().split('T')[0]!,
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

    nextTick(() => {
      pending.value = false
      isRefreshing.value = false
    })
  }

  async function fetchData() {
    error.value = null
    console.log('[DASHBOARD] Mengambil data dari API...')
    try {
      const response = await $api<DashboardStats>('/admin/dashboard/stats')
      stats.value = response
    }
    catch (e) {
      error.value = e
      console.error('Gagal mengambil statistik dashboard:', e)
    }
    finally {
      pending.value = false
      isRefreshing.value = false
    }
  }

  const refresh = () => {
    isRefreshing.value = true
    if (useDummyData.value) {
      setupDummyData()
    }
    else {
      fetchData()
    }
  }

  onMounted(() => {
    pending.value = true
    if (useDummyData.value) {
      setupDummyData()
    }
    else {
      watchEffect(() => {
        if (authStore.isAuthCheckDone && authStore.isLoggedIn) {
          fetchData()
        }
        else if (authStore.isAuthCheckDone && !authStore.isLoggedIn) {
          pending.value = false
        }
      })
    }
  })

  const statistics = computed(() => {
    if (stats.value == null)
      return []
    return [
      { icon: 'tabler-user-search', color: 'warning', title: 'Menunggu Persetujuan', value: stats.value.pendaftarBaru, change: 0.0 },
      { icon: 'tabler-calendar-exclamation', color: 'secondary', title: 'Akan Kadaluwarsa', value: stats.value.akanKadaluwarsa, change: 0.0 },
      { icon: 'tabler-users-group', color: 'primary', title: 'Pengguna Aktif', value: stats.value.penggunaAktif, change: 0.0 },
      { icon: 'tabler-wifi', color: 'success', title: 'Pengguna Online', value: stats.value.penggunaOnline, change: 0.0 },
    ]
  })

  const perbandinganPendapatanMingguan = computed(() => {
    if (stats.value == null)
      return { persentase: 0 }
    const { pendapatanMingguIni, pendapatanMingguLalu } = stats.value
    if (pendapatanMingguLalu === 0)
      return { persentase: pendapatanMingguIni > 0 ? 100 : 0 }
    const selisih = pendapatanMingguIni - pendapatanMingguLalu
    const persentase = (selisih / pendapatanMingguLalu) * 100
    return { persentase: isFinite(persentase) ? persentase : 0 }
  })

  const perbandinganKuota = computed(() => {
    if (stats.value == null || stats.value.kuotaPerHari == null || stats.value.kuotaPerHari.length < 14) {
      return { persentase: 0 }
    }

    const dataTerbaru = stats.value.kuotaPerHari
    const totalMingguIni = dataTerbaru.slice(-7).reduce((sum, val) => sum + val, 0)
    const totalMingguLalu = dataTerbaru.slice(-14, -7).reduce((sum, val) => sum + val, 0)

    if (totalMingguLalu === 0) {
      return { persentase: totalMingguIni > 0 ? 100 : 0 }
    }

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

  const kuotaChartOptions = computed(() => {
    const t = vuetifyTheme.current.value
    if (stats.value == null || t.colors.primary == null || t.colors.onSurface == null) {
      return {}
    }

    const barBaseRgb = safeHexToRgb(t.colors.primary)
    const dimOpacity = getOpacity(t.variables?.['dragged-opacity'], 0.28)

    const labelColor = `rgba(${safeHexToRgb(t.colors.onSurface)}, ${getOpacity(t.variables?.['medium-emphasis-opacity'], 0.64)})`

    return {
      chart: { type: 'bar', parentHeightOffset: 0, toolbar: { show: false } },
      plotOptions: { bar: { columnWidth: '38%', borderRadius: 4, distributed: true } },
      grid: { show: false, padding: { top: -30, bottom: 0, left: -10, right: -10 } },
      colors: lastSevenDaysLabels.value.map((_, i) =>
        `rgba(${barBaseRgb}, ${i === 6 ? 1 : dimOpacity})`,
      ),
      dataLabels: { enabled: false },
      legend: { show: false },
      xaxis: {
        categories: lastSevenDaysLabels.value,
        axisBorder: { show: false },
        axisTicks: { show: false },
        labels: { style: { colors: labelColor, fontSize: '13px', fontFamily: 'Public Sans' } },
      },
      yaxis: { labels: { show: false } },
      tooltip: { theme: vuetifyTheme.name.value, y: { formatter: (val: number) => formatBytes(val, 1) } },
    }
  })

  const kuotaChartSeries = computed(() => {
    if (stats.value?.kuotaPerHari == null)
      return []
    return [{ name: 'Kuota', data: stats.value.kuotaPerHari.slice(-7) }]
  })

  const pendapatanBulanIniChartOptions = computed(() => {
    const currentTheme = vuetifyTheme.current.value
    if (stats.value == null || currentTheme.colors.primary == null) {
      return {}
    }

    return {
      chart: { type: 'area', toolbar: { show: false }, sparkline: { enabled: true } },
      markers: { colors: 'transparent', strokeColors: 'transparent' },
      grid: { show: false },
      colors: [currentTheme.colors.primary],
      fill: { type: 'gradient', gradient: { shadeIntensity: 0.8, opacityFrom: 0.6, opacityTo: 0.1 } },
      dataLabels: { enabled: false },
      stroke: { width: 2, curve: 'smooth' },
      xaxis: { type: 'datetime', labels: { show: false }, axisBorder: { show: false }, axisTicks: { show: false } },
      yaxis: { show: false },
      tooltip: { theme: vuetifyTheme.name.value, x: { format: 'dd MMMM yyyy' }, y: { formatter: (val: number) => formatCurrency(val) } },
    }
  })

  const pendapatanBulanIniChartSeries = computed(() => (stats.value?.pendapatanPerHari ? [{ name: 'Pendapatan', data: stats.value.pendapatanPerHari }] : []))

  const paketTerlarisChartOptions = computed(() => {
    const t = vuetifyTheme.current.value
    if (stats.value == null || stats.value.paketTerlaris == null || stats.value.paketTerlaris.length === 0 || t.colors.primary == null || t.colors.onSurface == null) {
      return {}
    }

    const onSurfaceRgb = safeHexToRgb(t.colors.onSurface)
    const highColor = `rgba(${onSurfaceRgb}, ${getOpacity(t.variables?.['high-emphasis-opacity'], 0.87)})`
    const medColor = `rgba(${onSurfaceRgb}, ${getOpacity(t.variables?.['medium-emphasis-opacity'], 0.60)})`

    return {
      chart: { type: 'donut' },
      labels: stats.value.paketTerlaris.map(p => p.name),
      colors: [t.colors.primary, t.colors.success, t.colors.info, t.colors.warning, t.colors.secondary],
      stroke: { width: 0 },
      dataLabels: {
        enabled: true,
        formatter: (val: number, opts: any) => `${opts.w.globals.series[opts.seriesIndex]}x`,
        style: { fontSize: '12px', colors: [t.colors.surface], fontWeight: 'bold' },
        dropShadow: { enabled: false },
      },
      legend: { position: 'bottom', markers: { offsetX: -3 }, itemMargin: { horizontal: 10 }, labels: { colors: highColor, useSeriesColors: false } },
      plotOptions: {
        pie: {
          donut: {
            size: '70%',
            labels: {
              show: true,
              value: { fontSize: '1.625rem', fontFamily: 'Public Sans', color: highColor, fontWeight: 600, offsetY: -15, formatter: (val: string) => `${val}x` },
              name: { fontSize: '0.9rem', fontFamily: 'Public Sans', color: medColor, offsetY: 20 },
              total: {
                show: true,
                showAlways: true,
                label: 'Terjual',
                color: medColor,
                formatter: (w: any) => `${w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0)}x`,
              },
            },
          },
        },
      },
      tooltip: { theme: vuetifyTheme.name.value, y: { formatter: (val: number) => `${val} penjualan` } },
    }
  })

  const paketTerlarisChartSeries = computed(() => (stats.value?.paketTerlaris ? stats.value.paketTerlaris.map(p => p.count) : []))

  return {
    stats,
    pending,
    error,
    isRefreshing,
    refresh,
    statistics,
    perbandinganPendapatanMingguan,
    perbandinganKuota,
    kuotaChartOptions,
    kuotaChartSeries,
    pendapatanBulanIniChartOptions,
    pendapatanBulanIniChartSeries,
    paketTerlarisChartOptions,
    paketTerlarisChartSeries,
  }
}
