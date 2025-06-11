<script setup lang="ts">
import { useTheme } from 'vuetify'
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { initConfigStore, useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { useSettingsStore } from '~/store/settings'
import { useMaintenanceStore } from '~/store/maintenance' // <-- Tambahkan impor maintenance store
import { useHead, useNuxtApp } from '#app'

const { global } = useTheme()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()
const maintenanceStore = useMaintenanceStore() // <-- Tambahkan ini
const nuxtApp = useNuxtApp()

onMounted(() => {
  initConfigStore()
  
  // PERBAIKAN: Pindahkan logika mobile ke sini untuk menghindari error SSR
  if (process.client) {
    const { isMobile } = useDevice()
    if (isMobile) {
      configStore.appContentLayoutNav = 'vertical'
    }
  }
})

initCore()

useHead({
  title: computed(() => settingsStore.browserTitle || 'Hotspot App'),
  titleTemplate: (titleChunk) => {
    return titleChunk 
      ? `${titleChunk} Oleh ${settingsStore.appName || 'SOBIDIGUL'}` 
      : (settingsStore.appName || 'Portal Hotspot');
  }
})

// PERBAIKAN: Tambahkan pengecekan maintenance mode
watchEffect(() => {
  if (maintenanceStore.isActive) {
    // Redirect ke halaman maintenance jika tidak di halaman admin
    const currentPath = nuxtApp.$router.currentRoute.value.path
    const isAdminPath = currentPath.startsWith('/admin')
    
    if (!isAdminPath && currentPath !== '/maintenance') {
      nuxtApp.$router.replace('/maintenance')
    }
  }
})
</script>

<template>
  <VLocaleProvider :rtl="configStore.isAppRTL">
    <VApp :style="`--v-global-theme-primary: ${hexToRgb(global.current.value.colors.primary)}`">
      <!-- PERBAIKAN: Sembunyikan konten jika maintenance aktif dan bukan admin -->
      <template v-if="!maintenanceStore.isActive || $route.path.startsWith('/admin')">
        <NuxtLayout>
          <NuxtPage />
        </NuxtLayout>

        <ClientOnly>
          <ScrollToTop />
          <template #placeholder />
        </ClientOnly>
        <AppSnackbar />
      </template>
      
      <!-- Tampilkan halaman maintenance jika mode aktif -->
      <template v-else>
        <NuxtPage page-key="maintenance" :page-path="'/maintenance'" />
      </template>
    </VApp>
  </VLocaleProvider>
</template>