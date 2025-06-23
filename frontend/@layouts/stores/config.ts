import type { Ref } from 'vue'
import { useCookie } from '#app'
import { injectionKeyIsVerticalNavHovered } from '@layouts/symbols'
import { _setDirAttr } from '@layouts/utils'
import { layoutConfig } from '@themeConfig'
import { useMediaQuery, useWindowScroll } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, inject, ref, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { AppContentLayoutNav, NavbarType } from '@/types/enums'

export const namespaceConfig = (str: string) => `${layoutConfig.app.title}-${str}`

export function cookieRef<T>(key: string, defaultValue: T) {
  return useCookie<T>(namespaceConfig(key), { default: () => defaultValue })
}

export const useLayoutConfigStore = defineStore('layoutConfig', () => {
  const route = useRoute()

  // Panggil composables yang menggunakan inject/lifecycle hooks di level atas
  const { y: windowScrollY } = useWindowScroll()
  const isVerticalNavHoveredStore = inject(injectionKeyIsVerticalNavHovered, ref(false))

  // State Refs
  const navbarType = ref(layoutConfig.navbar.type)
  const isNavbarBlurEnabled = cookieRef('isNavbarBlurEnabled', layoutConfig.navbar.navbarBlur)
  const isVerticalNavCollapsed = cookieRef('isVerticalNavCollapsed', layoutConfig.verticalNav.isVerticalNavCollapsed)
  const appContentWidth = cookieRef('appContentWidth', layoutConfig.app.contentWidth)
  const appContentLayoutNav = ref(layoutConfig.app.contentLayoutNav)
  const horizontalNavType = ref(layoutConfig.horizontalNav.type)
  const horizontalNavPopoverOffset = ref(layoutConfig.horizontalNav.popoverOffset)
  const footerType = ref(layoutConfig.footer.type)
  const breakpointRefValue = ref(false)
  const isAppRTL = ref(layoutConfig.app.isRTL)

  // Watchers
  watch(appContentLayoutNav, (val) => {
    if (val === AppContentLayoutNav.Horizontal) {
      if (navbarType.value === NavbarType.Hidden)
        navbarType.value = NavbarType.Sticky
      isVerticalNavCollapsed.value = false
    }
  })

  watchEffect(() => {
    breakpointRefValue.value = useMediaQuery(
      `(max-width: ${layoutConfig.app.overlayNavFromBreakpoint}px)`,
    ).value
  })

  watch(isAppRTL, (val) => {
    _setDirAttr(val ? 'rtl' : 'ltr')
  })

  // Computed Properties
  const isLessThanOverlayNavBreakpoint = computed({
    get() {
      return breakpointRefValue.value
    },
    set(value) {
      breakpointRefValue.value = value
    },
  })

  const _layoutClasses = computed(() => {
    return [
      `layout-nav-type-${appContentLayoutNav.value}`,
      `layout-navbar-${navbarType.value}`,
      `layout-footer-${footerType.value}`,
      {
        'layout-vertical-nav-collapsed':
          isVerticalNavCollapsed.value
          && appContentLayoutNav.value === AppContentLayoutNav.Vertical
          && !isLessThanOverlayNavBreakpoint.value,
      },
      { [`horizontal-nav-${horizontalNavType.value}`]: appContentLayoutNav.value === AppContentLayoutNav.Horizontal },
      `layout-content-width-${appContentWidth.value}`,
      { 'layout-overlay-nav': isLessThanOverlayNavBreakpoint.value },
      { 'layout-navbar-hidden': navbarType.value === NavbarType.Hidden },
      { 'layout-navbar-sticky': navbarType.value === NavbarType.Sticky && windowScrollY.value < (layoutConfig.navbar.stickOnScroll ?? 100) },
      { 'layout-navbar-static': navbarType.value === NavbarType.Static },
      // Diperbaiki: Hapus referensi ke NavbarType.Floating
      { 'layout-vertical-nav-navbar-is-contained': layoutConfig.navbar.isContentWidthWide && appContentLayoutNav.value === AppContentLayoutNav.Vertical },
      { 'layout-horizontal-nav-navbar-is-contained': layoutConfig.navbar.isContentWidthWide && appContentLayoutNav.value === AppContentLayoutNav.Horizontal },
      { 'layout-footer-is-contained': layoutConfig.footer.isContentWidthWide },
      { 'layout-footer-hidden': footerType.value === 'hidden' },
      // Diperbaiki: Gunakan nilai langsung dari konfigurasi
      { 'layout-vertical-nav-mini': isVerticalNavCollapsed.value && !isVerticalNavHoveredStore.value && !isLessThanOverlayNavBreakpoint.value },
      { 'window-scrolled': windowScrollY.value > 0 },
      route.meta.layoutWrapperClasses ? route.meta.layoutWrapperClasses : null,
    ]
  })

  // Methods
  const isVerticalNavMini = (isVerticalNavHoveredPassed: Ref<boolean> | null = null) => {
    const isVerticalNavHovered = isVerticalNavHoveredPassed || isVerticalNavHoveredStore
    return computed(() => isVerticalNavCollapsed.value && !isVerticalNavHovered.value && !isLessThanOverlayNavBreakpoint.value)
  }

  return {
    // Refs
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
    windowScrollY,

    // Computed
    _layoutClasses,

    // Method
    isVerticalNavMini,
  }
})
