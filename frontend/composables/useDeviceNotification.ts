// composables/useDeviceNotification.ts

import { ref } from 'vue'

/**
 * DIOPTIMALKAN: File ini sekarang hanya berisi fungsi-fungsi minimal untuk
 * mempertahankan kompatibilitas dengan kode yang menggunakannya.
 * Logika notifikasi otomatis dihapus untuk mencegah notifikasi ganda dan race condition.
 * DeviceAuthPopup.vue sekarang sepenuhnya dikendalikan oleh state dari auth store.
 */

// State reaktif untuk visibilitas popup, tetap diekspor untuk mempertahankan kompatibilitas
const isPopupVisible = ref(false)

export function useDeviceNotification() {
  console.log('[DEVICE-NOTIFICATION] ℹ️ Menggunakan versi yang dioptimalkan, tanpa notifikasi otomatis')

  /**
   * Fungsi kosong untuk kompatibilitas
   */
  const startDeviceNotificationWatcher = () => {
    if (import.meta.client) {
      console.log('[DEVICE-NOTIFICATION] ℹ️ Watcher notifikasi otomatis dinonaktifkan untuk mencegah race condition')
    }
  }

  /**
   * Tetap menyediakan fungsi untuk menampilkan popup secara manual jika diperlukan
   */
  const showDeviceNotificationPopup = () => {
    isPopupVisible.value = true
  }

  /**
   * Tetap menyediakan fungsi untuk menyembunyikan popup
   */
  const hideDeviceNotificationPopup = () => {
    isPopupVisible.value = false
  }

  /**
   * Fungsi kosong untuk kompatibilitas
   */
  const showDeviceNotification = () => {
    console.log('[DEVICE-NOTIFICATION] ⚠️ Notifikasi dinonaktifkan - gunakan authStore.deviceAuthRequired untuk mengontrol popup')
  }

  return {
    startDeviceNotificationWatcher,
    showDeviceNotification,
    isPopupVisible,
    hideDeviceNotificationPopup,
  }
}
