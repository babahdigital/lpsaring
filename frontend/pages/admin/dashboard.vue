<template>
  <div>
    <!-- Baris 1: Statistik KPI Utama -->
    <VRow>
      <!-- Pendapatan Hari Ini -->
      <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendapatan Hari Ini</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ formatCurrency(stats?.pendapatanHariIni) }}
                </h6>
              </div>
              <span class="text-sm">Total transaksi sukses hari ini</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="success"
            >
              <VIcon icon="mdi-cash" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Pendaftar Menunggu Persetujuan (Actionable) -->
      <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Menunggu Persetujuan</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.pendaftarBaru ?? 0 }} Pengguna
                </h6>
              </div>
              <span class="text-sm text-warning">Perlu tindakan Anda</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="warning"
            >
              <VIcon icon="mdi-account-clock-outline" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Total Pengguna Aktif -->
      <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pengguna Aktif</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.penggunaAktif ?? 0 }} Pengguna
                </h6>
              </div>
              <span class="text-sm">Total pengguna terdaftar & disetujui</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="primary"
            >
              <VIcon icon="mdi-account-group-outline" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Pengguna Akan Kadaluwarsa (Proaktif) -->
      <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Akan Kadaluwarsa</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.akanKadaluwarsa ?? 0 }} Pengguna
                </h6>
              </div>
              <span class="text-sm">Masa aktif akan habis dalam 7 hari</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="secondary"
            >
              <VIcon icon="mdi-account-reactivate-outline" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Kuota Terjual Bulan Ini -->
      <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Kuota Terjual (Bulan Ini)</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.kuotaTerjualMb ? (stats.kuotaTerjualMb / 1024).toFixed(2) : '0.00' }} GB
                </h6>
              </div>
              <span class="text-sm">Total kuota dari paket terjual</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="info"
            >
              <VIcon icon="mdi-signal-cellular-3" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

       <!-- Pendapatan Bulan Ini -->
       <VCol
        cols="12"
        md="4"
        sm="6"
      >
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendapatan Bulan Ini</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ formatCurrency(stats?.pendapatanBulanIni) }}
                </h6>
              </div>
              <span class="text-sm">Total transaksi sukses bulan ini</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="success"
            >
              <VIcon icon="mdi-poll" />
            </VAvatar>
          </VCardText>
        </VCard>
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
          <VCardTitle>Paket Terlaris (Bulan Ini)</VCardTitle>
          <VCardText>
            <ClientOnly>
              <VueApexCharts
                v-if="!pending && pieChartSeries.length > 0"
                type="pie"
                height="350"
                :options="pieChartOptions"
                :series="pieChartSeries"
              />
              <template #fallback>
                <div class="text-center pa-5">
                  Memuat komponen grafik...
                </div>
              </template>
            </ClientOnly>
            <div
              v-if="!pending && pieChartSeries.length === 0"
              class="text-center"
            >
              Belum ada data penjualan paket bulan ini.
            </div>
            <div
              v-if="pending"
              class="text-center"
            >
              Memuat data grafik...
            </div>
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
import { VDataTable } from 'vuetify/labs/VDataTable';
import { VueApexCharts } from 'vue3-apexcharts';
import { computed } from 'vue';

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