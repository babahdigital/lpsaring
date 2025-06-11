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

// Gunakan useHead untuk mengatur judul halaman secara dinamis
// Data akan reaktif dan otomatis update saat nilai di settingsStore berubah
useHead({
  title: computed(() => settingsStore.browserTitle || 'Portal Hotspot'),
  titleTemplate: (titleChunk) => {
    // Format judul: "Judul Halaman - Nama Aplikasi"
    // atau hanya "Nama Aplikasi" jika tidak ada judul spesifik
    return titleChunk && titleChunk !== settingsStore.browserTitle
      ? `${titleChunk} - ${settingsStore.appName || 'Hotspot APP'}`
      : settingsStore.browserTitle || 'Portal Hotspot';
  }
})
</script>

<template>
  <VLocaleProvider :rtl="configStore.isAppRTL">
    <!-- 
      Style ini diperlukan oleh Vuetify untuk tema dinamis, jangan dihapus.
    -->
    <VApp :style="`--v-global-theme-primary: ${hexToRgb(global.current.value.colors.primary)}`">
      <!-- 
        NuxtLayout dan NuxtPage akan menangani rendering halaman utama
        dan halaman maintenance secara otomatis berdasarkan rute.
        Tidak perlu logika v-if/v-else di sini.
      -->
      <NuxtLayout>
        <NuxtPage />
      </NuxtLayout>

      <!-- Komponen tambahan yang hanya berjalan di client -->
      <ClientOnly>
        <ScrollToTop />
        <template #placeholder />
      </ClientOnly>
      
      <!-- Komponen untuk menampilkan notifikasi snackbar global -->
      <AppSnackbar />
    </VApp>
  </VLocaleProvider>
</template>