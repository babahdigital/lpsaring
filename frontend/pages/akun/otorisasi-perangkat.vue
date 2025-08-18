// pages/akun/otorisasi-perangkat.vue atau pages/otorisasi-perangkat.vue

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { useClientDetection } from '~/composables/useClientDetection'
import { useAuthStore } from '~/store/auth'

// Meta
definePageMeta({
  title: 'Otorisasi Perangkat',
  requiresAuth: true,
  layout: 'default',
})

// Composables
const authStore = useAuthStore()
const { detectionResult, triggerDetection } = useClientDetection() // [PERBAIKAN] Menggunakan triggerDetection dan detectionResult
const router = useRouter()

// State
// [PERBAIKAN] Menggunakan computed property dari composable untuk data yang lebih konsisten
const detectedInfo = computed(() => {
  const summary = detectionResult.value?.summary
  if (!summary)
    return { ip: null, mac: null, accessMode: null }

  return {
    ip: summary.detected_ip,
    mac: summary.detected_mac,
    accessMode: summary.access_mode,
  }
})

// Methods
async function handleAuthorizeDevice() {
  try {
    const success = await authStore.authorizeDevice()
    if (success) {
      // Redirect to device management page after successful authorization
      await router.push('/akun/perangkat')
    }
  }
  catch (error) {
    console.error('[DEVICE-AUTH] Authorization failed:', error)
  }
}

async function handleLogout() {
  try {
    await authStore.logout()
    await router.push('/login')
  }
  catch (error) {
    console.error('[DEVICE-AUTH] Logout failed:', error)
  }
}

// Lifecycle
onMounted(async () => {
  console.log('[DEVICE-AUTH-PAGE] Mounted, ensuring client info is detected...')

  try {
    // [PERBAIKAN] Memanggil triggerDetection jika data belum ada, untuk memastikan data selalu termuat.
    if (!detectedInfo.value.ip && !detectedInfo.value.mac) {
      await triggerDetection()
    }
    console.log('[DEVICE-AUTH-PAGE] Client detection completed:', detectedInfo.value)
  }
  catch (error) {
    console.error('[DEVICE-AUTH-PAGE] Client detection failed:', error)
    // Anda bisa menambahkan snackbar error di sini jika diperlukan
  }
})
</script>

<template>
  <div class="d-flex flex-column">
    <VCard class="mb-6">
      <VCardTitle class="pb-4">
        <VIcon icon="tabler-device-mobile" class="me-2" />
        Otorisasi Perangkat Baru
      </VCardTitle>
      <VCardText>
        <VAlert
          color="warning"
          variant="tonal"
          icon="tabler-alert-triangle"
          class="mb-4"
        >
          <VAlertTitle>Perangkat Baru Terdeteksi</VAlertTitle>
          <div class="mt-2">
            Kami mendeteksi bahwa Anda menggunakan perangkat yang belum terdaftar.
            Untuk keamanan akun Anda, silakan otorisasi perangkat ini terlebih dahulu.
          </div>
        </VAlert>

        <div v-if="detectedInfo.ip || detectedInfo.mac" class="mb-4">
          <h6 class="text-h6 mb-3">Informasi Perangkat:</h6>
          <VChip
            v-if="detectedInfo.ip"
            color="primary"
            variant="tonal"
            class="me-2 mb-2"
          >
            <VIcon icon="tabler-world" start />
            IP: {{ detectedInfo.ip }}
          </VChip>
          <VChip
            v-if="detectedInfo.mac"
            color="success"
            variant="tonal"
            class="me-2 mb-2"
          >
            <VIcon icon="tabler-device-mobile" start />
            MAC: {{ detectedInfo.mac }}
          </VChip>
        </div>
        <div v-else>
          <VSkeletonLoader type="text@2" />
        </div>
      </VCardText>
    </VCard>

    <VCard>
      <VCardTitle>Pilihan Otorisasi</VCardTitle>
      <VCardText>
        <VRow>
          <VCol cols="12" md="6">
            <VCard
              variant="outlined"
              class="h-100"
              :class="{ 'border-primary': !authStore.loading }"
            >
              <VCardTitle class="text-success">
                <VIcon icon="tabler-check-circle" class="me-2" />
                Daftarkan Perangkat Ini
              </VCardTitle>
              <VCardText>
                Jika ini adalah perangkat Anda yang sah, klik tombol di bawah untuk mendaftarkannya.
                Setelah didaftarkan, Anda dapat menggunakan perangkat ini untuk mengakses akun.
              </VCardText>
              <VCardActions>
                <VBtn
                  color="success"
                  variant="flat"
                  :loading="authStore.loading"
                  :disabled="authStore.loading"
                  @click="handleAuthorizeDevice"
                >
                  <VIcon icon="tabler-plus" start />
                  Daftarkan Perangkat
                </VBtn>
              </VCardActions>
            </VCard>
          </VCol>

          <VCol cols="12" md="6">
            <VCard
              variant="outlined"
              class="h-100"
              :class="{ 'border-error': !authStore.loading }"
            >
              <VCardTitle class="text-error">
                <VIcon icon="tabler-logout" class="me-2" />
                Logout dari Akun
              </VCardTitle>
              <VCardText>
                Jika ini bukan perangkat Anda atau Anda tidak ingin mendaftarkannya,
                logout dari akun untuk keamanan.
              </VCardText>
              <VCardActions>
                <VBtn
                  color="error"
                  variant="outlined"
                  :disabled="authStore.loading"
                  @click="handleLogout"
                >
                  <VIcon icon="tabler-logout" start />
                  Logout Sekarang
                </VBtn>
              </VCardActions>
            </VCard>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VAlert
      v-if="authStore.message"
      color="success"
      variant="tonal"
      class="mt-4"
      closable
      @click:close="authStore.clearMessage()"
    >
      {{ authStore.message }}
    </VAlert>

    <VAlert
      v-if="authStore.error"
      color="error"
      variant="tonal"
      class="mt-4"
      closable
      @click:close="authStore.clearError()"
    >
      {{ authStore.error }}
    </VAlert>
  </div>
</template>

<style scoped>
.border-primary {
  border-color: rgb(var(--v-theme-primary)) !important;
}

.border-error {
  border-color: rgb(var(--v-theme-error)) !important;
}
</style>
