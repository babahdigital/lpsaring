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
    // [PERBAIKAN] Langsung panggil action otorisasi dari store
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
      // Pesan error sudah di-set oleh authStore, tampilkan di snackbar
      addSnackbar({
        type: 'error',
        title: 'Otorisasi Gagal',
        text: authStore.error || 'Terjadi kesalahan yang tidak diketahui.',
      })
    }
  }
  catch (_e) {
    // Menangani error tak terduga
    addSnackbar({
      type: 'error',
      title: 'Error Kritis',
      text: 'Gagal memproses permintaan otorisasi.',
    })
  }
  finally {
    isLoading.value = false
  }
}

function handleDismiss() {
  hideDeviceNotificationPopup()
  authStore.resetAuthorizationFlow()
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

      <VCardActions class="d-flex flex-column flex-sm-row gap-3 justify-center">
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
      </VCardActions>
    </VCard>
  </VDialog>
</template>
