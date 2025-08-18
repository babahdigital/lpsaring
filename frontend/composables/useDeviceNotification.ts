// composables/useDeviceNotification.ts

import { ref, watch } from 'vue'

import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

// [PERBAIKAN] State reaktif untuk visibilitas popup, diekspor agar bisa diakses global.
const isPopupVisible = ref(false)

/**
 * Composable untuk menangani notifikasi otorisasi perangkat.
 * Menampilkan snackbar dan mengontrol popup modal.
 */
export function useDeviceNotification() {
  const authStore = useAuthStore()
  const { add: addSnackbar } = useSnackbar()

  // Fungsi untuk menampilkan popup
  const showDeviceNotificationPopup = () => {
    // Hanya tampilkan jika belum terlihat untuk menghindari duplikasi
    if (!isPopupVisible.value) {
      isPopupVisible.value = true
    }
  }

  // Fungsi untuk menyembunyikan popup
  const hideDeviceNotificationPopup = () => {
    isPopupVisible.value = false
  }

  // Fungsi utama yang dipanggil untuk memulai proses notifikasi.
  const showDeviceNotification = () => {
    try {
      // 1. Tampilkan snackbar yang tidak persisten sebagai pemberitahuan awal.
      addSnackbar({
        type: 'warning',
        title: 'Perangkat Belum Terdaftar',
        text: 'Aksi diperlukan untuk mendaftarkan perangkat ini.',
        timeout: 8000, // Tampilkan selama 8 detik
      })

      // 2. Tampilkan popup modal setelah jeda singkat untuk tindakan lebih lanjut.
      setTimeout(() => {
        showDeviceNotificationPopup()
      }, 1500)
    }
    catch (error) {
      console.error('[DEVICE-NOTIFICATION] ❌ Gagal menampilkan notifikasi:', error)
    }
  }

  // Watcher untuk mendeteksi perubahan status perangkat.
  const startDeviceNotificationWatcher = () => {
    if (import.meta.client) {
      let hasShownNotification = false

      watch(
        () => authStore.isNewDeviceDetected,
        (isDetected) => {
          if (isDetected && !hasShownNotification && !isPopupVisible.value) {
            console.log('[DEVICE-NOTIFICATION] 🚨 Perangkat baru terdeteksi, menampilkan notifikasi.')
            showDeviceNotification()
            hasShownNotification = true
          }
          else if (!isDetected) {
            // Reset flag jika perangkat sudah terdaftar, agar bisa muncul lagi di masa depan.
            hasShownNotification = false
            hideDeviceNotificationPopup()
          }
        },
        { immediate: true },
      )
    }
  }

  return {
    startDeviceNotificationWatcher,
    showDeviceNotification,
    isPopupVisible,
    hideDeviceNotificationPopup,
  }
}
