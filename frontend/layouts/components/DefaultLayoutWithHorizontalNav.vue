<script lang="ts" setup>
import { HorizontalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'

import { themeConfig } from '@themeConfig'
import { computed } from 'vue'
import HeaderWeeklyRevenue from '@/components/admin/HeaderWeeklyRevenue.vue'
// Components
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import { getHorizontalNavItems } from '@/navigation/horizontal'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const navItems = computed(() => getHorizontalNavItems())
const isAdmin = computed(() => authStore.isAdmin || authStore.isSuperAdmin)
</script>

<template>
  <HorizontalNavLayout :nav-items="navItems">
    <!-- 👉 navbar -->
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
      <HeaderWeeklyRevenue
        v-if="isAdmin"
        class="me-4"
      />
      <UserProfile />
    </template>

    <!-- 👉 Pages -->
    <slot />

    <!-- 👉 Footer -->
    <template #footer>
      <Footer />
    </template>

    <!-- 👉 Customizer -->
    <!-- <TheCustomizer /> -->
  </HorizontalNavLayout>
</template>
