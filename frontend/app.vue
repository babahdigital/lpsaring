<script setup lang="ts">
import { useTheme } from 'vuetify'
import { watchEffect, computed, onUnmounted } from 'vue'
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useSettingsStore } from '~/store/settings'
import { Theme } from '@/types/enums';

// Inisialisasi store-store yang diperlukan
const { global } = useTheme()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()

// Panggil initCore untuk inisialisasi dasar
initCore()

// Buat computed property yang aman untuk style VApp.
const vAppStyle = computed(() => {
  if (global.current.value?.colors?.primary) {
    return { '--v-global-theme-primary': hexToRgb(global.current.value.colors.primary) }
  }
  return {}
})

// Logika sinkronisasi yang disempurnakan berdasarkan analisis Anda
watchEffect(() => {
  if (import.meta.client && settingsStore.isLoaded) {
    // 1. Terapkan skin, layout, dll.
    configStore.skin = settingsStore.skin
    configStore.appContentLayoutNav = settingsStore.layout
    configStore.appContentWidth = settingsStore.contentWidth

    // 2. Gunakan `effectiveTheme` dari store untuk menerapkan tema yang benar.
    const themeToApply = settingsStore.effectiveTheme
    configStore.theme = themeToApply
    global.name.value = themeToApply
  }
})

// PENYEMPURNAAN: Tambahkan listener untuk perubahan tema sistem (OS)
// Ini membuat tema 'system' benar-benar reaktif.
if (import.meta.client) {
  const darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

  const handleSystemThemeChange = (e: MediaQueryListEvent) => {
    if (settingsStore.theme === Theme.System) {
      const newTheme = e.matches ? Theme.Dark : Theme.Light
      configStore.theme = newTheme
      global.name.value = newTheme
    }
  }

  darkModeMediaQuery.addEventListener('change', handleSystemThemeChange)

  // Pastikan untuk membersihkan listener saat komponen tidak lagi digunakan
  onUnmounted(() => {
    darkModeMediaQuery.removeEventListener('change', handleSystemThemeChange)
  })
}


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
    <VApp :style="vAppStyle">
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