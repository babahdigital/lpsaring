// @layouts/stores/config.ts - VERSI SEMPURNA

import type { Ref } from 'vue'

import { AppContentLayoutNav, NavbarType } from '@layouts/enums'
import { injectionKeyIsVerticalNavHovered } from '@layouts/symbols'
import { _setDirAttr } from '@layouts/utils'
import { layoutConfig } from '@themeConfig'
import { useMediaQuery, useWindowScroll } from '@vueuse/core'
import { useCookie } from '#app'
// [PERBAIKAN 1] Tambahkan impor yang hilang untuk defineStore dan lainnya
import { defineStore } from 'pinia'
import { computed, inject, ref, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'

// Helper yang sudah ada
export const namespaceConfig = (str: string) => `${layoutConfig.app.title}-${str}`
export function cookieRef<T>(key: string, defaultValue: T) {
  return useCookie<T>(namespaceConfig(key), { default: () => defaultValue })
}

// Definisikan store dengan impor yang sudah benar
export const useLayoutConfigStore = defineStore('layoutConfig', () => {
  const route = useRoute()

  // --- State dari Layout Config ---
  const navbarType = ref(layoutConfig.navbar.type)
  const isNavbarBlurEnabled = cookieRef('isNavbarBlurEnabled', layoutConfig.navbar.navbarBlur)
  const isVerticalNavCollapsed = cookieRef('isVerticalNavCollapsed', layoutConfig.verticalNav.isVerticalNavCollapsed)
  const appContentWidth = cookieRef('appContentWidth', layoutConfig.app.contentWidth)
  const appContentLayoutNav = ref(layoutConfig.app.contentLayoutNav)
  const horizontalNavType = ref(layoutConfig.horizontalNav.type)
  const horizontalNavPopoverOffset = ref(layoutConfig.horizontalNav.popoverOffset)
  const footerType = ref(layoutConfig.footer.type)
  const isAppRTL = ref(false)

  // [PERBAIKAN 2] Logika `useWindowScroll` dibuat aman dari error lifecycle
  // Kita inisialisasi sebagai ref biasa, lalu hanya aktifkan di sisi client.
  const windowScrollY = ref(0)
  if (import.meta.client) {
    const { y } = useWindowScroll()
    // Gunakan watch untuk mengupdate ref lokal kita secara reaktif
    watch(y, (value) => {
      windowScrollY.value = value
    }, { immediate: true })
  }

  // --- Watchers ---
  watch(appContentLayoutNav, (val) => {
    if (val === AppContentLayoutNav.Horizontal) {
      if (navbarType.value === NavbarType.Hidden)
        navbarType.value = NavbarType.Sticky
      isVerticalNavCollapsed.value = false
    }
  })

  watch(isAppRTL, (val) => {
    _setDirAttr(val ? 'rtl' : 'ltr')
  })

  // --- Computed Properties ---
  const breakpointRef = ref(false)
  watchEffect(() => {
    breakpointRef.value = useMediaQuery(
      `(max-width: ${layoutConfig.app.overlayNavFromBreakpoint}px)`,
    ).value
  })

  const isLessThanOverlayNavBreakpoint = computed({
    get: () => breakpointRef.value,
    set: value => breakpointRef.value = value,
  })

  const _layoutClasses = computed(() => [
    `layout-nav-type-${appContentLayoutNav.value}`,
    `layout-navbar-${navbarType.value}`,
    `layout-footer-${footerType.value}`,
    { 'layout-vertical-nav-collapsed': isVerticalNavCollapsed.value && appContentLayoutNav.value === 'vertical' && !isLessThanOverlayNavBreakpoint.value },
    { [`horizontal-nav-${horizontalNavType.value}`]: appContentLayoutNav.value === 'horizontal' },
    `layout-content-width-${appContentWidth.value}`,
    { 'layout-overlay-nav': isLessThanOverlayNavBreakpoint.value },
    { 'window-scrolled': windowScrollY.value > 0 }, // Menggunakan ref yang aman
    route.meta.layoutWrapperClasses ? route.meta.layoutWrapperClasses : null,
  ])

  const isVerticalNavMini = (isVerticalNavHovered: Ref<boolean> | null = null) => {
    const isVerticalNavHoveredLocal = isVerticalNavHovered || inject(injectionKeyIsVerticalNavHovered) || ref(false)
    return computed(() => isVerticalNavCollapsed.value && !isVerticalNavHoveredLocal.value && !isLessThanOverlayNavBreakpoint.value)
  }

  return {
    appContentWidth,
    appContentLayoutNav,
    navbarType,
    isNavbarBlurEnabled,
    isVerticalNavCollapsed,
    horizontalNavType,
    horizontalNavPopoverOffset,
    footerType,
    isLessThanOverlayNavBreakpoint,
    isAppRTL,
    _layoutClasses,
    isVerticalNavMini,
  }
})
