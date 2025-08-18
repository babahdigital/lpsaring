// themeConfig.ts - VERSI DISEMPURNAKAN

import { breakpointsVuetifyV3 } from '@vueuse/core'
import { h } from 'vue'
import { VIcon } from 'vuetify/components/VIcon'

import { defineThemeConfig } from './@core'
import {
  AppContentLayoutNav,
  ContentWidth,
  FooterType,
  HorizontalNavType,
  NavbarType,
  Skins,
} from './types/enums'

/**
 * Konfigurasi ini mendefinisikan tampilan dan nuansa default (awal) dari aplikasi.
 * Nilai-nilai ini akan digunakan saat aplikasi pertama kali dimuat, sebelum pengaturan
 * dinamis dari server (API) diterima dan diterapkan oleh store (misalnya: useConfigStore).
 * Konsistensi antara nilai di sini (cth: theme: 'dark') dan gaya default di nuxt.config.ts
 * sangat penting untuk pengalaman pengguna yang mulus tanpa kedipan.
 */
export const { themeConfig, layoutConfig } = defineThemeConfig({
  app: {
    title: 'sobigidul',

    // Menggunakan VNode div kosong yang aman untuk SSR/SPA sebagai placeholder logo.
    logo: h('div'),

    contentWidth: ContentWidth.Boxed,
    contentLayoutNav: AppContentLayoutNav.Horizontal, // Use horizontal nav as shown in image

    overlayNavFromBreakpoint: breakpointsVuetifyV3.lg - 1, // Starter kit style

    i18n: {
      enable: false, // i18n dinonaktifkan sesuai konfigurasi.
      defaultLocale: 'id',
      langConfig: [
        { label: 'Indonesia', i18nLang: 'id', isRTL: false },
        { label: 'English', i18nLang: 'en', isRTL: false },
      ],
    },
    theme: 'dark', // Dark theme as shown in image
    skin: Skins.Default, // Default skin
    iconRenderer: VIcon,
  },
  navbar: {
    type: NavbarType.Sticky,
    navbarBlur: true,
  },
  footer: {
    type: FooterType.Static,
  },
  verticalNav: {
    isVerticalNavCollapsed: false,
    defaultNavItemIconProps: { icon: 'tabler:circle' },
    isVerticalNavSemiDark: false,
  },
  horizontalNav: {
    type: HorizontalNavType.Sticky,
    transition: 'slide-y-reverse-transition',
    popoverOffset: 4,
  },
  icons: {
    chevronDown: { icon: 'tabler:chevron-down' },
    chevronRight: { icon: 'tabler:chevron-right', size: 20 },
    close: { icon: 'tabler:x', size: 20 },
    verticalNavPinned: { icon: 'tabler:circle-dot', size: 20 },
    verticalNavUnPinned: { icon: 'tabler:circle', size: 20 },
    sectionTitlePlaceholder: { icon: 'tabler:minus' },
  },
})
