import { defineThemeConfig } from '@core'
import { Skins } from '@/types/enums'
// ❗ Logo SVG must be imported with ?raw suffix
import logo from '@images/logo.svg?raw'

import {
  AppContentLayoutNav,
  ContentWidth,
  FooterType,
  HorizontalNavType,
  NavbarType,
} from  '@/types/enums'

import { breakpointsVuetifyV3 } from '@vueuse/core'
import { h } from 'vue'
import { VIcon } from 'vuetify/components/VIcon'

export const { themeConfig, layoutConfig } = defineThemeConfig({
  app: {
    title: 's o b i g i d u l',
    logo: h('div', { innerHTML: logo, style: 'display: none;' }),
    contentWidth: ContentWidth.Boxed,
    contentLayoutNav: AppContentLayoutNav.Horizontal,
    overlayNavFromBreakpoint: breakpointsVuetifyV3.lg,
    i18n: {
      enable: false,
      defaultLocale: 'id',
      langConfig: [
        { label: 'Indonesia', i18nLang: 'id', isRTL: false },
        { label: 'English', i18nLang: 'en', isRTL: false },
      ],
    },
    // PERBAIKAN: Kembalikan properti 'theme' dengan nilai default 'system'.
    // Ini diperlukan untuk memenuhi kontrak tipe TypeScript.
    // Nilai ini akan segera ditimpa oleh pengaturan dari database di app.vue.
    theme: 'dark',
    skin: Skins.Bordered,
    iconRenderer: VIcon,
    isRTL: false,
  },
  navbar: {
    type: NavbarType.Sticky,
    navbarBlur: true,
    isContentWidthWide: true,
    stickOnScroll: 100,
  },
  footer: {
    type: FooterType.Static,
    isContentWidthWide: true,
  },
  verticalNav: {
    isVerticalNavCollapsed: false,
    defaultNavItemIconProps: { icon: 'tabler-circle' },
    isVerticalNavSemiDark: false,
    isMini: false,
  },
  horizontalNav: {
    type: HorizontalNavType.Sticky,
    transition: 'slide-y-reverse-transition',
    popoverOffset: 4,
  },
  icons: {
    chevronDown: { icon: 'tabler-chevron-down' },
    chevronRight: { icon: 'tabler-chevron-right', size: 20 },
    close: { icon: 'tabler-x', size: 20 },
    verticalNavPinned: { icon: 'tabler-circle-dot', size: 20 },
    verticalNavUnPinned: { icon: 'tabler-circle', size: 20 },
    sectionTitlePlaceholder: { icon: 'tabler-minus' },
  },
})