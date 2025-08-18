import type { NuxtApp } from 'nuxt/app'
import type { VNode } from 'vue'

declare module '@layouts' {
  // ========== TAMBAHAN BARU ========== //
  export type NavbarType = 'sticky' | 'static' | 'hidden' | 'floating'
  export type FooterType = 'sticky' | 'static' | 'hidden'
  export type ContentWidth = 'fluid' | 'boxed'
  // =================================== //

  export interface LayoutLogoConfig {
    ref?: VNode | null
  }

  export interface LayoutAppConfig {
    logo?: LayoutLogoConfig
    title?: string
    contentWidth?: ContentWidth
    contentLayoutNav?: 'vertical' | 'horizontal'
    overlayNavFromBreakpoint?: number
    i18n?: {
      enable: boolean
      defaultLocale: string
      langConfig: Array<{
        label: string
        i18nLang: string
        isRTL: boolean
      }>
    }
    theme?: string
    skin?: string
    iconRenderer?: any
    isRTL?: boolean // PROPERI BARU
  }

  export interface LayoutNavbarConfig {
    type?: NavbarType
    navbarBlur?: boolean
    isContentWidthWide?: boolean // PROPERI BARU
    stickOnScroll?: number // PROPERI BARU
  }

  export interface LayoutFooterConfig {
    type?: FooterType
    isContentWidthWide?: boolean // PROPERI BARU
  }

  export interface LayoutVerticalNavConfig {
    isVerticalNavCollapsed?: boolean
    defaultNavItemIconProps?: Record<string, any>
    isVerticalNavSemiDark?: boolean
    isMini?: boolean // PROPERI BARU
  }

  export interface LayoutHorizontalNavConfig {
    type?: 'sticky' | 'static'
    transition?: string
    popoverOffset?: number
  }

  export interface LayoutIconsConfig {
    [key: string]: any
  }

  export interface LayoutConfig {
    app?: LayoutAppConfig
    navbar?: LayoutNavbarConfig
    footer?: LayoutFooterConfig
    verticalNav?: LayoutVerticalNavConfig
    horizontalNav?: LayoutHorizontalNavConfig
    icons?: LayoutIconsConfig
    $route?: NuxtApp['$route']
    $nuxt?: NuxtApp['$nuxt']
  }
}
