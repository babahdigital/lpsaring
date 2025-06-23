<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useAuthStore } from '~/store/auth'
import { useDashboardStore } from '~/store/dashboard'

const authStore = useAuthStore()
const dashboardStore = useDashboardStore()

const currentUser = computed(() => authStore.currentUser)
const isLoggedIn = computed(() => authStore.isLoggedIn)
const isAdmin = computed(() => authStore.isAdmin || authStore.isSuperAdmin)
const isSuperAdmin = computed(() => authStore.isSuperAdmin)
const pendingUserCount = computed(() => dashboardStore.stats?.pendingApprovals ?? 0)

onMounted(() => {
  if (isAdmin.value && isLoggedIn.value) {
    dashboardStore.fetchDashboardStats()
  }
})

watch(isAdmin, (newIsAdmin) => {
  if (newIsAdmin && isLoggedIn.value) {
    dashboardStore.fetchDashboardStats()
  }
  else {
    dashboardStore.resetState()
  }
})

function handleLogout() {
  authStore.logout(true)
}

const displayName = computed(() => {
  if (!currentUser.value)
    return 'Pengguna'
  if (currentUser.value.full_name?.trim())
    return currentUser.value.full_name
  if (currentUser.value.phone_number)
    return currentUser.value.phone_number
  return 'Pengguna Terdaftar'
})

const userInitials = computed(() => {
  const name = displayName.value
  if (!name || name === 'Pengguna')
    return 'U'
  const words = name.split(' ').filter(Boolean)
  if (words.length >= 2)
    return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1 && words[0].length > 1)
    return words[0].slice(0, 2).toUpperCase()
  return name[0].toUpperCase()
})

const userRole = computed(() => {
  if (!currentUser.value)
    return 'Guest'
  if (currentUser.value.role === 'SUPER_ADMIN')
    return 'Super Admin'
  if (currentUser.value.role === 'ADMIN')
    return 'Admin'
  return 'User'
})

const headerBadgeProps = computed(() => {
  if (isAdmin.value && pendingUserCount.value > 0) {
    return {
      color: 'error',
      content: pendingUserCount.value,
      dot: false,
    }
  }
  else {
    return {
      color: 'success',
      content: undefined,
      dot: true,
    }
  }
})

const isLoadingAuth = computed(() => !authStore.initialAuthCheckDone && !authStore.user)
</script>

<template>
  <VBadge
    v-if="isLoggedIn && currentUser"
    v-bind="headerBadgeProps"
    location="top end"
    offset-x="-1"
    offset-y="-1"
    bordered
  >
    <VAvatar
      class="cursor-pointer"
      color="primary"
      variant="tonal"
    >
      <span class="font-weight-medium">{{ userInitials }}</span>
      <VMenu
        activator="parent"
        width="260"
        location="bottom end"
        offset="14px"
        close-on-content-click
      >
        <VList>
          <VListItem>
            <template #prepend>
              <VListItemAction start>
                <VBadge
                  dot
                  location="bottom right"
                  offset-x="3"
                  offset-y="3"
                  color="success"
                  bordered
                >
                  <VAvatar color="primary" variant="tonal" size="40">
                    <span class="text-h6 font-weight-medium">{{ userInitials }}</span>
                  </VAvatar>
                </VBadge>
              </VListItemAction>
            </template>
            <VListItemTitle class="font-weight-semibold">
              {{ displayName }}
            </VListItemTitle>
            <VListItemSubtitle>{{ userRole }}</VListItemSubtitle>
          </VListItem>
          <VDivider class="my-2" />

          <!-- Profil Saya (untuk semua user) -->
          <VListItem link to="/akun" density="compact">
            <template #prepend>
              <VIcon class="me-2" icon="tabler-user" size="22" />
            </template>
            <VListItemTitle>Profil Saya</VListItemTitle>
          </VListItem>

          <!-- Pengaturan (hanya untuk Admin/Super Admin) -->
          <VListItem
            v-if="isAdmin"
            link
            :to="isSuperAdmin ? '/admin/settings/general' : '/admin/settings'"
            density="compact"
          >
            <template #prepend>
              <VIcon class="me-2" icon="tabler-settings" size="22" />
            </template>
            <VListItemTitle>Pengaturan</VListItemTitle>
          </VListItem>

          <!-- Persetujuan Pengguna (hanya untuk Admin dengan pending) -->
          <VListItem
            v-if="isAdmin && pendingUserCount > 0"
            link
            to="/admin/users"
            density="compact"
          >
            <template #prepend>
              <VIcon class="me-2" icon="tabler-user-exclamation" size="22" color="warning" />
            </template>
            <VListItemTitle class="text-warning">
              Persetujuan Pengguna
            </VListItemTitle>
            <template #append>
              <VBadge color="error" :content="pendingUserCount" inline />
            </template>
          </VListItem>

          <VDivider class="my-2" />
          <div class="px-2 py-1">
            <VBtn
              block
              color="error"
              variant="tonal"
              @click="handleLogout"
            >
              <template #prepend>
                <VIcon icon="tabler-logout" size="20" />
              </template>
              Logout
            </VBtn>
          </div>
        </VList>
      </VMenu>
    </VAvatar>
  </VBadge>

  <VAvatar v-else-if="isLoadingAuth" color="grey-lighten-1" variant="tonal">
    <VProgressCircular indeterminate size="24" />
  </VAvatar>

  <VBtn v-else-if="!isLoggedIn && authStore.initialAuthCheckDone" to="/login" color="primary">
    Login
  </VBtn>
</template>
