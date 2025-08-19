<script setup lang="ts">
// Import components and utilities
import ScrollToTop from '@core/components/ScrollToTop.vue'
import initCore from '@core/initCore'
import { useConfigStore } from '@core/stores/config'
import { hexToRgb } from '@core/utils/colorConverter'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'

import { Theme } from '@/types/enums'
// [PERBAIKAN] Impor komponen popup otorisasi perangkat
import DeviceAuthPopup from '~/components/layout/DeviceAuthPopup.vue'
// Impor komponen dan store lokal
import SnackbarWrapper from '~/components/layout/SnackbarWrapper.vue'
import PromoFetcher from '~/components/promo/PromoFetcher.vue'
import { useDeviceNotification } from '~/composables/useDeviceNotification'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'

const { global } = useTheme()
const route = useRoute()
const configStore = useConfigStore()
const settingsStore = useSettingsStore()
const authStore = useAuthStore()

// State lokal untuk mengontrol visibilitas loader secara andal.
const showLoader = ref(true)

// Initialize core before checking data readiness
initCore()

// Juga pastikan auth diinisialisasi
onMounted(async () => {
  if (!authStore.isAuthCheckDone) {
    await authStore.initializeAuth()
  }

  // Initialize device notification watcher
  const { startDeviceNotificationWatcher } = useDeviceNotification()
  startDeviceNotificationWatcher()
})

// Force show loader for at least 2 seconds for testing
if (process.dev) {
  onMounted(() => {
    console.log('App.vue mounted, showLoader initial state:', showLoader.value)
  })
}

// Hide the initial loader once Vue is mounted
onMounted(() => {
  console.log('App.vue mounted, starting loader management')

  // Hide initial loader setelah Vue app siap
  nextTick(() => {
    const globalWindow = window as any
    if (typeof window !== 'undefined' && globalWindow.hideInitialLoader) {
      console.log('Calling hideInitialLoader from app.vue')
      // Delay sedikit untuk memastikan halaman sudah render
      setTimeout(() => {
        globalWindow.hideInitialLoader?.()
      }, 300)
    }
  })
})

// Kondisi logis kapan aplikasi siap (tidak berubah).
const isDataReady = computed(() => authStore.isAuthCheckDone && settingsStore.isLoaded)

// Function untuk apply settings ke config store
function applySettingsToConfig() {
  // Apply settings dari backend ke store konfigurasi
  if (!settingsStore.hasSettings) {
    console.log('Settings not loaded yet, skipping apply')
    return
  }

  const settings = settingsStore.settings

  // Clear any cached settings that might interfere
  if (process.client) {
    // Clear settings cache to ensure fresh start
    localStorage.removeItem('settings')
    sessionStorage.removeItem('settings')
    console.log('🔧 Cleared settings cache for fresh starter-kit style layout')
  }

  console.log('Applying settings to config store:', settings)

  // Skin setting
  if (settings.SKIN) {
    const skinValue = (settings.SKIN as string).toLowerCase()
    console.log('Applying skin:', skinValue)
    configStore.skin = skinValue as any
  }
  else if (settings.VUEXY_SKIN) {
    const skinValue = (settings.VUEXY_SKIN as string).toLowerCase()
    console.log('Applying skin (with prefix):', skinValue)
    configStore.skin = skinValue as any
  }
  else {
    console.log('No skin setting found, using default: default')
    configStore.skin = 'default' // Match starter kit
  }

  if (settings.APP_CONTENT_LAYOUT_NAV) {
    const navValue = (settings.APP_CONTENT_LAYOUT_NAV as string).toLowerCase()
    console.log('Applying layout nav:', navValue)
    configStore.appContentLayoutNav = navValue as any
  }
  else if (settings.VUEXY_APP_CONTENT_LAYOUT_NAV) {
    const navValue = (settings.VUEXY_APP_CONTENT_LAYOUT_NAV as string).toLowerCase()
    console.log('Applying layout nav (with prefix):', navValue)
    configStore.appContentLayoutNav = navValue as any
  }
  else {
    console.log('No layout nav setting found, using default: horizontal')
    configStore.appContentLayoutNav = 'horizontal'
  }

  if (settings.APP_CONTENT_WIDTH) {
    const widthValue = (settings.APP_CONTENT_WIDTH as string).toLowerCase()
    console.log('Applying content width:', widthValue)
    configStore.appContentWidth = widthValue as any
  }
  else if (settings.VUEXY_APP_CONTENT_WIDTH) {
    const widthValue = (settings.VUEXY_APP_CONTENT_WIDTH as string).toLowerCase()
    console.log('Applying content width (with prefix):', widthValue)
    configStore.appContentWidth = widthValue as any
  }
  else {
    console.log('No content width setting found, using default: boxed')
    configStore.appContentWidth = 'boxed' // Respect your preference for boxed
  }

  // Theme setting
  if (settings.THEME && settings.THEME !== Theme.System) {
    const themeValue = (settings.THEME as string).toLowerCase()
    console.log('Applying theme:', themeValue)
    configStore.theme = themeValue as any
  }
  else if (settings.VUEXY_THEME && settings.VUEXY_THEME !== Theme.System) {
    const themeValue = (settings.VUEXY_THEME as string).toLowerCase()
    console.log('Applying theme (with prefix):', themeValue)
    configStore.theme = themeValue as any
  }
  else {
    console.log('No theme setting found, using default: system')
    configStore.theme = 'system' // Match starter kit default
  }
}

// Call function when settings are loaded
watch(() => settingsStore.hasSettings, (hasSettings) => {
  if (hasSettings) {
    applySettingsToConfig()
  }
}, { immediate: true })

// Watcher untuk mengontrol kapan loader disembunyikan.
let loaderTimeout: ReturnType<typeof setTimeout> | null = null
const MIN_LOADER_TIME = 1500
let loaderStart = Date.now()

onMounted(() => {
  // [PENYEMPURNAAN] Hanya inisialisasi waktu mulai loader.
  // Pengaturan class dan style kini sepenuhnya ditangani oleh watcher di bawah
  // dan pengaturan di nuxt.config.ts untuk mencegah FOUC.
  loaderStart = Date.now()
})

watch(isDataReady, (ready) => {
  console.log('[APP] isDataReady changed:', ready)
  if (ready) {
    const elapsed = Date.now() - loaderStart
    const remaining = MIN_LOADER_TIME - elapsed
    console.log('[APP] Data ready, elapsed:', elapsed, 'remaining:', remaining)

    if (loaderTimeout)
      clearTimeout(loaderTimeout)
    loaderTimeout = setTimeout(() => {
      console.log('[APP] Hiding application loader')
      showLoader.value = false
    }, remaining > 0 ? remaining : 0)
  }
}, { immediate: true })

// Sinkronisasi class skin/theme pada body setelah settings diterima
watch(
  () => [configStore.skin, configStore.theme],
  ([skin, theme]) => {
    // Hapus semua skin/theme class lama
    document.body.classList.forEach((cls) => {
      if (cls.startsWith('skin--') || cls.startsWith('theme--'))
        document.body.classList.remove(cls)
    })
    // Tambahkan skin/theme baru
    document.body.classList.add(`skin--${skin || 'bordered'}`)
    document.body.classList.add(`theme--${theme || 'dark'}`)
    // Set background sesuai theme, ini akan menimpa style dari nuxt.config.ts jika diperlukan
    if ((theme || 'dark') === 'dark') {
      document.body.style.background = '#181818'
    }
    else {
      document.body.style.background = '#fff'
    }
  },
  { immediate: true },
)

// Debug watcher untuk showLoader
if (process.dev) {
  watch(showLoader, (show) => {
    console.log('Loader visibility changed:', show)
  }, { immediate: true })
}

// Hide window scrollbar while loader is active
watch(showLoader, (show) => {
  document.body.style.overflow = show ? 'hidden' : ''
}, { immediate: true })

const vAppStyle = computed(() => {
  const primaryColor = global.current.value?.colors?.primary
  const rgbValue = primaryColor ? hexToRgb(primaryColor) : null

  return rgbValue
    ? { '--v-global-theme-primary': rgbValue }
    : {}
})

useHead({
  titleTemplate: '%s - sobigidul',
  title: 'sobigidul',
})

const shouldShowPromoFetcher = computed(
  () => !route.path.startsWith('/admin') && !route.path.startsWith('/maintenance'),
)
</script>

<template>
  <VLocaleProvider :rtl="configStore.isAppRTL">
    <VApp :style="vAppStyle">
      <ErrorBoundary>
        <NuxtLayout>
          <div :style="{ display: showLoader ? 'none' : 'block' }">
            <NuxtPage />
          </div>
        </NuxtLayout>

        <ScrollToTop />
        <SnackbarWrapper />
        <!-- PERBAIKAN: Tampilkan DeviceAuthPopup hanya ketika user terautentikasi -->
        <DeviceAuthPopup v-if="authStore.isLoggedIn" />
        <PromoFetcher v-if="shouldShowPromoFetcher && !showLoader" />
        <NetworkStatusIndicator />
      </ErrorBoundary>
    </VApp>
  </VLocaleProvider>
</template>

<style>
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
