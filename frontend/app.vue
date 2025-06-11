<script setup lang="ts">
import { useTheme } from 'vuetify'
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useSettingsStore } from '~/store/settings'

// Inisialisasi store-store yang diperlukan
const { global } = useTheme()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()

// Panggil initCore untuk inisialisasi dasar
initCore()

// PERBAIKAN: Logika `useHead` disempurnakan untuk menangani semua kasus judul.
useHead({
  // Menetapkan judul default untuk seluruh aplikasi.
  // Ini akan menjadi nilai `titleChunk` pada halaman yang tidak memiliki `useHead` sendiri.
  title: computed(() => settingsStore.browserTitle),

  // Template ini akan memformat judul akhir.
  titleTemplate: (titleChunk) => {
    // Ambil nama aplikasi dan judul browser dari store, berikan fallback jika kosong.
    const appName = settingsStore.appName || 'Sobigidul';
    const browserTitle = settingsStore.browserTitle || 'Hotspot App';

    // Jika ada judul halaman spesifik (titleChunk tidak kosong dan berbeda dari judul default),
    // maka format menjadi "Judul Halaman - Nama Aplikasi".
    if (titleChunk && titleChunk !== browserTitle) {
      return `${titleChunk} By ${appName}`;
    }
    
    // Jika tidak ada judul halaman spesifik, cukup kembalikan judul browser default.
    // Ini akan menjadi judul untuk halaman utama dan halaman lain tanpa `useHead`.
    return browserTitle;
  }
})
</script>

<template>
  <VLocaleProvider :rtl="configStore.isAppRTL">
    <VApp :style="`--v-global-theme-primary: ${hexToRgb(global.current.value.colors.primary)}`">
      <NuxtLayout>
        <NuxtPage />
      </NuxtLayout>

      <ClientOnly>
        <ScrollToTop />
        <template #placeholder />
      </ClientOnly>
      
      <AppSnackbar />
    </VApp>
  </VLocaleProvider>
</template>