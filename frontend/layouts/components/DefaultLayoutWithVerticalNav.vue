<script lang="ts" setup>
import { VerticalNavLayout } from '@layouts'
import { themeConfig } from '@themeConfig'
import { computed } from 'vue'

// Components
import Footer from '@/layouts/components/Footer.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import HeaderWeeklyRevenue from '@/components/admin/HeaderWeeklyRevenue.vue'

// PENYEMPURNAAN: Mengimpor fungsi dinamis dari sistem navigasi terpusat kita
import { getHorizontalNavItems } from '@/navigation/horizontal'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin || authStore.isSuperAdmin)

// PENYEMPURNAAN: navItems sekarang menjadi computed property yang memanggil fungsi terpusat
const navItems = computed(() => getHorizontalNavItems())

</script>

<template>
  <VerticalNavLayout :nav-items="navItems">
    <!-- 👉 navbar -->
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

        <VSpacer />

        <!-- Info Pendapatan Mingguan -->
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
  </VerticalNavLayout>
</template>