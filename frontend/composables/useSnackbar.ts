// frontend/composables/useSnackbar.ts
// PERBAIKAN: Hanya mengizinkan satu pesan pada satu waktu.

import { readonly, ref } from 'vue'

interface SnackbarMessage {
  id: number
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  text: string
  timeout?: number
}

const messages = ref<SnackbarMessage[]>([])

export function useSnackbar() {
  function remove(id: number) {
    const index = messages.value.findIndex(m => m.id === id)
    if (index > -1)
      messages.value.splice(index, 1)
  }

  function add(message: Omit<SnackbarMessage, 'id'>) {
    // [PERUBAHAN KUNCI] Hapus semua pesan yang ada sebelum menambahkan yang baru.
    messages.value = []

    const id = Date.now() + Math.random()
    const timeout: number = message.timeout === 0
      ? 0
      : (typeof message.timeout === 'number' ? message.timeout : 4000) // Default 4 detik

    // Gunakan nextTick untuk memastikan array sudah kosong sebelum push
    nextTick(() => {
      messages.value.push({ id, ...message })
    })

    if (timeout > 0)
      setTimeout(() => remove(id), timeout)
  }

  return {
    messages: readonly(messages),
    add,
    remove,
  }
}
