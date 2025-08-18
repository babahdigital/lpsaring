<script lang="ts" setup>
import { computed, defineAsyncComponent, onMounted, onUnmounted } from 'vue'

import { AppContentLayoutNav } from '@/types/enums'
import { useSettingsStore } from '~/store/settings'

// Remove NewDeviceDialog as we're using alert system instead
const DefaultLayoutWithHorizontalNav = defineAsyncComponent(() => import('@/layouts/components/DefaultLayoutWithHorizontalNav.vue'))
const DefaultLayoutWithVerticalNav = defineAsyncComponent(() => import('@/layouts/components/DefaultLayoutWithVerticalNav.vue'))

const settingsStore = useSettingsStore()

const layoutClasses = computed(() => {
  const s = settingsStore.settings
  const classes = [
    s.SKIN ? `skin--${s.SKIN}` : '',
    (s.APP_CONTENT_WIDTH || s.CONTENT_WIDTH) ? `content-width-${s.APP_CONTENT_WIDTH || s.CONTENT_WIDTH}` : '',
    s.APP_CONTENT_LAYOUT_NAV ? `layout-nav-type-${s.APP_CONTENT_LAYOUT_NAV}` : '',
    s.FOOTER_TYPE ? `footer-type-${s.FOOTER_TYPE}` : '',
    s.NAVBAR_TYPE ? `navbar-type-${s.NAVBAR_TYPE}` : '',
  ].filter(Boolean)

  // Enhanced debug logging untuk melihat classes yang diterapkan
  console.log('🎨 Layout classes applied:', classes)
  console.log('🔧 Settings store content:', s)
  console.log('🔍 NAVBAR_TYPE specifically:', s.NAVBAR_TYPE)

  return classes
})

// Device sync and client detection is now handled by:
// 1. Middleware (04-device-authorization.global.ts)
// 2. useClientDetection composable
// 3. Auth store sync methods
// Layout only needs to handle UI layout, not device detection

onMounted(() => {
  console.log('[LAYOUT] Default layout mounted - device sync handled by middleware')
})

onUnmounted(() => {
  console.log('[LAYOUT] Default layout unmounted')
})
</script>

<template>
  <div :class="layoutClasses">
    <Component
      :is="(settingsStore.settings.APP_CONTENT_LAYOUT_NAV || settingsStore.settings.VUEXY_APP_CONTENT_LAYOUT_NAV) === AppContentLayoutNav.Horizontal
        ? DefaultLayoutWithHorizontalNav
        : DefaultLayoutWithVerticalNav"
    >
      <slot />
    </Component>

    <!-- NewDeviceDialog removed - using alert system instead -->
  </div>
</template>

<style lang="scss">
@use "@layouts/styles/default-layout";
</style>
