<script lang="ts" setup>
import NavBarI18n from '@core/components/I18n.vue'
import { HorizontalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'

import { themeConfig } from '@themeConfig'

import { computed } from 'vue' // 1. Impor computed
// Components
import Footer from '@/layouts/components/Footer.vue'
import NavbarThemeSwitcher from '@/layouts/components/NavbarThemeSwitcher.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import navItemsData from '@/navigation/horizontal' // 2. Impor data menu lengkap
import { useAuthStore } from '~/store/auth' // 3. Impor auth store

// 4. Dapatkan instance auth store
const authStore = useAuthStore()

// 5. Buat computed property untuk memfilter navItems
const filteredNavItems = computed(() => {
  // Pastikan user sudah ada dan memiliki properti is_admin
  const isAdmin = authStore.user?.is_admin === true

  // Filter navItemsData
  return navItemsData.filter((item) => {
    // Selalu tampilkan item yang tidak memerlukan admin
    if (!item.requiresAdmin) {
      return true
    }
    // Hanya tampilkan item admin jika pengguna adalah admin
    return isAdmin
  })
})
</script>

<template>
  <HorizontalNavLayout :nav-items="filteredNavItems">
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

      <NavBarI18n
        v-if="themeConfig.app.i18n.enable && themeConfig.app.i18n.langConfig?.length"
        :languages="themeConfig.app.i18n.langConfig"
      />

      <NavbarThemeSwitcher class="me-2" />
      <UserProfile />
    </template>

    <slot />

    <template #footer>
      <Footer />
    </template>
  </HorizontalNavLayout>
</template>
