<script setup lang="ts">
import { useTheme } from 'vuetify'
import { watchEffect } from 'vue'
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useSettingsStore } from '~/store/settings'

// Inisialisasi store-store yang diperlukan
const { global } = useTheme() // Menggunakan 'global' dari useTheme
const configStore = useConfigStore()
const settingsStore = useSettingsStore()

// Panggil initCore untuk inisialisasi dasar
initCore()

// PENYEMPURNAAN: Sinkronisasi Otomatis Tema dari Database
watchEffect(() => {
  if (settingsStore.isLoaded) {
    // 1. Terapkan pengaturan ke configStore (untuk skin, layout, dll.)
    configStore.theme = settingsStore.theme
    configStore.skin = settingsStore.skin
    configStore.appContentLayoutNav = settingsStore.layout
    configStore.appContentWidth = settingsStore.contentWidth

    // 2. PERBAIKAN UTAMA: Perintahkan Vuetify untuk mengubah tema global.
    // Ini adalah langkah kunci yang akan mengubah warna aplikasi (terang/gelap).
    global.name.value = configStore.theme
  }
})

// Logika `useHead` yang sudah benar untuk menangani judul
useHead({
  title: computed(() => settingsStore.browserTitle),
  titleTemplate: (titleChunk) => {
    const appName = settingsStore.appName || 'Sobigidul';
    const browserTitle = settingsStore.browserTitle || 'Hotspot APP';

    if (titleChunk && titleChunk !== browserTitle) {
      return `${titleChunk} - ${appName}`;
    }
    
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