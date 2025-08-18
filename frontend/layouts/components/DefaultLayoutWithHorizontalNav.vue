<script lang="ts" setup>
import type { HorizontalNavItems } from '@layouts/types'
import type { ComputedRef } from 'vue'

import NavBarI18n from '@core/components/I18n.vue'
import { HorizontalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

// Components
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
// [PERBAIKAN KUNCI] Impor FUNGSI composable-nya.
import { useHorizontalNav } from '@/navigation/horizontal'
import { useAuthStore } from '~/store/auth'

// Initialize auth if needed
const authStore = useAuthStore()
if (!authStore.isAuthCheckDone) {
  authStore.initializeAuth()
}

// [PERBAIKAN KUNCI] Panggil fungsi composable DI DALAM setup script.
const { navItems } = useHorizontalNav()

// Type assertion to match expected layout type
const typedNavItems = navItems as ComputedRef<HorizontalNavItems>

// Tambahkan debugging untuk membantu pemecahan masalah menu navigasi
console.log('DefaultLayoutWithHorizontalNav - navItems:', {
  count: navItems.value?.length || 0,
  items: navItems.value?.map(item => ({ title: item.title, to: item.to })) || [],
  isAuthCheckDone: authStore.isAuthCheckDone,
  isLoggedIn: authStore.isLoggedIn,
})
</script>

<template>
  <HorizontalNavLayout :nav-items="typedNavItems">
    <template #navbar>
      <NuxtLink
        to="/"
        class="app-logo d-flex align-center gap-x-3"
      >
        <VNodeRenderer :nodes="themeConfig.app.logo" />

        <h1 class="app-title font-weight-bold leading-normal text-xl text-capitalize">
          {{ themeConfig.app.title }}
        </h1>
      </NuxtLink>
      <VSpacer />
      <!-- Theme switcher dihapus untuk menyederhanakan UI -->
      <NavBarI18n
        v-if="themeConfig.app.i18n.enable && themeConfig.app.i18n.langConfig?.length"
        :languages="themeConfig.app.i18n.langConfig"
      />

      <UserProfile />
    </template>

    <slot />

    <template #footer>
      <Footer />
    </template>
  </HorizontalNavLayout>
</template>
