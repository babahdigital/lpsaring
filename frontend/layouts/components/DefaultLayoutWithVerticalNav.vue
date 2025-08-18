<script lang="ts" setup>
import type { VerticalNavItems } from '@layouts/types'
import type { ComputedRef } from 'vue'

import NavBarI18n from '@core/components/I18n.vue'
// @layouts plugin
import { VerticalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

// Components
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
// [PERBAIKAN KUNCI] Impor FUNGSI composable-nya, bukan hasilnya.
import { useVerticalNav } from '@/navigation/vertical'

// [PERBAIKAN KUNCI] Panggil fungsi composable DI DALAM setup script.
// Ini memastikan ia berjalan dalam konteks lifecycle komponen yang benar,
// sehingga error 'onMounted' tidak akan terjadi lagi.
const { navItems } = useVerticalNav()

// Type assertion to match expected layout type
const typedNavItems = navItems as ComputedRef<VerticalNavItems>
</script>

<template>
  <VerticalNavLayout :nav-items="typedNavItems">
    <template #navbar="{ toggleVerticalOverlayNavActive }">
      <div class="d-flex h-100 align-center">
        <IconBtn
          id="vertical-nav-toggle-btn"
          class="ms-n3 d-lg-none"
          @click="toggleVerticalOverlayNavActive(true)"
        >
          <VIcon
            size="26"
            icon="tabler-menu-2"
          />
        </IconBtn>

        <!-- Brand: samakan dengan layout horizontal agar tampak konsisten -->
        <NuxtLink
          to="/"
          class="app-logo d-flex align-center gap-x-3 ms-2"
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
        <UserProfile />
      </div>
    </template>

    <slot />

    <template #footer>
      <Footer />
    </template>
  </VerticalNavLayout>
</template>
