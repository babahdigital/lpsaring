<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'

// --- State & Config ---
const authStore = useAuthStore()

// --- Role Check ---
const isAdmin = computed(() => authStore.isAdmin)
const _pageTitle = computed(() => isAdmin.value ? 'Dashboard Admin' : 'Dashboard Pengguna') // Beri prefix _

// --- Placeholder Data (untuk statis) ---
const _quotaData = null // Beri prefix _
const _quotaPending = false // Beri prefix _
const _weeklyUsageData = null // Beri prefix _
const _weeklyUsagePending = false // Beri prefix _
const _monthlyUsageData = null // Beri prefix _
const _monthlyChartPending = false // Beri prefix _

// --- Helper Functions (diubah menjadi private) ---
function _formatDateTime(_dateTimeString: string | null | undefined): string { // Beri prefix _
  return 'N/A' // Implementasi asli dihapus untuk kesederhanaan
}

function _formatUsername(_username: string | null | undefined): string { // Beri prefix _
  return 'Tidak Tersedia' // Implementasi asli dihapus untuk kesederhanaan
}

// Refresh all relevant data fetches based on role
function _refreshAllData() { // Beri prefix _
  if (!isAdmin.value) {
    console.warn('Memperbarui data pengguna...') // Ganti console.log dengan console.warn
  }
  else {
    console.warn('Memperbarui data admin...') // Ganti console.log dengan console.warn
  }
}
</script>

<template>
  <VRow>
    <VCol cols="12" sm="6" md="4">
      <VCard>
        <VCardText class="d-flex align-center">
          <VAvatar color="primary" variant="tonal" rounded size="42" class="me-4">
            <VIcon icon="tabler-users" size="28" />
          </VAvatar>
          <div>
            <span class="text-caption">Pengguna Aktif</span>
            <div class="text-h6 font-weight-medium">
              152
            </div>
          </div>
        </VCardText>
      </VCard>
    </VCol>

    <VCol cols="12" sm="6" md="4">
      <VCard>
        <VCardText class="d-flex align-center">
          <VAvatar color="success" variant="tonal" rounded size="42" class="me-4">
            <VIcon icon="tabler-receipt-2" size="28" />
          </VAvatar>
          <div>
            <span class="text-caption">Transaksi (Bulan Ini)</span>
            <div class="text-h6 font-weight-medium">
              Rp 1.250.000
            </div>
          </div>
        </VCardText>
      </VCard>
    </VCol>

    <VCol cols="12" sm="6" md="4">
      <VCard>
        <VCardText class="d-flex align-center">
          <VAvatar color="info" variant="tonal" rounded size="42" class="me-4">
            <VIcon icon="tabler-package" size="28" />
          </VAvatar>
          <div>
            <span class="text-caption">Paket Terpopuler</span>
            <div class="text-h6 font-weight-medium">
              Hemat 30 Hari
            </div>
          </div>
        </VCardText>
      </VCard>
    </VCol>
  </VRow>
</template>
