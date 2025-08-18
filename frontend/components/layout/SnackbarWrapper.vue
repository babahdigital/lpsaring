// frontend/components/SnackbarWrapper.vue
// PERBAIKAN: Menambahkan fungsi handleClose yang aman untuk mencegah race condition.
// FIXED: Menggunakan custom transition yang kompatibel dengan Nuxt 4

<script lang="ts" setup>
import { computed } from 'vue'

import FadeTransition from '@/components/transitions/FadeTransition.vue'
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()

// Peta SVG untuk setiap jenis notifikasi
const svgIconMap = {
  success: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" /><path d="M9 12l2 2l4 -4" /></svg>',
  error: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0" /><path d="M12 8v4" /><path d="M12 16h.01" /></svg>',
  info: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0" /><path d="M12 9h.01" /><path d="M11 12h1v4h1" /></svg>',
  warning: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 9v4" /><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z" /><path d="M12 16h.01" /></svg>',
}

const colorMap = {
  success: 'success-darken-2',
  error: 'error-darken-2',
  info: 'info-darken-2',
  warning: 'warning',
}

const currentMessage = computed(() => messages.value.length > 0 ? messages.value[0] : null)

const iconColor = computed(() => {
  return currentMessage.value?.type === 'warning' ? '#333333' : 'white'
})

const buttonColor = computed(() => {
  return currentMessage.value?.type === 'warning' ? 'grey-darken-4' : 'white'
})

// [PERBAIKAN KUNCI] Membuat fungsi penanganan yang aman
function handleClose() {
  // Hanya panggil 'remove' jika 'currentMessage' masih memiliki data.
  // Ini mencegah error jika tombol diklik saat transisi keluar.
  if (currentMessage.value) {
    remove(currentMessage.value.id)
  }
}
</script>

<template>
  <FadeTransition>
    <div
      v-if="currentMessage"
      :key="currentMessage.id"
      class="fullscreen-snackbar-overlay"
    >
      <VCard
        :color="colorMap[currentMessage.type]"
        variant="elevated"
        class="pa-6 text-center"
        width="90%"
        max-width="400px"
        elevation="12"
        rounded="xl"
      >
        <div
          class="snackbar-icon-container mb-4"
          :style="{ color: iconColor }"
          v-html="svgIconMap[currentMessage.type]"
        />

        <h2 class="text-h5 font-weight-bold mb-2 snackbar-text-glow">
          {{ currentMessage.title }}
        </h2>
        <p
          class="text-body-1 mb-6 snackbar-text-glow"
          v-html="currentMessage.text"
        />

        <VBtn
          variant="tonal"
          :color="buttonColor"
          block
          @click="handleClose"
        >
          Tutup
        </VBtn>
      </VCard>
    </div>
  </FadeTransition>
</template>

<style scoped>
.fullscreen-snackbar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 9999;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(5px);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 16px;
}

.snackbar-icon-container {
  line-height: 1;
  filter: drop-shadow(0px 1px 2px rgba(0, 0, 0, 0.7));
}

.snackbar-text-glow {
  text-shadow: 0px 1px 3px rgba(0, 0, 0, 0.6);
}
</style>
