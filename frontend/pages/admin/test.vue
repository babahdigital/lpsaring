<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

// Ambil fungsi 'add' dari composable snackbar kita
const { add: addSnackbar } = useSnackbar()

// Add network status testing
const networkStatus = useNetworkStatus()
const clientInfo = ref({
  ip: 'Detecting...',
  userAgent: '',
  timestamp: new Date().toISOString(),
})

// Add deduplication for API calls
const isDetecting = ref(false)
let detectionPromise: Promise<any> | null = null

// Deduplicated client info detection
async function detectClientInfoSafe() {
  if (isDetecting.value || detectionPromise) {
    console.log('🛡️ Duplicate API call prevented')
    return detectionPromise
  }

  isDetecting.value = true
  console.log('🔍 Starting client detection...')

  detectionPromise = $fetch('/api/auth/detect-client-info')
    .then((response) => {
      if (response.status === 'SUCCESS') {
        clientInfo.value.ip = response.data.detected_ip || 'Unknown'
        clientInfo.value.timestamp = new Date().toISOString()
        console.log('✅ Client detection successful:', response.data.detected_ip)
      }
      else {
        clientInfo.value.ip = 'API Error'
        console.warn('⚠️ API returned error status')
      }
      return response
    })
    .catch((error) => {
      console.error('❌ Failed to get client info:', error)
      clientInfo.value.ip = 'Error fetching IP'
      throw error
    })
    .finally(() => {
      isDetecting.value = false
      // Clear promise after a short delay to allow for normal re-calls
      setTimeout(() => {
        detectionPromise = null
      }, 1000)
    })

  return detectionPromise
}

// Get client info
onMounted(async () => {
  if (import.meta.client) {
    clientInfo.value.userAgent = navigator.userAgent

    // Test IP detection with deduplication
    await detectClientInfoSafe()
  }
})

function triggerSuccess() {
  addSnackbar({
    type: 'success',
    title: 'Berhasil',
    text: 'Ini adalah notifikasi sukses dari halaman tes.',
  })
}

function triggerError() {
  addSnackbar({
    type: 'error',
    title: 'Error Terjadi',
    text: 'Ini adalah notifikasi error dari halaman tes.',
  })
}

function triggerWarning() {
  addSnackbar({
    type: 'warning',
    title: 'Peringatan',
    text: 'Ini adalah notifikasi peringatan dari halaman tes.',
  })
}

function triggerInfo() {
  addSnackbar({
    type: 'info',
    title: 'Informasi',
    text: 'Ini adalah notifikasi informasi dari halaman tes.',
  })
}
</script>

<template>
  <VCard title="Alat Tes Snackbar">
    <VCardText>
      Gunakan tombol-tombol di bawah ini untuk memicu berbagai jenis notifikasi
      snackbar dan memeriksa apakah ikonnya muncul dengan benar.
    </VCardText>

    <VCardActions class="flex-wrap">
      <VBtn
        variant="tonal"
        color="success"
        @click="triggerSuccess"
      >
        <VIcon
          start
          icon="tabler:circle-check"
        />
        Tampilkan Sukses
      </VBtn>
      <VBtn
        variant="tonal"
        color="error"
        @click="triggerError"
      >
        <VIcon
          start
          icon="tabler:alert-circle"
        />
        Tampilkan Error
      </VBtn>
      <VBtn
        variant="tonal"
        color="warning"
        @click="triggerWarning"
      >
        <VIcon
          start
          icon="tabler:alert-triangle"
        />
        Tampilkan Peringatan
      </VBtn>
      <VBtn
        variant="tonal"
        color="info"
        @click="triggerInfo"
      >
        <VIcon
          start
          icon="tabler:info-circle"
        />
        Tampilkan Info
      </VBtn>
    </VCardActions>
  </VCard>

  <!-- Network Status Test Card -->
  <VCard class="mt-6" title="Network Status & IP Detection Test">
    <VCardText>
      <div class="grid gap-4">
        <!-- Network Status Info -->
        <VAlert
          :type="networkStatus.isOnline.value ? 'success' : 'error'"
          :title="networkStatus.isOnline.value ? 'Online' : 'Offline'"
        >
          <div class="mt-2">
            <p><strong>Connection Type:</strong> {{ networkStatus.connectionType.value }}</p>
            <p><strong>Effective Type:</strong> {{ networkStatus.effectiveType.value }}</p>
            <p v-if="networkStatus.downlink.value > 0">
              <strong>Downlink:</strong> {{ networkStatus.downlink.value.toFixed(1) }} Mbps
            </p>
            <p v-if="networkStatus.rtt.value > 0">
              <strong>RTT:</strong> {{ networkStatus.rtt.value }}ms
            </p>
          </div>
        </VAlert>

        <!-- Client Info -->
        <VAlert type="info" title="Client Information">
          <div class="mt-2">
            <p><strong>Detected IP:</strong> {{ clientInfo.ip }}</p>
            <p><strong>User Agent:</strong> {{ clientInfo.userAgent.substring(0, 100) }}...</p>
            <p><strong>Timestamp:</strong> {{ new Date(clientInfo.timestamp).toLocaleString() }}</p>
          </div>
        </VAlert>

        <!-- Actions -->
        <div class="flex gap-2">
          <VBtn
            color="primary"
            @click="networkStatus.refresh()"
          >
            <VIcon start icon="tabler:refresh" />
            Refresh Network Status
          </VBtn>
          <VBtn
            color="secondary"
            @click="async () => {
              try {
                await detectClientInfoSafe();
                addSnackbar({
                  type: 'success',
                  title: 'IP Updated',
                  text: `Current IP: ${clientInfo.ip}`,
                });
              }
              catch (error) {
                addSnackbar({
                  type: 'error',
                  title: 'Update Failed',
                  text: 'Failed to refresh IP detection',
                });
              }
            }"
          >
            title: 'IP Detection Failed',
            text: String(error)
            });
            }
            }"
            >
            <VIcon start icon="tabler:network" />
            Refresh IP Detection
          </VBtn>
        </div>
      </div>
    </VCardText>
  </VCard>
</template>
