<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted } from 'vue'

import { useAdminAccess } from '~/composables/useAdminAccess'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { AppContentLayoutNav } from '~/types/enums'

// Define layout components
const DefaultLayoutWithHorizontalNav = defineAsyncComponent(() => import('@/layouts/components/DefaultLayoutWithHorizontalNav.vue'))
const DefaultLayoutWithVerticalNav = defineAsyncComponent(() => import('@/layouts/components/DefaultLayoutWithVerticalNav.vue'))

const _router = useRouter()
const _authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { verifyAdminAccess, _redirectIfNotAdmin } = useAdminAccess()

// Create computed classes for layout styling
const layoutClasses = computed(() => {
  const s = settingsStore.settings
  const classes = [
    s.SKIN ? `skin--${s.SKIN}` : '',
    (s.APP_CONTENT_WIDTH || s.CONTENT_WIDTH) ? `content-width-${s.APP_CONTENT_WIDTH || s.CONTENT_WIDTH}` : '',
    s.APP_CONTENT_LAYOUT_NAV ? `layout-nav-type-${s.APP_CONTENT_LAYOUT_NAV}` : '',
    s.FOOTER_TYPE ? `footer-type-${s.FOOTER_TYPE}` : '',
    s.NAVBAR_TYPE ? `navbar-type-${s.NAVBAR_TYPE}` : '',
    'admin-layout', // Additional class to identify admin layout
  ].filter(Boolean)

  console.log('[ADMIN-LAYOUT] Classes applied:', classes)

  return classes
})

// Protect all admin pages with this layout check and apply admin-specific layout settings
onMounted(async () => {
  console.log('[ADMIN-LAYOUT] Admin layout mounted - checking admin access')

  // Use the centralized admin access logic
  const isAdmin = await verifyAdminAccess()

  // If not admin, redirect to regular dashboard
  if (!isAdmin) {
    console.log('[ADMIN-LAYOUT] Access denied, redirecting to user dashboard')
    redirectIfNotAdmin()
  }
  else {
    console.log('[ADMIN-LAYOUT] Admin access confirmed')
  }
})
</script>

<template>
  <div :class="layoutClasses">
    <Component
      :is="(settingsStore.settings.APP_CONTENT_LAYOUT_NAV || settingsStore.settings.VUEXY_APP_CONTENT_LAYOUT_NAV) === AppContentLayoutNav.Horizontal
        ? DefaultLayoutWithHorizontalNav
        : DefaultLayoutWithVerticalNav"
    >
      <slot />
    </Component>
  </div>
</template>

<style lang="scss">
@use "@layouts/styles/default-layout";

.admin-layout {
  // You can add admin-specific styling here if needed
}
</style>
