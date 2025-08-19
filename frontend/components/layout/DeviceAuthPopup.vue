// components/layout/DeviceAuthPopup.vue

<script setup lang="ts">
import { ref, watch } from 'vue'

import { useDeviceNotification } from '~/composables/useDeviceNotification'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const { isPopupVisible, hideDeviceNotificationPopup } = useDeviceNotification()
const { add: addSnackbar } = useSnackbar()
const router = useRouter()
const isLoading = ref(false)

// Computed para device info with fallback
const deviceInfo = computed(() => authStore.pendingDeviceInfo || {})

// Dialog visibility based directly on auth store state
const isVisible = computed(() => authStore.deviceAuthRequired)

// SEMPURNAKAN: Tambahkan watcher untuk debugging visibilitas popup
watch(isVisible, (value) => {
  console.log('[DEVICE-AUTH-POPUP] Visibility changed:', value)
  if (value) {
    console.log('[DEVICE-AUTH-POPUP] Pending device info:', authStore.pendingDeviceInfo)
  }
})

async function handleRegister() {
  if (isLoading.value)
    return
  isLoading.value = true

  try {
    // ✅ OPTIMASI: Periksa ketersediaan token terlebih dahulu
    if (!authStore.hasValidToken()) {
      console.warn('[DEVICE-AUTH-POPUP] Mencoba otorisasi tanpa token valid')
      addSnackbar({
        type: 'error',
        title: 'Sesi Login Bermasalah',
        text: 'Silakan login ulang untuk melanjutkan otorisasi perangkat.',
      })
      await router.push('/login')
      return
    }

    console.log('[DEVICE-AUTH-POPUP] Memulai proses otorisasi perangkat')
    // Proses otorisasi perangkat
    const success = await authStore.authorizeDevice()
    // Sembunyikan popup notifikasi yang mungkin muncul dari sistem sebelumnya
    hideDeviceNotificationPopup() 

    if (success) {
      console.log('[DEVICE-AUTH-POPUP] Otorisasi berhasil, menampilkan notifikasi')
      addSnackbar({
        type: 'success',
        title: 'Otorisasi Berhasil',
        text: 'Perangkat Anda telah berhasil didaftarkan.',
      })
      // Arahkan ke halaman daftar perangkat untuk melihat hasilnya
      await router.push('/akun/perangkat')
    }
    else {
      // Handle specific error types
      if (authStore.error?.includes('401') || authStore.error?.includes('Unauthorized')) {
        addSnackbar({
          type: 'error',
          title: 'Sesi Berakhir',
          text: 'Sesi login Anda telah berakhir. Silakan login ulang.',
        })
        await router.push('/login')
      } else {
        addSnackbar({
          type: 'error',
          title: 'Otorisasi Gagal',
          text: authStore.error || 'Terjadi kesalahan yang tidak diketahui.',
        })
      }
    }
  }
  catch (err) {
    console.error('[DEVICE-AUTH-POPUP] Error saat otorisasi perangkat:', err)
    
    // Check for 401/403 errors to handle session issues
    if (err?.status === 401 || err?.status === 403 || 
        String(err).includes('401') || String(err).includes('Unauthorized')) {
      addSnackbar({
        type: 'error',
        title: 'Sesi Berakhir',
        text: 'Sesi login Anda telah berakhir. Silakan login ulang.',
      })
      await router.push('/login')
    } else {
      addSnackbar({
        type: 'error',
        title: 'Error Otorisasi',
        text: 'Gagal memproses permintaan otorisasi. Silakan coba lagi.',
      })
    }
  }
  finally {
    isLoading.value = false
  }
}

function handleDismiss() {
  hideDeviceNotificationPopup()
  authStore.resetAuthorizationFlow()
}

// ✅ SEMPURNAKAN: Fungsi untuk menolak perangkat dan logout
async function handleRejectDevice() {
  if (isLoading.value)
    return
  isLoading.value = true
  
  try {
    addSnackbar({
      type: 'info',
      title: 'Menolak Perangkat',
      text: 'Memproses penolakan perangkat dan logout...',
    })
    
    // Tambahkan log untuk debugging
    console.log('[DEVICE-AUTH-POPUP] Menolak perangkat dan memulai logout...')
    
    await authStore.rejectDeviceAuthorization()
    
    // Notifikasi tidak perlu, karena akan redirect ke halaman login oleh auth store
    console.log('[DEVICE-AUTH-POPUP] Penolakan perangkat berhasil diproses')
  }
  catch (err) {
    console.error('[DEVICE-AUTH-POPUP] Error saat menolak perangkat:', err)
    addSnackbar({
      type: 'error',
      title: 'Error',
      text: 'Gagal menolak perangkat. Silakan coba lagi.',
    })
  }
  finally {
    isLoading.value = false
  }
}
</script>

<template>
  <!-- SEMPURNAKAN: Binding dialog ke state deviceAuthRequired dari auth store dengan tambahan watch untuk debugging -->
  <VDialog
    :model-value="authStore.deviceAuthRequired || isPopupVisible"
    persistent
    max-width="500px"
    transition="dialog-bottom-transition"
    @update:model-value="val => val === false && handleDismiss()"
  >
    <VCard class="text-center pa-4 pa-sm-6">
      <VCardTitle class="d-flex justify-center mb-2">
        <VAvatar color="warning" variant="tonal" size="48" class="me-3">
          <VIcon size="28" icon="tabler-device-mobile-question" />
        </VAvatar>
        <span class="text-h5 font-weight-bold d-flex align-center">Otorisasi Perangkat</span>
      </VCardTitle>

      <VCardText>
        <p class="text-body-1 text-medium-emphasis mb-4">
          Untuk keamanan akun Anda, kami perlu memverifikasi perangkat baru ini. Silakan otorisasi perangkat untuk melanjutkan menggunakan layanan kami.
        </p>
        
        <!-- Info perangkat -->
        <VList density="compact" class="bg-grey-lighten-4 rounded-lg mb-3">
          <VListItem>
            <template #prepend>
              <VIcon icon="tabler-device-laptop" />
            </template>
            <VListItemTitle>Informasi Perangkat</VListItemTitle>
          </VListItem>
          
          <VListItem>
            <template #prepend>
              <VIcon icon="tabler-network" color="info" size="small" />
            </template>
            <VListItemTitle class="text-body-2">
              IP: {{ deviceInfo.ip || 'Tidak terdeteksi' }}
            </VListItemTitle>
          </VListItem>
          
          <VListItem>
            <template #prepend>
              <VIcon icon="tabler-device-desktop-analytics" color="info" size="small" />
            </template>
            <VListItemTitle class="text-body-2">
              MAC: {{ deviceInfo.mac || 'Tidak terdeteksi' }}
            </VListItemTitle>
          </VListItem>
        </VList>
        
        <VAlert
          type="warning"
          variant="tonal"
          border="start"
          density="compact"
          class="text-body-2 mb-2"
        >
          <p class="mb-0">
            Jika ini bukan Anda yang login, pilih <strong>Tolak & Logout</strong> untuk keamanan akun Anda.
          </p>
        </VAlert>
      </VCardText>

      <VCardActions class="d-flex flex-column gap-3 justify-center">
        <VBtn
          color="success"
          variant="elevated"
          block
          size="large"
          :loading="isLoading"
          :disabled="isLoading"
          @click="handleRegister"
        >
          <VIcon start icon="tabler-device-mobile-check" />
          Otorisasi Perangkat Ini
        </VBtn>
        <VBtn
          color="secondary"
          variant="tonal"
          block
          size="large"
          :disabled="isLoading"
          @click="handleDismiss"
        >
          Nanti Saja
        </VBtn>
        <VBtn
          color="error"
          variant="outlined"
          block
          size="large"
          :loading="isLoading"
          :disabled="isLoading"
          @click="handleRejectDevice"
        >
          <VIcon start icon="tabler-logout" />
          Tolak & Logout
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
