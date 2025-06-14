<template>
  <div>
    <!-- Baris Atas: Statistik Ringkas -->
    <VRow class="mb-4">
      <!-- Kartu Menunggu Persetujuan -->
      <VCol
        cols="12"
        sm="6"
        lg="4"
      >
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <h6 class="text-h6">
                  Menunggu Persetujuan
                </h6>
                <span class="text-sm">Pengguna baru perlu ditinjau</span>
              </div>
              <VAvatar
                rounded
                variant="tonal"
                color="warning"
              >
                <VIcon icon="tabler-user-clock" />
              </VAvatar>
            </div>
            <h5 class="text-h5 font-weight-semibold my-2">
              {{ stats?.pendaftarBaru ?? 0 }} Pengguna
            </h5>
            <VProgressLinear
              :model-value="(stats?.pendaftarBaru ?? 0) > 0 ? 100 : 0"
              color="warning"
              height="8"
              rounded
            />
          </VCardText>
        </VCard>
      </VCol>

      <!-- Kartu Akan Kadaluwarsa -->
      <VCol
        cols="12"
        sm="6"
        lg="4"
      >
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <h6 class="text-h6">
                  Akan Kadaluwarsa
                </h6>
                <span class="text-sm">Masa aktif habis dalam 7 hari</span>
              </div>
              <VAvatar
                rounded
                variant="tonal"
                color="secondary"
              >
                <VIcon icon="tabler-calendar-exclamation" />
              </VAvatar>
            </div>
            <h5 class="text-h5 font-weight-semibold my-2">
              {{ stats?.akanKadaluwarsa ?? 0 }} Pengguna
            </h5>
            <VProgressLinear
              :model-value="((stats?.akanKadaluwarsa ?? 0) / (stats?.penggunaAktif || 1)) * 100"
              color="secondary"
              height="8"
              rounded
            />
          </VCardText>
        </VCard>
      </VCol>

      <!-- Kartu Pengguna Aktif -->
      <VCol
        cols="12"
        sm="12"
        lg="4"
      >
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <h6 class="text-h6">
                  Pengguna Aktif
                </h6>
                <span class="text-sm">Total pengguna terverifikasi</span>
              </div>
              <VAvatar
                rounded
                variant="tonal"
                color="primary"
              >
                <VIcon icon="tabler-users-group" />
              </VAvatar>
            </div>
            <h5 class="text-h5 font-weight-semibold my-2">
              {{ stats?.penggunaAktif ?? 0 }} Pengguna
            </h5>
            <VProgressLinear
              model-value="100"
              color="primary"
              height="8"
              rounded
            />
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- Baris Tengah: Grafik Pendapatan & Kuota -->
    <VRow class="mb-4">
      <!-- Kartu Pendapatan Hari Ini (Sales Overview Style) -->
      <VCol
        cols="12"
        md="4"
      >
        <VCard>
          <VCardItem>
            <VCardTitle>Pendapatan Hari Ini</VCardTitle>
            <template #append>
              <div class="me-n3">
                <MoreBtn />
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <p class="text-xs">
              Dibandingkan dengan kemarin
            </p>
            <div class="d-flex align-center justify-space-between">
              <div class="d-flex flex-column">
                <div class="d-flex align-center">
                  <h5 class="text-h5">
                    {{ formatCurrency(stats?.pendapatanHariIni) }}
                  </h5>
                  <VChip
                    :color="perbandinganPendapatan.persentase >= 0 ? 'success' : 'error'"
                    class="ms-2"
                    size="small"
                  >
                    <VIcon
                      :icon="perbandinganPendapatan.persentase >= 0 ? 'tabler-arrow-up' : 'tabler-arrow-down'"
                      size="18"
                      class="me-1"
                    />
                    {{ perbandinganPendapatan.persentase.toFixed(1) }}%
                  </VChip>
                </div>
                <span class="text-sm">
                  {{ stats?.transaksiHariIni ?? 0 }} transaksi sukses
                </span>
              </div>
              <VAvatar
                variant="tonal"
                rounded
                color="success"
                size="42"
              >
                <VIcon
                  icon="tabler-currency-dollar"
                  size="28"
                />
              </VAvatar>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Kartu Kuota Terjual (Bulan Ini) (Avg Daily Traffic Style) -->
      <VCol
        cols="12"
        md="4"
      >
        <VCard>
          <VCardItem>
            <VCardTitle>Kuota Terjual (7 Hari Terakhir)</VCardTitle>
          </VCardItem>
          <VCardText>
            <VRow>
              <VCol
                cols="12"
                sm="6"
              >
                <div class="d-flex align-center">
                  <VAvatar
                    color="info"
                    variant="tonal"
                    :size="42"
                    class="me-3"
                  >
                    <VIcon
                      icon="tabler-chart-line"
                      size="28"
                    />
                  </VAvatar>

                  <div>
                    <p class="mb-0">
                      Total Kuota
                    </p>
                    <h5 class="text-h5 font-weight-semibold">
                      {{ (stats?.kuotaTerjual7HariMb ?? 0) > 1024 ? ((stats?.kuotaTerjual7HariMb ?? 0) / 1024).toFixed(2) + ' GB' : (stats?.kuotaTerjual7HariMb ?? 0).toFixed(2) + ' MB' }}
                    </h5>
                  </div>
                </div>
              </VCol>
              <VCol
                cols="12"
                sm="6"
              >
                <ClientOnly>
                  <VueApexCharts
                    type="line"
                    height="80"
                    :options="kuotaChartOptions"
                    :series="kuotaChartSeries"
                  />
                  <template #fallback>
                    <div class="text-center pa-2">
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
      
      <!-- Kartu Pendapatan Bulan Ini (Average Daily Sales Style) -->
      <VCol
        cols="12"
        md="4"
      >
        <VCard>
          <VCardText>
            <h5 class="text-h5 mb-2">
              Pendapatan Bulan Ini
            </h5>
            <p class="mb-1">
              Total Penjualan Bulan {{ new Date().toLocaleString('id-ID', { month: 'long' }) }}
            </p>
            <h4 class="text-h4 font-weight-bold">
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
              <div class="text-center pa-2">
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
      <!-- Kartu Paket Terlaris (Bulan Ini) (Expense Ratio Chart Style) -->
      <VCol
        cols="12"
        md="5"
      >
        <VCard
          title="Paket Terlaris"
          subtitle="Berdasarkan jumlah penjualan bulan ini"
        >
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
                class="d-flex flex-column align-center justify-center"
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

      <!-- Kartu Aktivitas Transaksi Terakhir (Activity Timeline Style) -->
      <VCol
        cols="12"
        md="7"
      >
        <VCard>
          <VCardItem>
            <VCardTitle>Aktivitas Transaksi Terakhir</VCardTitle>
            <template #append>
              <VBtn
                variant="text"
                color="primary"
                @click="navigateTo('/admin/transactions')"
              >
                Lihat Semua
              </VBtn>
            </template>
          </VCardItem>
          
          <VDataTable
            :headers="transactionHeaders"
            :items="stats?.transaksiTerakhir ?? []"
            :loading="pending"
            :items-per-page="7"
            density="compact"
            class="text-no-wrap"
          >
            <template #item.user.full_name="{ item }">
              <div class="d-flex align-center py-2">
                <VAvatar
                  size="34"
                  :color="item.raw.user ? 'primary' : 'grey-lighten-1'"
                  class="me-3"
                  variant="tonal"
                >
                  <VIcon :icon="item.raw.user ? 'tabler-user' : 'tabler-user-off'" />
                </VAvatar>
                <div>
                  <div class="text-body-1 font-weight-medium">
                    {{ item.raw.user?.full_name ?? 'Pengguna Dihapus' }}
                  </div>
                  <div class="text-xs">
                    {{ item.raw.user?.username ?? 'N/A' }}
                  </div>
                </div>
              </div>
            </template>

            <template #item.package.name="{ item }">
              <VChip
                color="info"
                size="small"
                label
              >
                {{ item.raw.package.name }}
              </VChip>
            </template>

            <template #item.created_at="{ item }">
              <span class="text-sm text-disabled">{{ formatRelativeTime(item.raw.created_at) }}</span>
            </template>

            <template #item.amount="{ item }">
              <span class="font-weight-medium">{{ formatCurrency(item.raw.amount) }}</span>
            </template>

            <template #loading>
              <VSkeletonLoader type="table-row@7" />
            </template>

            <template #bottom />
          </VDataTable>
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
            <VAlert
              v-if="error"
              type="error"
              variant="tonal"
              class="mb-3"
            >
              Gagal memuat data statistik: {{ error.message }}
            </VVAlert>
            <pre
              v-if="!pending"
              style="white-space: pre-wrap; word-wrap: break-word; background-color: #282c34; color: #abb2bf; padding: 1rem; border-radius: 8px;"
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
  </div>
</template>

<script setup lang="ts">
import { useTheme } from 'vuetify'
import { useApiFetch } from '~/composables/useApiFetch'
import { VDataTable } from 'vuetify/labs/VDataTable' // Diperlukan untuk Vuetify 3
import { computed, defineAsyncComponent, h } from 'vue'

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    console.error(`Gagal memuat VueApexCharts`, err)
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
  }),
)

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

// --- Definisi Tipe untuk Data Dashboard ---
interface TransaksiTerakhir {
  id: string
  amount: number
  created_at: string
  package: { name: string }
  user: { full_name: string; username: string } | null
}

interface PaketTerlaris {
  name: string
  count: number
}

interface DashboardStats {
  pendapatanHariIni: number
  pendapatanBulanIni: number
  pendapatanKemarin: number // Data pembanding
  transaksiHariIni: number
  pendaftarBaru: number
  penggunaAktif: number
  akanKadaluwarsa: number
  kuotaTerjual7HariMb: number // Total kuota 7 hari
  kuotaPerHari: number[] // Array data kuota 7 hari terakhir
  pendapatanPerHari: number[] // Array data pendapatan 30 hari terakhir
  transaksiTerakhir: TransaksiTerakhir[]
  paketTerlaris: PaketTerlaris[]
}

// --- Fetch Data Statistik ---
const { data: stats, pending, error } = useApiFetch<DashboardStats>('/admin/dashboard/stats', {
  lazy: true,
  server: false,
})

const vuetifyTheme = useTheme()

// --- Konfigurasi Kartu & Tabel ---
const transactionHeaders = [
  { title: 'PENGGUNA', key: 'user.full_name', sortable: false, width: '40%' },
  { title: 'PAKET', key: 'package.name', sortable: false },
  { title: 'WAKTU', key: 'created_at', sortable: false, align: 'end' },
  { title: 'JUMLAH', key: 'amount', align: 'end', sortable: false },
]

// --- Logika Perbandingan Pendapatan ---
const perbandinganPendapatan = computed(() => {
  const hariIni = stats.value?.pendapatanHariIni ?? 0
  const kemarin = stats.value?.pendapatanKemarin ?? 0
  if (kemarin === 0) {
    return { persentase: hariIni > 0 ? 100 : 0 }
  }
  const selisih = hariIni - kemarin
  const persentase = (selisih / kemarin) * 100
  
  return { persentase: isFinite(persentase) ? persentase : 0 }
})

// --- Konfigurasi Grafik Kuota (Line Chart) ---
const kuotaChartOptions = computed(() => ({
  chart: {
    type: 'line',
    toolbar: { show: false },
    sparkline: { enabled: true },
  },
  grid: { show: false, padding: { left: 0, right: 0 } },
  colors: [vuetifyTheme.current.value.colors.info],
  stroke: { width: 2.5, curve: 'smooth' },
  xaxis: { categories: Array.from({ length: 7 }, (_, i) => `H-${6 - i}`) },
  tooltip: {
    enabled: true,
    theme: 'dark',
    custom: function ({ series, seriesIndex, dataPointIndex, w }: any) {
      return `<div class="px-2 py-1"><span>${series[seriesIndex][dataPointIndex]} MB</span></div>`
    },
  },
}))
const kuotaChartSeries = computed(() => [{
  name: 'Kuota',
  data: stats.value?.kuotaPerHari ?? Array(7).fill(0), // Gunakan data dari API atau array kosong
}])


// --- Konfigurasi Grafik Pendapatan Bulan Ini (Sparkline Area) ---
const pendapatanBulanIniChartOptions = computed(() => ({
  chart: {
    type: 'area',
    toolbar: { show: false },
    sparkline: { enabled: true },
  },
  markers: { colors: 'transparent', strokeColors: 'transparent' },
  grid: { show: false },
  colors: [vuetifyTheme.current.value.colors.success],
  fill: {
    type: 'gradient',
    gradient: { shadeIntensity: 0.8, opacityFrom: 0.6, opacityTo: 0.1 },
  },
  dataLabels: { enabled: false },
  stroke: { width: 2, curve: 'smooth' },
  xaxis: { show: false, lines: { show: false }, labels: { show: false }, axisBorder: { show: false } },
  yaxis: { show: false },
}))
const pendapatanBulanIniChartSeries = computed(() => [{
  name: 'Pendapatan',
  data: stats.value?.pendapatanPerHari ?? Array(30).fill(0), // Gunakan data API atau array kosong
}])


// --- Konfigurasi Grafik Paket Terlaris (Donut Chart) ---
const paketTerlarisChartOptions = computed(() => ({
  chart: { type: 'donut' },
  labels: stats.value?.paketTerlaris.map(p => p.name) ?? [],
  colors: [
    vuetifyTheme.current.value.colors.primary,
    vuetifyTheme.current.value.colors.success,
    vuetifyTheme.current.value.colors.info,
    vuetifyTheme.current.value.colors.warning,
    vuetifyTheme.current.value.colors.secondary,
  ],
  dataLabels: {
    enabled: true,
    formatter: (val: number, opts: any) => `${opts.w.config.series[opts.seriesIndex]}x`,
  },
  legend: {
    position: 'bottom',
    markers: { offsetX: -3 },
    itemMargin: { horizontal: 10 },
    labels: { colors: vuetifyTheme.current.value.colors.onSurface },
  },
  plotOptions: {
    pie: {
      donut: {
        labels: {
          show: true,
          name: { show: false },
          value: {
            show: true,
            fontSize: '1.5rem',
            fontWeight: '600',
            color: vuetifyTheme.current.value.colors.onBackground,
            formatter: (val: string) => `${val}x`,
          },
          total: {
            show: true,
            label: 'Total Terjual',
            fontSize: '0.9rem',
            color: vuetifyTheme.current.value.colors.onSurface,
            formatter: function (w: any) {
              return w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0) + 'x'
            },
          },
        },
      },
    },
  },
  responsive: [{
    breakpoint: 480,
    options: {
      chart: { width: 300 },
      legend: { position: 'bottom' },
    },
  }],
}))
const paketTerlarisChartSeries = computed(() => stats.value?.paketTerlaris.map(p => p.count) ?? [])

// --- Fungsi Helper ---
const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined) 
    return 'Rp 0'
  
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

const formatRelativeTime = (dateString: string): string => {
  const date = new Date(dateString)
  const now = new Date()
  const seconds = Math.round((now.getTime() - date.getTime()) / 1000)
  
  const minutes = Math.round(seconds / 60)
  const hours = Math.round(minutes / 60)
  const days = Math.round(hours / 24)

  if (seconds < 60)
    return `${seconds} detik lalu`
  if (minutes < 60)
    return `${minutes} menit lalu`
  if (hours < 24)
    return `${hours} jam lalu`
  
  return `${days} hari lalu`
}


useHead({ title: 'Dashboard Admin' })
</script>

<style lang="scss">
// Pastikan gaya apex-chart sudah diimpor secara global atau di sini
@use "@core/scss/template/libs/apex-chart.scss";

// Kustomisasi VDataTable
.v-data-table__wrapper {
  thead {
    th {
      background-color: transparent !important;
      font-weight: 600 !important;
      font-size: 0.8rem !important;
      color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity)) !important;
    }
  }

  tbody {
    tr:not(:last-child) {
      td {
        border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
      }
    }
  }
}

// Styling untuk pre tag
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