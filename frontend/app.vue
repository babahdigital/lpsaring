<script setup lang="ts">
import { useTheme } from 'vuetify'
import { watchEffect } from 'vue'
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

// PENYEMPURNAAN: Sinkronisasi Otomatis Tema dari Database
// watchEffect akan berjalan setiap kali nilai di dalam settingsStore berubah.
// Ini memastikan bahwa tema yang disimpan di database akan langsung diterapkan.
watchEffect(() => {
  // Hanya jalankan jika pengaturan sudah dimuat dari database
  if (settingsStore.isLoaded) {
    configStore.theme = settingsStore.theme
    configStore.skin = settingsStore.skin
    configStore.appContentLayoutNav = settingsStore.layout
    configStore.appContentWidth = settingsStore.contentWidth
  }
})

// Logika `useHead` yang sudah benar untuk menangani judul
useHead({
  title: computed(() => settingsStore.browserTitle),
  titleTemplate: (titleChunk) => {
    const appName = settingsStore.appName || 'Sobigidul';
    const browserTitle = settingsStore.browserTitle || 'Hotspot APP';

    if (titleChunk && titleChunk !== browserTitle) {
      return `${titleChunk} By ${appName}`;
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
