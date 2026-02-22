<script setup lang="ts">
import { useRuntimeConfig } from '#app'
import { computed, defineAsyncComponent, ref } from 'vue'
import { useAuthStore } from '~/store/auth'

// --- Data Tabel ---
const headers = ref([
  { title: 'Waktu', key: 'timestamp', sortable: true, width: '25%' },
  { title: 'Tipe', key: 'type', sortable: true, width: '15%' },
  { title: 'Nomor Telepon', key: 'phone', sortable: false, width: '30%' },
  { title: 'Keterangan', key: 'details', sortable: false, width: '30%' },
])

const placeholderItems = ref([
  { timestamp: '2025-04-27 15:30:05', type: 'Login', phone: '081234567890', details: 'Login berhasil via OTP' },
  { timestamp: '2025-04-27 15:28:12', type: 'Register', phone: '089876543210', details: 'Pengguna baru terdaftar' },
  { timestamp: '2025-04-27 14:15:55', type: 'Login', phone: '081112223334', details: 'Login berhasil via OTP' },
  { timestamp: '2025-04-26 20:05:10', type: 'Login', phone: '081234567890', details: 'Login berhasil via OTP' },
  { timestamp: '2025-04-26 10:00:01', type: 'Register', phone: '085556667778', details: 'Pengguna baru terdaftar' },
])

// --- Variabel tidak terpakai (diberi prefix _) ---
const _WeeklyUsageChart = defineAsyncComponent(() => import('~/components/charts/WeeklyUsageChart.vue'))
const _MonthlyUsageChart = defineAsyncComponent(() => import('~/components/charts/MonthlyUsageChart.vue'))
const _pageTitle = computed(() => '')

// --- State & Config ---
const _config = useRuntimeConfig()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

// --- Fetch Data (Placeholder - tidak digunakan) ---
const _quotaData = ref(null)
const _quotaPending = ref(false)
const _weeklyUsageData = ref(null)
const _weeklyUsagePending = ref(false)
const _monthlyUsageData = ref(null)
const _monthlyChartPending = ref(false)

// --- Fungsi tidak terpakai (diberi prefix _) ---
function _formatDateTime(_dateTimeString: string | null | undefined): string {
  return 'N/A'
}

function _formatUsername(_username: string | null | undefined): string {
  return 'Tidak Tersedia'
}

function _refreshAllData() {
  if (!isAdmin.value) {
    console.warn('Memperbarui data pengguna...')
  }
  else {
    console.warn('Memperbarui data admin...')
  }
}
</script>

<template>
  <VCard>
    <VCardItem>
      <VCardTitle>Aktivitas Terbaru</VCardTitle>
      <VCardSubtitle>Log Pendaftaran & Login Pengguna</VCardSubtitle>
    </VCardItem>
    <VDataTable
      :headers="headers"
      :items="placeholderItems"
      :items-per-page="5"
      density="compact"
      class="text-no-wrap"
      hide-default-footer
    >
      <template #no-data>
        <div class="text-center py-4">
          Belum ada aktivitas tercatat.
        </div>
      </template>
    </VDataTable>
  </VCard>
</template>
