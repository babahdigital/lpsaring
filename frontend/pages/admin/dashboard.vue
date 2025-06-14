<template>
  <div>
    <!-- Baris Atas: Statistik Model Logistik -->
    <VRow class="mb-4">
      <VCol
        v-for="(data, index) in statistics"
        :key="index"
        cols="12"
        md="3"
        sm="6"
      >
        <VCard
          class="logistics-card-statistics cursor-pointer"
          :style="data.isHover ? `border-block-end-color: rgb(var(--v-theme-${data.color}))` : `border-block-end-color: rgba(var(--v-theme-${data.color}),0.38)`"
          @mouseenter="data.isHover = true"
          @mouseleave="data.isHover = false"
        >
          <VCardText>
            <div class="d-flex align-center gap-x-4 mb-1">
              <VAvatar
                variant="tonal"
                :color="data.color"
                rounded
              >
                <VIcon
                  :icon="data.icon"
                  size="28"
                />
              </VAvatar>
              <h4 class="text-h4">
                {{ data.value }}
              </h4>
            </div>
            <div class="text-body-1 mb-1">
              {{ data.title }}
            </div>
            <div class="d-flex gap-x-2 align-center">
              <h6
                class="text-h6"
                :class="data.change >= 0 ? 'text-success' : 'text-error'"
              >
                {{ (data.change > 0) ? '+' : '' }}{{ data.change.toFixed(1) }}%
              </h6>
              <div class="text-disabled">
                dari kemarin
              </div>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- Baris Tengah: Grafik Pendapatan & Kuota -->
    <VRow
      class="mb-4"
      match-height
    >
      <!-- Kartu Pendapatan Hari Ini (Sales Overview Style) -->
      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100">
          <VCardText>
            <div class="d-flex align-center justify-space-between">
              <div class="text-body-1">
                Pendapatan Hari Ini
              </div>
              <div
                class="font-weight-medium"
                :class="perbandinganPendapatan.persentase >= 0 ? 'text-success' : 'text-error'"
              >
                <span v-if="stats?.pendapatanKemarin === 0 && stats?.pendapatanHariIni > 0">BARU</span>
                <span v-else>{{ perbandinganPendapatan.persentase >= 0 ? '+' : '' }}{{ perbandinganPendapatan.persentase.toFixed(1) }}%</span>
              </div>
            </div>
            <h4 class="text-h4 my-2">
              {{ formatCurrency(stats?.pendapatanHariIni) }}
            </h4>
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
                      icon="tabler-shopping-cart"
                    />
                  </VAvatar>
                  <span>Transaksi</span>
                </div>
                <h5 class="text-h5">
                  {{ stats?.transaksiHariIni ?? stats?.transaksiTerakhir.length ?? 0 }}
                </h5>
                <div class="text-body-2 text-disabled">
                  Sukses
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
                  <span class="me-2">Kemarin</span>
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
                  {{ formatCurrency(stats?.pendapatanKemarin) }}
                </h5>
                <div class="text-body-2 text-disabled">
                  Pendapatan
                </div>
              </VCol>
            </VRow>
            <div class="mt-6">
              <VProgressLinear
                :model-value="(stats?.pendapatanHariIni ?? 0) / ((stats?.pendapatanHariIni ?? 0) + (stats?.pendapatanKemarin ?? 1)) * 100"
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

      <!-- Kartu Kuota Terjual (7 Hari) -->
      <VCol
        cols="12"
        md="4"
      >
        <VCard class="h-100">
          <VCardText class="d-flex justify-space-between">
            <div class="d-flex flex-column">
              <div class="mb-auto">
                <h5 class="text-h5 text-no-wrap mb-2">
                  Kuota Terjual
                </h5>
                <div class="text-body-1">
                  Laporan Mingguan
                </div>
              </div>
              <div>
                <h5 class="text-h3 mb-2">
                  {{ formatBytes(stats?.kuotaTerjualMb) }}
                </h5>
                <VChip
                  label
                  :color="perbandinganKuota.persentase >= 0 ? 'success' : 'error'"
                  size="small"
                >
                  {{ perbandinganKuota.persentase >= 0 ? '+' : '' }}{{ perbandinganKuota.persentase.toFixed(1) }}%
                </VChip>
              </div>
            </div>
            <div style="min-width: 120px;">
              <ClientOnly>
                <VueApexCharts
                  :options="kuotaChartOptions"
                  :series="kuotaChartSeries"
                  :height="162"
                />
                <template #fallback>
                  <div
                    class="d-flex align-center justify-center"
                    style="height: 162px;"
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
      
      <!-- Kartu Pendapatan Bulan Ini -->
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
              Total Penjualan Bulan {{ new Date().toLocaleString('id-ID', { month: 'long' }) }}
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

    <!-- Baris Bawah: Paket & Aktivitas -->
    <VRow>
      <!-- Kartu Paket Terlaris (Bulan Ini) -->
      <VCol
        cols="12"
        md="5"
      >
        <VCard>
          <VCardItem>
            <VCardTitle>Paket Terlaris</VCardTitle>
            <VCardSubtitle>Berdasarkan jumlah penjualan bulan ini</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <ClientOnly>
              <VueApexCharts
                v-if="!pending && paketTerlarisChartSeries.length > 0 && paketTerlarisChartSeries.some(s => s > 0)"
                type="donut"
                height="350"
                :options="paketTerlarisChartOptions"
                :series="paketTerlarisChartSeries"
              />
              <div
                v-else-if="!pending"
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

      <!-- Kartu Aktivitas Transaksi Terakhir -->
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
                  @click="refresh"
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
              <!-- Item Timeline -->
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
                  <span class="app-timeline-meta">{{ formatTime(transaksi.created_at) }}</span>
                </div>
                <div class="app-timeline-text mt-1 mb-3">
                  Transaksi sebesar {{ formatCurrency(transaksi.amount) }} telah berhasil.
                </div>

                <!-- Info Pengguna -->
                <div class="d-flex justify-space-between align-center flex-wrap">
                  <div class="d-flex align-center">
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
              v-else-if="!pending"
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
    
    <!-- Kartu Debugging API -->
    <VRow class="mt-4">
      <VCol cols="12">
        <VCard>
          <VCardItem>
            <VCardTitle>Respons API (Untuk Debug)</VCardTitle>
            <VCardSubtitle>Gunakan ini untuk memeriksa data mentah yang diterima dari server.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <v-alert
              v-if="error"
              type="error"
              variant="tonal"
              class="mb-3"
            >
              Gagal memuat data statistik: {{ error.message }}
            </v-alert>
            <pre
              v-if="!pending"
            >{{ JSON.stringify(stats, null, 2) }}</pre>
            <div
              v-else
              class="text-center"
            >
              <VProgressCircular
                indeterminate
                color="primary"
              />
              <p class="mt-2 text-disabled">
                Memuat data dari API...
              </p>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- Snackbar untuk Notifikasi -->
    <VSnackbar
      v-model="snackbar.visible"
      :color="snackbar.color"
      :timeout="3000"
      location="top right"
      variant="tonal"
    >
      <div class="d-flex align-center">
        <VIcon
          :icon="snackbar.icon"
          class="me-3"
        />
        <span>{{ snackbar.text }}</span>
      </div>
    </VSnackbar>
  </div>
</template>

<script setup lang="ts">
import { useTheme } from 'vuetify'
import { useApiFetch } from '~/composables/useApiFetch'
import { computed, defineAsyncComponent, h, ref, watch } from 'vue'
import { hexToRgb } from '@layouts/utils'

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    console.error(`Gagal memuat VueApexCharts`, err)
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
  }),
)

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

// --- Tipe Data ---
interface TransaksiTerakhir {
  id: string
  amount: number
  created_at?: string
  package: { name: string }
  user: { full_name: string; username: string, phone_number?: string } | null
}

interface PaketTerlaris {
  name: string
  count: number
}

interface DashboardStats {
  pendapatanHariIni: number
  pendapatanBulanIni: number
  pendapatanKemarin?: number
  transaksiHariIni?: number
  pendaftarBaru: number
  penggunaAktif: number
  penggunaOnline?: number
  akanKadaluwarsa: number
  kuotaTerjualMb?: number
  kuotaTerjual7HariMb?: number
  kuotaTerjualKemarinMb?: number
  kuotaPerHari?: number[]
  pendapatanPerHari?: number[]
  transaksiTerakhir: TransaksiTerakhir[]
  paketTerlaris: PaketTerlaris[]
}

// --- State & Fetching ---
const snackbar = ref({
  visible: false,
  text: '',
  color: 'success',
  icon: 'tabler-check',
})

const { data: stats, pending, error, refresh } = useApiFetch<DashboardStats>('/admin/dashboard/stats', {
  lazy: true,
  server: false,
  default: () => ({
    pendapatanHariIni: 0,
    pendapatanBulanIni: 0,
    pendaftarBaru: 0,
    penggunaAktif: 0,
    akanKadaluwarsa: 0,
    kuotaTerjualMb: 0,
    transaksiTerakhir: [],
    paketTerlaris: [],
    kuotaPerHari: [],
  }),
})

const vuetifyTheme = useTheme()

// --- Data untuk Kartu Statistik Atas ---
const statistics = ref([
  { icon: 'tabler-user-search', color: 'warning', title: 'Menunggu Persetujuan', value: 0, change: 0, isHover: false },
  { icon: 'tabler-calendar-exclamation', color: 'secondary', title: 'Akan Kadaluwarsa', value: 0, change: 0, isHover: false },
  { icon: 'tabler-users-group', color: 'primary', title: 'Pengguna Aktif', value: 0, change: 0, isHover: false },
  { icon: 'tabler-wifi', color: 'success', title: 'Pengguna Online', value: 0, change: 0, isHover: false },
])

watch(stats, (newStats) => {
  if (newStats) {
    statistics.value[0].value = newStats.pendaftarBaru ?? 0
    statistics.value[1].value = newStats.akanKadaluwarsa ?? 0
    statistics.value[2].value = newStats.penggunaAktif ?? 0
    statistics.value[3].value = newStats.penggunaOnline ?? 0
  }
})

// --- Logika Perbandingan ---
const perbandinganPendapatan = computed(() => {
  const hariIni = stats.value?.pendapatanHariIni ?? 0
  const kemarin = stats.value?.pendapatanKemarin ?? 0
  if (kemarin === 0) return { persentase: hariIni > 0 ? 100 : 0 }
  const selisih = hariIni - kemarin
  const persentase = (selisih / kemarin) * 100
  return { persentase: isFinite(persentase) ? persentase : 0 }
})

const perbandinganKuota = computed(() => {
    const totalMingguIni = stats.value?.kuotaTerjual7HariMb ?? stats.value?.kuotaTerjualMb ?? 0
    const totalMingguLalu = stats.value?.kuotaTerjualKemarinMb ?? 0
    if (totalMingguLalu === 0) return { persentase: totalMingguIni > 0 ? 100 : 0 }
    const selisih = totalMingguIni - totalMingguLalu
    const persentase = (selisih / totalMingguLalu) * 100
    return { persentase: isFinite(persentase) ? persentase : 0 }
});

// --- Konfigurasi Grafik ---
const kuotaChartOptions = computed(() => {
  const currentTheme = vuetifyTheme.current.value.colors
  const variableTheme = vuetifyTheme.current.value.variables
  const labelColor = `rgba(${hexToRgb(currentTheme['on-surface'])},${variableTheme['disabled-opacity']})`
  const labelSuccessColor = `rgba(${hexToRgb(currentTheme.success)},0.2)`

  return {
    chart: { type: 'bar', height: 162, parentHeightOffset: 0, toolbar: { show: false } },
    plotOptions: {
      bar: { barHeight: '80%', columnWidth: '30%', startingShape: 'rounded', endingShape: 'rounded', borderRadius: 6, distributed: true },
    },
    grid: { show: false, padding: { top: -20, bottom: -12, left: -10, right: 0 } },
    colors: [
      labelSuccessColor, labelSuccessColor, labelSuccessColor, labelSuccessColor, currentTheme.success, labelSuccessColor, labelSuccessColor,
    ],
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: ['S', 'S', 'R', 'K', 'J', 'S', 'M'],
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { style: { colors: labelColor, fontSize: '13px', fontFamily: 'Public sans' } },
    },
    yaxis: { labels: { show: false } },
    states: { hover: { filter: { type: 'none' } } },
    tooltip: { // Tooltip diaktifkan di sini
      enabled: true,
      theme: 'dark',
      x: { show: false },
      y: {
        formatter: (val: number) => `${formatBytes(val)}`,
        title: { formatter: (seriesName: string, opts: any) => `Hari ke-${opts.dataPointIndex + 1}` },
      },
      marker: { show: false },
    },
  }
})

const kuotaChartSeries = computed(() => [{
  name: 'Kuota',
  data: stats.value?.kuotaPerHari ?? [1024, 2048, 1536, 3072, 4096, 2560, 1024], // Menggunakan data dummy jika API belum siap
}])

const pendapatanBulanIniChartOptions = computed(() => ({
  chart: { type: 'area', toolbar: { show: false }, sparkline: { enabled: true } },
  markers: { colors: 'transparent', strokeColors: 'transparent' },
  grid: { show: false },
  colors: [vuetifyTheme.current.value.colors.primary],
  fill: { type: 'gradient', gradient: { shadeIntensity: 0.8, opacityFrom: 0.6, opacityTo: 0.1 } },
  dataLabels: { enabled: false },
  stroke: { width: 2, curve: 'smooth' },
  xaxis: { show: false, lines: { show: false }, labels: { show: false }, axisBorder: { show: false } },
  yaxis: { show: false },
}))
const pendapatanBulanIniChartSeries = computed(() => [{
  name: 'Pendapatan',
  data: stats.value?.pendapatanPerHari ?? Array(30).fill(0).map((_, i) => Math.random() * 100000 * (i/10)), // Data dummy jika API belum siap
}])

const paketTerlarisChartOptions = computed(() => {
    const currentTheme = vuetifyTheme.current.value
    return {
        chart: { type: 'donut' },
        labels: stats.value?.paketTerlaris.map(p => p.name) ?? [],
        colors: [
            currentTheme.colors.primary, currentTheme.colors.success, currentTheme.colors.info, currentTheme.colors.warning, currentTheme.colors.secondary,
        ],
        stroke: { width: 5, colors: [currentTheme.colors.surface] },
        dataLabels: { enabled: false },
        legend: {
            position: 'bottom',
            markers: { offsetX: -3 },
            itemMargin: { horizontal: 10 },
            labels: { colors: currentTheme.colors.onSurface, useSeriesColors: false },
        },
        plotOptions: {
            pie: {
                donut: {
                    size: '75%',
                    labels: {
                        show: true,
                        value: { fontSize: '1.625rem', fontFamily: 'Public Sans', color: currentTheme.colors.onBackground, fontWeight: 600, offsetY: -15, formatter: (val: string) => `${val}x` },
                        name: { fontSize: '0.9rem', fontFamily: 'Public Sans', color: currentTheme.colors.onSurface, offsetY: 20 },
                        total: { show: true, showAlways: true, label: 'Total', color: currentTheme.colors.onSurface, formatter: (w: any) => w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0) + 'x' },
                    },
                },
            },
        },
    }
})
const paketTerlarisChartSeries = computed(() => stats.value?.paketTerlaris.map(p => p.count) ?? [])

// --- Fungsi Helper ---
const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return 'Rp 0'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

const formatBytes = (bytesInMb: number | null | undefined, decimals = 2) => {
    if (bytesInMb === null || bytesInMb === undefined || bytesInMb === 0) return '0 MB';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['MB', 'GB', 'TB'];
    let i = 0;
    let size = bytesInMb;
    while(size >= k && i < sizes.length -1) {
        size /= k;
        i++;
    }
    return `${parseFloat(size.toFixed(dm))} ${sizes[i]}`;
}

const formatTime = (dateString?: string): string => {
  if (!dateString) return '';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('id-ID', { hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}

const formatPhoneNumberForDisplay = (phoneNumber?: string | null) => {
  if (!phoneNumber) return 'No. Telp tidak ada';
  if (phoneNumber.startsWith('+62')) return '0' + phoneNumber.substring(3);
  return phoneNumber;
};

const getUserInitials = (name?: string) => {
  if (!name || name.trim() === '') return 'N/A'
  const words = name.split(' ').filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1 && words[0].length > 1) return (words[0][0] + words[0][1]).toUpperCase()
  return name.substring(0, 1).toUpperCase()
}

useHead({ title: 'Dashboard Admin' })
</script>

<style lang="scss">
@use "@core/scss/template/libs/apex-chart.scss";
@use "@core/scss/base/mixins" as mixins;

.logistics-card-statistics {
  border-block-end-style: solid;
  border-block-end-width: 2px;
  &:hover {
    border-block-end-width: 3px;
    margin-block-end: -1px;
    @include mixins.elevation(8);
    transition: all 0.1s ease-out;
  }
}

.skin--bordered {
  .logistics-card-statistics {
    border-block-end-width: 2px;
    &:hover {
      border-block-end-width: 3px;
      margin-block-end: -2px;
      transition: all 0.1s ease-out;
    }
  }
}

pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.theme--dark pre {
  background-color: #282c34;
  color: #abb2bf;
  border-color: rgba(255, 255, 255, 0.12);
}
</style>