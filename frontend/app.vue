<script setup lang="ts">
import { useTheme } from 'vuetify'
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { initConfigStore, useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useSettingsStore } from '~/store/settings'
// --- PERBAIKAN: Pastikan 'useDevice' TIDAK diimpor dari '#app' ---
import { useHead } from '#app'

const { global } = useTheme()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()

onMounted(() => {
  initConfigStore()
})

initCore()

useHead({
  title: computed(() => settingsStore.browserTitle),
  titleTemplate: (titleChunk) => {
    return titleChunk ? `${titleChunk} - ${settingsStore.appName}` : settingsStore.appName;
  }
})

// Panggilan ini akan bekerja karena auto-import Nuxt. TIDAK PERLU IMPORT MANUAL.
const { isMobile } = useDevice()
if (isMobile) {
  configStore.appContentLayoutNav = 'vertical'
}
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