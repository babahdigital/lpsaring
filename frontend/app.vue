<script setup lang="ts">
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { computed, onUnmounted, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import { Theme } from '@/types/enums'
// [PENYEMPURNAAN] Impor SnackbarWrapper sesuai dengan nama file yang ada
import SnackbarWrapper from '~/components/layout/SnackbarWrapper.vue'
import PromoFetcher from '~/components/promo/PromoFetcher.vue'

import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'

const { global } = useTheme()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()
const authStore = useAuthStore()
const route = useRoute()

initCore()

// Style untuk tema utama, tidak ada perubahan
const vAppStyle = computed(() => {
  if (global.current.value?.colors?.primary)
    return { '--v-global-theme-primary': hexToRgb(global.current.value.colors.primary) }

  return {}
})

// Logika sinkronisasi tema, tidak ada perubahan
watchEffect(() => {
  if (import.meta.client && settingsStore.isLoaded) {
    configStore.skin = settingsStore.skin
    configStore.appContentLayoutNav = settingsStore.layout
    configStore.appContentWidth = settingsStore.contentWidth

    const themeToApply = settingsStore.effectiveTheme
    configStore.theme = themeToApply
    global.name.value = themeToApply
  }
})

// Listener tema sistem, tidak ada perubahan
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
  onUnmounted(() => {
    darkModeMediaQuery.removeEventListener('change', handleSystemThemeChange)
  })
}

// [PENYEMPURNAAN] SEO diperkaya dengan meta description
useHead({
  title: computed(() => settingsStore.browserTitle),
  titleTemplate: (titleChunk) => {
    const appName = settingsStore.appName || 'Sobigidul'
    const browserTitle = settingsStore.browserTitle || 'Hotspot APP'

    if (titleChunk && titleChunk !== browserTitle)
      return `${titleChunk} By ${appName}`

    return browserTitle
  },
  meta: [
    {
      name: 'description',
      content: computed(() => settingsStore.appDescription || 'Aplikasi manajemen hotspot modern.'),
    },
  ],
})

// Kondisi untuk menampilkan komponen promo, tidak ada perubahan
const shouldShowPromoFetcher = computed(() => {
  return !route.path.startsWith('/admin')
})
</script>

<template>
  <VLocaleProvider :rtl="configStore.isAppRTL">
    <VApp :style="vAppStyle">
      <div
        v-if="!authStore.initialAuthCheckDone"
        class="initial-loading-screen"
      >
        <div class="loading-content">
          <VProgressCircular
            indeterminate
            color="primary"
            size="64"
          />
          <p class="mt-4 text-center text-disabled">
            Memverifikasi sesi...
          </p>
        </div>
      </div>

      <template v-else>
        <NuxtLayout>
          <NuxtPage />
        </NuxtLayout>

        <ClientOnly>
          <ScrollToTop />

          <SnackbarWrapper />

          <PromoFetcher v-if="shouldShowPromoFetcher" />
        </ClientOnly>
      </template>
    </VApp>
  </VLocaleProvider>
</template>

<style>
.initial-loading-screen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgb(var(--v-theme-surface));
}

.initial-loading-screen .loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>
