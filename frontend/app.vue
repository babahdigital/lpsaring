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

// PERBAIKAN: Sederhanakan `useHead` untuk menghilangkan fallback yang berkonflik.
// Sekarang ia hanya bergantung pada data dari settingsStore.
// Jika data di store kosong, Nuxt akan otomatis menggunakan nilai default dari `nuxt.config.ts`.
useHead({
  // Judul utama situs, diambil dari pengaturan.
  // Jika halaman tertentu mengatur judulnya sendiri, ini akan ditimpa oleh titleTemplate.
  title: computed(() => settingsStore.browserTitle),

  // Template untuk judul halaman.
  titleTemplate: (titleChunk) => {
    // Hanya gunakan template "Judul Halaman - Nama Aplikasi" jika nama aplikasi dari pengaturan ADA.
    if (settingsStore.appName && titleChunk) {
      return `${titleChunk} - ${settingsStore.appName}`;
    }
    
    // Jika tidak, kembalikan hanya judul halaman atau biarkan Nuxt yang menangani.
    return titleChunk || '';
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