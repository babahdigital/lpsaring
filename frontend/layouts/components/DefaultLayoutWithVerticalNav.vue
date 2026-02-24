<script lang="ts" setup>
// @layouts plugin
import { VerticalNavLayout } from '@layouts'
import { computed } from 'vue'

// Components
import HeaderWeeklyRevenue from '@/components/admin/HeaderWeeklyRevenue.vue'
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'

import { getVerticalNavItems } from '@/navigation/vertical'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin || authStore.isSuperAdmin)
const navItems = computed(() => getVerticalNavItems())
</script>

<template>
  <VerticalNavLayout :nav-items="navItems">
    <!-- 👉 navbar -->
    <template #navbar="{ toggleVerticalOverlayNavActive }">
      <div class="d-flex h-100 align-center">
        <IconBtn
          id="vertical-nav-toggle-btn"
          class="d-lg-none"
          @click="toggleVerticalOverlayNavActive(true)"
        >
          <VIcon
            size="26"
            icon="tabler-menu-2"
          />
        </IconBtn>

        <VSpacer />

        <HeaderWeeklyRevenue
          v-if="isAdmin"
          class="me-4"
        />
        <UserProfile />
      </div>
    </template>

    <!-- 👉 Pages -->
    <slot />

    <!-- 👉 Footer -->
    <template #footer>
      <Footer />
    </template>

    <!-- 👉 Customizer -->
    <!-- <TheCustomizer /> -->
  </VerticalNavLayout>
</template>
