<template>
  <div>
    <!-- Baris 1: Ringkasan Keuangan & Data + Statistik KPI Utama Lainnya -->
    <VRow>
      <!-- Ringkasan Keuangan & Data (Gabungan) -->
      <VCol
        cols="12"
        md="6"
      >
        <VCard>
          <VCardItem class="pb-2">
            <VCardTitle>Ringkasan Keuangan & Data</VCardTitle>
            <template #append>
              <div class="me-n3">
                <IconBtn>
                  <VIcon icon="tabler-dots-vertical" />
                </IconBtn>
              </div>
            </template>
          </VCardItem>

          <VCardText>
            <!-- Pendapatan Hari Ini -->
            <div class="d-flex justify-space-between align-center mb-2">
              <h6 class="text-h6">
                Pendapatan Hari Ini
              </h6>
              <VChip
                label
                color="success"
                size="small"
              >
                {{ formatCurrency(stats?.pendapatanHariIni) }}
              </VChip>
            </div>
            <div class="text-base mb-1">
              Total transaksi sukses hari ini
            </div>
            <!-- Daily Revenue Chart (Last 7 Days) -->
            <ClientOnly>
              <VueApexCharts
                type="line"
                height="100"
                :options="dailyRevenueChartOptions"
                :series="dailyRevenueChartSeries"
              />
            </ClientOnly>

            <VDivider class="my-6" />

            <!-- Pendapatan Bulan Ini -->
            <div class="d-flex justify-space-between align-center mb-2">
              <h6 class="text-h6">
                Pendapatan Bulan Ini
              </h6>
              <VChip
                label
                color="success"
                size="small"
              >
                {{ formatCurrency(stats?.pendapatanBulanIni) }}
              </VChip>
            </div>
            <div class="text-base mb-1">
              Total transaksi sukses bulan ini
            </div>
             <!-- Monthly Revenue Chart (Last 12 Months) -->
             <ClientOnly>
              <VueApexCharts
                type="bar"
                height="100"
                :options="monthlyRevenueChartOptions"
                :series="monthlyRevenueChartSeries"
              />
            </ClientOnly>

            <VDivider class="my-6" />

            <!-- Kuota Terjual Bulan Ini -->
            <div class="d-flex justify-space-between align-center mb-2">
              <h6 class="text-h6">
                Kuota Terjual (Bulan Ini)
              </h6>
              <VChip
                label
                color="info"
                size="small"
              >
                {{ stats?.kuotaTerjualMb ? (stats.kuotaTerjualMb / 1024).toFixed(2) : '0.00' }} GB
              </VChip>
            </div>
            <div class="text-base mb-1">
              Total kuota dari paket terjual
            </div>
            <VProgressLinear
              :model-value="percentageKuotaTerjual"
              color="info"
              height="8"
              rounded
            />
          </VCardText>
        </VCard>
      </VCol>

      <!-- KPI Utama lainnya yang tetap terpisah -->
      <VCol
        cols="12"
        md="6"
      >
        <VRow>
          <!-- Pendaftar Menunggu Persetujuan (Actionable) -->
          <VCol cols="12" sm="6">
            <VCard
              class="logistics-card-statistics cursor-pointer"
              :style="isHoverPendaftarMenunggu ? `border-block-end-color: rgb(var(--v-theme-warning))` : `border-block-end-color: rgba(var(--v-theme-warning),0.38)`"
              @mouseenter="isHoverPendaftarMenunggu = true"
              @mouseleave="isHoverPendaftarMenunggu = false"
            >
              <VCardText>
                <div class="d-flex align-center gap-x-4 mb-1">
                  <VAvatar
                    variant="tonal"
                    color="warning"
                    rounded
                  >
                    <VIcon
                      icon="mdi-account-clock-outline"
                      size="28"
                    />
                  </VAvatar>
                  <h4 class="text-h4">
                    {{ stats?.pendaftarBaru ?? 0 }}
                  </h4>
                </div>
                <div class="text-body-1 mb-1">
                  Menunggu Persetujuan
                </div>
                <div class="text-sm text-warning">
                  Perlu tindakan Anda
                </div>
              </VCardText>
            </VCard>
          </VCol>

          <!-- Total Pengguna Aktif -->
          <VCol cols="12" sm="6">
            <VCard
              class="logistics-card-statistics cursor-pointer"
              :style="isHoverPenggunaAktif ? `border-block-end-color: rgb(var(--v-theme-primary))` : `border-block-end-color: rgba(var(--v-theme-primary),0.38)`"
              @mouseenter="isHoverPenggunaAktif = true"
              @mouseleave="isHoverPenggunaAktif = false"
            >
              <VCardText>
                <div class="d-flex align-center gap-x-4 mb-1">
                  <VAvatar
                    variant="tonal"
                    color="primary"
                    rounded
                  >
                    <VIcon
                      icon="mdi-account-group-outline"
                      size="28"
                    />
                  </VAvatar>
                  <h4 class="text-h4">
                    {{ stats?.penggunaAktif ?? 0 }}
                  </h4>
                </div>
                <div class="text-body-1 mb-1">
                  Pengguna Aktif
                </div>
                <div class="text-disabled text-sm">
                  Total pengguna terdaftar & disetujui
                </div>
              </VCardText>
            </VCard>
          </VCol>

          <!-- Pengguna Akan Kadaluwarsa (Proaktif) -->
          <VCol cols="12" sm="6">
            <VCard
              class="logistics-card-statistics cursor-pointer"
              :style="isHoverAkanKadaluwarsa ? `border-block-end-color: rgb(var(--v-theme-secondary))` : `border-block-end-color: rgba(var(--v-theme-secondary),0.38)`"
              @mouseenter="isHoverAkanKadaluwarsa = true"
              @mouseleave="isHoverAkanKadaluwarsa = false"
            >
              <VCardText>
                <div class="d-flex align-center gap-x-4 mb-1">
                  <VAvatar
                    variant="tonal"
                    color="secondary"
                    rounded
                  >
                    <VIcon
                      icon="mdi-account-reactivate-outline"
                      size="28"
                    />
                  </VAvatar>
                  <h4 class="text-h4">
                    {{ stats?.akanKadaluwarsa ?? 0 }}
                  </h4>
                </div>
                <div class="text-body-1 mb-1">
                  Akan Kadaluwarsa
                </div>
                <div class="text-disabled text-sm">
                  Masa aktif akan habis dalam 7 hari
                </div>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VCol>
    </VRow>

    <!-- Baris 2: Grafik & Tabel -->
    <VRow class="mt-4">
      <!-- Grafik Paket Terlaris -->
      <VCol
        cols="12"
        md="5"
      >
        <VCard>
          <VCardItem class="pb-2">
            <VCardTitle>Paket Terlaris (Bulan Ini)</VCardTitle>
            <template #append>
              <div class="me-n3">
                <IconBtn>
                  <VIcon icon="tabler-dots-vertical" />
                </IconBtn>
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <ClientOnly>
              <VueApexCharts
                v-if="!pending && pieChartSeries.length > 0"
                type="pie"
                height="350"
                :options="pieChartOptions"
                :series="pieChartSeries"
              />
              <div
                v-else-if="!pending && pieChartSeries.length === 0"
                class="text-center py-10"
              >
                Belum ada data penjualan paket bulan ini.
              </div>
              <div
                v-else
                class="text-center py-10"
              >
                Memuat data grafik...
              </div>
              <template #fallback>
                <div class="text-center pa-5">
                  Memuat komponen grafik...
                </div>
              </template>
            </ClientOnly>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Tabel Transaksi Terakhir -->
      <VCol
        cols="12"
        md="7"
      >
        <VCard>
          <VCardTitle>Aktivitas Transaksi Terakhir</VCardTitle>
          <ClientOnly>
            <VDataTable
              :headers="transactionHeaders"
              :items="stats?.transaksiTerakhir ?? []"
              :loading="pending"
              :items-per-page="5"
              density="compact"
              class="text-no-wrap"
            >
              <template #item.amount="{ item }">
                {{ formatCurrency(item.raw.amount) }}
              </template>
              <template #item.user.full_name="{ item }">
                <div class="d-flex align-center">
                  <VAvatar
                    size="32"
                    :color="item.raw.user ? 'primary' : 'grey'"
                    class="me-3"
                    variant="tonal"
                  >
                    <VIcon :icon="item.raw.user ? 'mdi-account-outline' : 'mdi-account-off-outline'" />
                  </VAvatar>
                  <span>{{ item.raw.user?.full_name ?? 'Pengguna Dihapus' }}</span>
                </div>
              </template>
              <template #item.package.name="{ item }">
                <VChip
                  color="success"
                  size="small"
                  label
                >
                  {{ item.raw.package.name }}
                </VChip>
              </template>
              <template #no-data>
                <div class="text-center py-5">
                  Tidak ada transaksi terbaru.
                </div>
              </template>
            </VDataTable>
            <template #fallback>
              <div class="text-center pa-5">
                Memuat komponen tabel...
              </div>
            </template>
          </ClientOnly>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>

<script setup lang="ts">
import { useApiFetch } from '~/composables/useApiFetch';
import { computed, defineAsyncComponent, h, ref } from 'vue';

// --- PERBAIKAN: Menggunakan defineAsyncComponent dengan nama paket yang benar ('vue3-apexcharts') ---
const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    console.error(`Gagal memuat VueApexCharts`, err);
    // Fallback jika komponen gagal dimuat
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') };
  }),
);

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
});

// --- Definisi Tipe untuk Data Dashboard ---
interface TransaksiTerakhir {
  id: string;
  amount: number;
  package: { name: string };
  user: { full_name: string } | null;
}

interface PaketTerlaris {
  name: string;
  count: number;
}

interface DashboardStats {
  pendapatanHariIni: number;
  pendapatanBulanIni: number;
  pendaftarBaru: number;
  penggunaAktif: number;
  akanKadaluwarsa: number;
  kuotaTerjualMb: number;
  transaksiTerakhir: TransaksiTerakhir[];
  paketTerlaris: PaketTerlaris[];
}

// --- Fetch Data Statistik Utama ---
const { data: stats, pending, error } = useApiFetch<DashboardStats>('/admin/dashboard/stats', {
  lazy: true,
  server: false,
});

// --- State untuk Efek Hover pada Card Statistik Utama ---
// Variabel hover ini hanya relevan untuk kartu yang masih individual.
// Yang digabungkan tidak lagi membutuhkan efek hover individual ini.
const isHoverPendaftarMenunggu = ref(false);
const isHoverPenggunaAktif = ref(false);
const isHoverAkanKadaluwarsa = ref(false);


// --- Konfigurasi Tabel Transaksi ---
const transactionHeaders = [
  { title: 'PENGGUNA', key: 'user.full_name', sortable: false },
  { title: 'PAKET', key: 'package.name', sortable: false },
  { title: 'JUMLAH', key: 'amount', align: 'end', sortable: false },
];

// --- Konfigurasi Grafik Pie ---
const pieChartOptions = computed(() => ({
  chart: {
    type: 'pie',
  },
  labels: stats.value?.paketTerlaris.map(p => p.name) ?? [],
  legend: {
    position: 'bottom',
  },
  responsive: [{
    breakpoint: 480,
    options: {
      chart: {
        width: 200,
      },
      legend: {
        position: 'bottom',
      },
    },
  }],
}));

const pieChartSeries = computed(() => stats.value?.paketTerlaris.map(p => p.count) ?? []);

// --- Data Simulasi untuk Grafik Pendapatan Harian 7 Hari Terakhir ---
const generateDailyRevenueData = () => {
  const data = [];
  for (let i = 6; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    // Simulasikan pendapatan acak, bisa disesuaikan dengan pola yang lebih realistis
    const amount = Math.floor(Math.random() * 500000) + 100000;
    data.push({
      date: date.toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }),
      amount: amount,
    });
  }
  return data;
};

const dailyRevenueData = ref(generateDailyRevenueData());

const dailyRevenueChartOptions = computed(() => ({
  chart: {
    type: 'line',
    toolbar: { show: false },
    sparkline: { enabled: true },
  },
  grid: { show: false },
  xaxis: {
    categories: dailyRevenueData.value.map(d => d.date),
    labels: { show: false },
    axisBorder: { show: false },
    axisTicks: { show: false },
  },
  yaxis: {
    labels: { show: false },
  },
  stroke: {
    curve: 'smooth',
    width: 2,
  },
  tooltip: {
    enabled: true,
    y: {
      formatter: (val: number) => formatCurrency(val),
    },
    x: {
      formatter: (val: string) => `Tanggal: ${val}`,
    },
  },
  colors: ['#28C76F'], // Warna hijau untuk pendapatan
}));

const dailyRevenueChartSeries = computed(() => [{
  name: 'Pendapatan Harian',
  data: dailyRevenueData.value.map(d => d.amount),
}]);

// --- Data Simulasi untuk Grafik Pendapatan Bulanan 12 Bulan Terakhir ---
const generateMonthlyRevenueData = () => {
  const data = [];
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  const currentMonth = new Date().getMonth();

  for (let i = 11; i >= 0; i--) {
    const monthIndex = (currentMonth - i + 12) % 12;
    // Simulasikan pendapatan acak bulanan
    const amount = Math.floor(Math.random() * 5000000) + 1000000; // Antara 1 juta - 6 juta
    data.push({
      month: monthNames[monthIndex],
      amount: amount,
    });
  }
  return data;
};

const monthlyRevenueData = ref(generateMonthlyRevenueData());

const monthlyRevenueChartOptions = computed(() => ({
  chart: {
    type: 'bar',
    toolbar: { show: false },
    sparkline: { enabled: true },
  },
  plotOptions: {
    bar: {
      horizontal: false,
      columnWidth: '50%',
    },
  },
  grid: { show: false },
  xaxis: {
    categories: monthlyRevenueData.value.map(d => d.month),
    labels: { show: false },
    axisBorder: { show: false },
    axisTicks: { show: false },
  },
  yaxis: {
    labels: { show: false },
  },
  tooltip: {
    enabled: true,
    y: {
      formatter: (val: number) => formatCurrency(val),
    },
    x: {
      formatter: (val: string) => `Bulan: ${val}`,
    },
  },
  colors: ['#00cfe8'], // Warna biru untuk pendapatan bulanan
}));

const monthlyRevenueChartSeries = computed(() => [{
  name: 'Pendapatan Bulanan',
  data: monthlyRevenueData.value.map(d => d.amount),
}]);


// --- Computed untuk Progress Linear (Pertahankan jika masih relevan di komponen lain) ---
const percentageKuotaTerjual = computed(() => {
  const maxKuotaUntukPersentase = 100000; // Contoh: 100 GB dalam MB
  if (!stats.value?.kuotaTerjualMb || maxKuotaUntukPersentase === 0) {
    return 0;
  }
  return (stats.value.kuotaTerjualMb / maxKuotaUntukPersentase) * 100;
});

// --- Fungsi Helper ---
const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined) {
    return 'Rp 0';
  }
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

useHead({ title: 'Dashboard Admin' });
</script>

<style lang="scss" scoped>
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
</style>