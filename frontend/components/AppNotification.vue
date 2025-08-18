// components/AppNotification.vue
// PERBAIKAN TOTAL: Dirombak menggunakan VAlert untuk tampilan yang konsisten, andal, dan profesional.

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps({
  type: {
    type: String as () => 'success' | 'warning' | 'error' | 'info',
    required: true,
  },
  message: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['close'])

// VAlert menggunakan v-model untuk state buka/tutup.
// Kita gunakan variabel lokal untuk mengontrolnya.
const isVisible = ref(true)

// Jika parent component menyembunyikan notifikasi (misal: v-if),
// kita reset state internal agar bisa ditampilkan lagi lain kali.
watch(() => props.message, () => {
  isVisible.value = true
})

function handleClose() {
  isVisible.value = false
  // Beri tahu parent component bahwa notifikasi sudah ditutup.
  emit('close')
}
</script>

<template>
  <VAlert
    v-model="isVisible"
    :type="props.type"
    :text="props.message"
    variant="tonal"
    density="compact"
    closable
    class="text-start"
    @update:model-value="handleClose"
  />
</template>

<style scoped>
/* Tidak ada lagi style manual yang diperlukan. VAlert mengurus semuanya. */
/* Ini membuat komponen lebih bersih dan andal. */
</style>
