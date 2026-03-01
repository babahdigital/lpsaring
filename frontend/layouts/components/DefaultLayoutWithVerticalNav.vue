<script lang="ts" setup>
// @layouts plugin
import { VerticalNavLayout } from '@layouts'
import { computed } from 'vue'
import { useRoute } from '#app'

// Components
import HeaderWeeklyRevenue from '@/components/admin/HeaderWeeklyRevenue.vue'
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'

import { getVerticalNavItems } from '@/navigation/vertical'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin || authStore.isSuperAdmin)
const navItems = computed(() => getVerticalNavItems())
const route = useRoute()

interface NavItemLike {
  title?: string
  to?: { path?: string }
  children?: NavItemLike[]
}

function normalizePath(path: string | undefined | null): string {
  const raw = String(path ?? '').trim()
  if (!raw)
    return ''
  if (raw === '/')
    return '/'
  return raw.replace(/\/+$/, '')
}

function findTitlePath(items: NavItemLike[], currentPath: string, trail: string[] = []): string[] | null {
  for (const item of items) {
    const title = String(item.title ?? '').trim()
    const nextTrail = title ? [...trail, title] : trail
    const itemPath = normalizePath(item.to?.path)
    if (itemPath && itemPath === currentPath)
      return nextTrail

    const children = Array.isArray(item.children) ? item.children : []
    if (children.length > 0) {
      const found = findTitlePath(children, currentPath, nextTrail)
      if (found)
        return found
    }
  }
  return null
}

const mobileBreadcrumbItems = computed(() => {
  const currentPath = normalizePath(route.path)
  const found = findTitlePath(navItems.value as NavItemLike[], currentPath)
  const labels = found && found.length > 0
    ? found
    : [currentPath === '/' ? 'Home' : currentPath.split('/').filter(Boolean).slice(-1)[0]?.replace(/-/g, ' ') || 'Halaman']

  return labels.map((label, index) => ({
    title: label,
    disabled: index === labels.length - 1,
  }))
})
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

        <VBreadcrumbs
          class="d-lg-none pa-0 ms-1 mobile-navbar-breadcrumb"
          :items="mobileBreadcrumbItems"
          divider="/"
        />

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

<style scoped>
.mobile-navbar-breadcrumb {
  min-inline-size: 0;
}

.mobile-navbar-breadcrumb :deep(.v-breadcrumbs-item) {
  font-size: 0.875rem;
  text-transform: capitalize;
}
</style>
