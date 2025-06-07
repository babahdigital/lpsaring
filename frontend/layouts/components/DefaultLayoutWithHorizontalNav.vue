<script lang="ts" setup>
import NavBarI18n from '@core/components/I18n.vue'
import { HorizontalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

// 1. Impor `computed` dari Vue
import { computed } from 'vue'

// 2. Impor fungsi navigasi dinamis yang baru
import { getHorizontalNavItems } from '@/navigation/horizontal'

// Components
import Footer from '@/layouts/components/Footer.vue'
import NavbarThemeSwitcher from '@/layouts/components/NavbarThemeSwitcher.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'

// 3. Buat computed property untuk mendapatkan item navigasi
// Logika filtering sekarang terpusat di dalam `getHorizontalNavItems`
const navItems = computed(() => getHorizontalNavItems())
</script>

<template>
  <HorizontalNavLayout :nav-items="navItems">
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
