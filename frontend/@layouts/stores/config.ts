import { AppContentLayoutNav, NavbarType } from '@layouts/enums'
import { injectionKeyIsVerticalNavHovered } from '@layouts/symbols'
import { _setDirAttr } from '@layouts/utils'

// ℹ️ We should not import themeConfig here but in urgency we are doing it for now
import { layoutConfig } from '@themeConfig'

export const namespaceConfig = (str: string) => `${layoutConfig.app.title}-${str}`

export function cookieRef<T>(key: string, defaultValue: T) {
  return useCookie<T>(namespaceConfig(key), { default: () => defaultValue })
}

export const useLayoutConfigStore = defineStore('layoutConfig', () => {
  const route = useRoute()

  const windowScrollY = ref(0)

  if (import.meta.client) {
    const { y } = useWindowScroll()

    watchEffect(() => {
      windowScrollY.value = y.value
    })
  }

  // 👉 Navbar Type
  const navbarType = ref(layoutConfig.navbar.type)

  // 👉 Navbar Type
  const isNavbarBlurEnabled = cookieRef('isNavbarBlurEnabled', layoutConfig.navbar.navbarBlur)

  // 👉 Vertical Nav Collapsed
  const isVerticalNavCollapsed = cookieRef('isVerticalNavCollapsed', layoutConfig.verticalNav.isVerticalNavCollapsed)

  // 👉 App Content Width
  const appContentWidth = cookieRef('appContentWidth', layoutConfig.app.contentWidth)

  // 👉 App Content Layout Nav
  const appContentLayoutNav = ref(layoutConfig.app.contentLayoutNav)

  watch(appContentLayoutNav, (val) => {
    // If Navbar type is hidden while switching to horizontal nav => Reset it to sticky
    if (val === AppContentLayoutNav.Horizontal) {
      if (navbarType.value === NavbarType.Hidden)
        navbarType.value = NavbarType.Sticky

      isVerticalNavCollapsed.value = false
    }
  })

  // 👉 Horizontal Nav Type
  const horizontalNavType = ref(layoutConfig.horizontalNav.type)

  //  👉 Horizontal Nav Popover Offset
  const horizontalNavPopoverOffset = ref(layoutConfig.horizontalNav.popoverOffset)

  // 👉 Footer Type
  const footerType = ref(layoutConfig.footer.type)

  // 👉 Misc
  const isOverlayBreakpointMatch = useMediaQuery(
    `(max-width: ${layoutConfig.app.overlayNavFromBreakpoint}px)`,
  )
  const breakpointRef = ref(isOverlayBreakpointMatch.value)

  watchEffect(() => {
    breakpointRef.value = isOverlayBreakpointMatch.value
  })

  const isLessThanOverlayNavBreakpoint = computed({
    get() {
      return breakpointRef.value // Getter for reactive state
    },
    set(value) {
      breakpointRef.value = value // Allow manual mutation
    },
  })

  const effectiveAppContentLayoutNav = computed(() => {
    if (isLessThanOverlayNavBreakpoint.value)
      return AppContentLayoutNav.Vertical

    return appContentLayoutNav.value
  })

  // 👉 Layout Classes
  const _layoutClasses = computed(() => {
    return [
      `layout-nav-type-${effectiveAppContentLayoutNav.value}`,
      `layout-navbar-${navbarType.value}`,
      `layout-footer-${footerType.value}`,
      {
        'layout-vertical-nav-collapsed':
          isVerticalNavCollapsed.value
          && effectiveAppContentLayoutNav.value === AppContentLayoutNav.Vertical
          && !isLessThanOverlayNavBreakpoint.value,
      },
      { [`horizontal-nav-${horizontalNavType.value}`]: effectiveAppContentLayoutNav.value === AppContentLayoutNav.Horizontal },
      `layout-content-width-${appContentWidth.value}`,
      { 'layout-overlay-nav': isLessThanOverlayNavBreakpoint.value },
      { 'window-scrolled': unref(windowScrollY) },
      route.meta.layoutWrapperClasses ? route.meta.layoutWrapperClasses : null,
    ]
  })

  // 👉 RTL
  // const isAppRTL = ref(layoutConfig.app.isRTL)
  const isAppRTL = ref(false)

  watch(isAppRTL, (val) => {
    _setDirAttr(val ? 'rtl' : 'ltr')
  })

  // 👉 Is Vertical Nav Mini
  /*
    This function will return true if current state is mini. Mini state means vertical nav is:
      - Collapsed
      - Isn't hovered by mouse
      - nav is not less than overlay breakpoint (hence, isn't overlay menu)

    ℹ️ We are getting `isVerticalNavHovered` as param instead of via `inject` because
        we are using this in `VerticalNav.vue` component which provide it and I guess because
        same component is providing & injecting we are getting undefined error
  */
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
