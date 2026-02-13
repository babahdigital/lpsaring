// frontend/composables/useSnackbar.ts

import { readonly, ref } from 'vue'

// Definisikan struktur dari sebuah pesan snackbar
interface SnackbarMessage {
  id: number
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  text: string
  timeout?: number
}

// State reaktif untuk menyimpan semua pesan snackbar yang aktif
const messages = ref<SnackbarMessage[]>([])

export function useSnackbar() {
  /**
   * Menghapus pesan dari antrian snackbar berdasarkan ID-nya.
   * @param id - ID unik dari pesan yang akan dihapus.
   */
  function remove(id: number) {
    const index = messages.value.findIndex(m => m.id === id)
    if (index > -1)
      messages.value.splice(index, 1)
  }

  /**
   * Menambahkan pesan baru ke dalam antrian snackbar.
   * @param message - Objek pesan yang berisi tipe, judul, dan teks.
   */
  function add(message: Omit<SnackbarMessage, 'id'>) {
    const id = Date.now() + Math.random()
    const timeoutValue = message.timeout
    const timeout = timeoutValue === 0
      ? 0
      : (typeof timeoutValue === 'number' && Number.isFinite(timeoutValue) ? timeoutValue : 5000) // default 5 detik, 0 berarti tidak hilang otomatis

    messages.value.push({ id, ...message })

    if (timeout > 0)
      setTimeout(() => remove(id), timeout)
  }

  return {
    // Berikan akses baca saja ke daftar pesan agar tidak bisa diubah dari luar
    messages: readonly(messages),
    add,
    remove,
  }
}
