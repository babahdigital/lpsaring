<template>
  <div>
    <VRow>
      <VCol cols="12" md="4" sm="6">
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendapatan Hari Ini</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ formatCurrency(stats?.pendapatanHariIni) }}
                </h6>
              </div>
              <span class="text-sm">Ringkasan hari ini</span>
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

      <VCol cols="12" md="4" sm="6">
         <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendapatan Minggu Ini</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ formatCurrency(stats?.pendapatanMingguIni) }}
                </h6>
              </div>
              <span class="text-sm">Total minggu ini</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="primary"
            >
              <VIcon icon="mdi-cash-multiple" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>
      
      <VCol cols="12" md="4" sm="6">
         <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendapatan Bulan Ini</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ formatCurrency(stats?.pendapatanBulanIni) }}
                </h6>
              </div>
              <span class="text-sm">Total bulan ini</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="info"
            >
              <VIcon icon="mdi-poll" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" md="4" sm="6">
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pendaftar Baru</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.pendaftarBaru }}
                </h6>
              </div>
              <span class="text-sm">Menunggu persetujuan</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="warning"
            >
              <VIcon icon="mdi-account-plus-outline" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" md="4" sm="6">
        <VCard>
          <VCardText class="d-flex justify-space-between">
            <div>
              <span>Pengguna Aktif</span>
              <div class="d-flex align-center gap-2 my-1">
                <h6 class="text-h6">
                  {{ stats?.penggunaAktif }}
                </h6>
              </div>
              <span class="text-sm">Total pengguna disetujui</span>
            </div>
            <VAvatar
              rounded
              variant="tonal"
              color="secondary"
            >
              <VIcon icon="mdi-account-group-outline" />
            </VAvatar>
          </VCardText>
        </VCard>
      </VCol>

    </VRow>
    
    <VRow class="mt-4">
      <VCol>
        <VCard>
          <VCardTitle>Grafik Pendapatan (Segera Hadir)</VCardTitle>
          <VCardText>
            Area ini akan menampilkan grafik tren pendapatan.
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
    
  </div>
</template>

<script setup lang="ts">
import { useApiFetch } from '~/composables/useApiFetch';

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

// Fetch data statistik dari backend
const { data: stats, pending, error } = useApiFetch('/admin/dashboard/stats', {
  lazy: true, // Load data di background
  server: false, // Ambil data di sisi klien saja untuk dashboard
});

// Fungsi helper untuk format mata uang
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

useHead({ title: 'Dashboard Admin' })
</script>