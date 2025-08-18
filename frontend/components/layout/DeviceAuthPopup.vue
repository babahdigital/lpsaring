// components/layout/DeviceAuthPopup.vue

<script setup lang="ts">
import { ref } from 'vue'

import { useDeviceNotification } from '~/composables/useDeviceNotification'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const { isPopupVisible, hideDeviceNotificationPopup } = useDeviceNotification()
const { add: addSnackbar } = useSnackbar()
const router = useRouter()
const isLoading = ref(false)

async function handleRegister() {
  if (isLoading.value)
    return
  isLoading.value = true

  try {
    // ✅ SEMPURNAKAN: Periksa ketersediaan token terlebih dahulu
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

    // Proses otorisasi perangkat
    const success = await authStore.authorizeDevice()
    hideDeviceNotificationPopup()

    if (success) {
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

// ✅ BARU: Fungsi untuk menolak perangkat dan logout
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
    
    await authStore.rejectDeviceAuthorization()
    
    // Notification tidak perlu, karena akan redirect ke halaman login
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
  <VDialog
    :model-value="isPopupVisible"
    persistent
    max-width="450px"
    transition="dialog-bottom-transition"
  >
    <VCard class="text-center pa-4 pa-sm-6">
      <VCardText>
        <VAvatar color="warning" variant="tonal" size="60" class="mb-4">
          <VIcon size="36" icon="tabler-device-mobile-question" />
        </VAvatar>

        <h4 class="text-h5 font-weight-bold mb-2">
          Perangkat Belum Terdaftar
        </h4>
        <p class="text-body-1 text-medium-emphasis">
          Perangkat yang Anda gunakan belum terdaftar. Untuk keamanan dan fungsionalitas penuh, silakan daftarkan perangkat ini.
        </p>
      </VCardText>

      <VCardActions class="d-flex flex-column gap-3 justify-center">
        <VBtn
          color="warning"
          variant="flat"
          block
          size="large"
          :loading="isLoading"
          :disabled="isLoading"
          @click="handleRegister"
        >
          <VIcon start icon="tabler-device-mobile-plus" />
          Daftarkan Sekarang
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
