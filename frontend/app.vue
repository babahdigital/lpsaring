<script setup lang="ts">
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { initConfigStore, useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useTheme } from 'vuetify'
// Import useDevice jika belum (mungkin sudah auto-imported oleh Nuxt)
// import { useDevice } from '#imports';

onMounted(() => {
  initConfigStore()
})

const { global } = useTheme()

// ℹ️ Sync current theme with initial loader theme
initCore()
initConfigStore()

const configStore = useConfigStore()
// Pastikan useDevice tersedia (mungkin perlu didefinisikan atau diimpor jika tidak auto-imported)
const { isMobile } = useDevice ? useDevice() : { isMobile: false } // Beri nilai default jika useDevice tidak ada
if (isMobile)
  configStore.appContentLayoutNav = 'vertical'
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
    </VApp>
  </VLocaleProvider>
</template>
