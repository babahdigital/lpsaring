<script setup lang="ts">
// useFetch dari #app
// Import tipe UserProfile
// Pastikan path avatar benar
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
// const config = useRuntimeConfig()

// Data pengguna diambil langsung dari store. Middleware harusnya sudah mengisi ini.
const currentUser = computed(() => authStore.currentUser)
const isLoggedIn = computed(() => authStore.isLoggedIn)

// UseFetch di sini bisa bersifat sekunder, misalnya untuk refresh data profil secara berkala
// atau jika ada detail profil yang tidak selalu dimuat oleh initializeAuth.
// Untuk kasus umum, data dari authStore.currentUser sudah cukup.
// Jika Anda tetap ingin fetch di sini, pastikan tidak konflik dengan store.
// Contoh: UseFetch untuk mendapatkan data profil yang lebih detail jika diperlukan
/*
const getApiUrl = () => {
  const endpoint = '/auth/me'; // Endpoint untuk data user
  return `${config.public.apiBaseUrl}${endpoint}`; // Asumsi selalu client-side untuk komponen ini
};

const { data: profileDetails, pending: profilePending, error: profileError, refresh: refreshProfile } = useFetch<UserProfile>(
  () => getApiUrl(), // Gunakan fungsi agar reaktif jika URL berubah
  {
    method: 'GET',
    key: 'userProfileDetailsComponent', // Kunci unik
    lazy: true,
    immediate: false, // Jangan fetch otomatis, tunggu kondisi tertentu atau panggilan manual
    headers: computed(() => ({ // Headers reaktif terhadap token di store
      'Authorization': `Bearer ${authStore.token}`,
    })),
    watch: [() => authStore.token], // Re-fetch jika token berubah (dan user belum ada)
    // Hanya fetch jika ada token dan belum ada data user di store (atau data di sini kosong)
    // condition: () => !!authStore.token && !authStore.user,

    onResponse({ response }) {
      if (response.status === 200 && response._data) {
        // Jika fetch ini menghasilkan data yang lebih baru/lengkap, update store
        // Perlu logika untuk membandingkan atau memutuskan apakah store perlu diupdate
        // authStore.setUser(response._data as UserProfile);
        console.log('[UserProfile Component useFetch] Profile details fetched:', response._data);
      }
    },
    onResponseError({ response }) {
      console.error('[UserProfile Component useFetch] Error fetching profile details:', response?.status);
      if (response?.status === 401 || response?.status === 403) {
        // authStore.logout(); // Biarkan middleware atau watcher di store yang menangani ini
      }
    }
  }
);

// Panggil refreshProfile jika login dan belum ada currentUser atau profileDetails
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn && !currentUser.value && !profileDetails.value && typeof refreshProfile === 'function') {
    // refreshProfile();
  }
}, { immediate: true });
*/

// Fungsi logout menggunakan action dari store
function handleLogout() {
  authStore.logout(true) // true untuk redirect ke halaman login
}

// Computed properties berdasarkan currentUser dari store
const userRole = computed(() => {
  if (!currentUser.value)
    return 'Guest' // Atau status loading jika authStore.initialAuthCheckDone masih false
  if (currentUser.value.is_admin) { // Sesuaikan dengan struktur UserProfile Anda
    return 'Admin'
  }
  return currentUser.value.role || 'User' // Fallback ke role jika ada, atau 'User'
})

const displayName = computed(() => {
  if (!currentUser.value)
    return 'Pengguna'
  if (currentUser.value.full_name && currentUser.value.full_name.trim() !== '') {
    return currentUser.value.full_name
  }
  if (currentUser.value.phone_number) {
    return currentUser.value.phone_number
  }
  return 'Pengguna Terdaftar'
})

// Untuk VAvatar dan VMenu, kita perlu status loading dari store
const isLoadingAuth = computed(() => !authStore.initialAuthCheckDone && !authStore.user)
// Anda mungkin juga ingin status error jika initializeAuth gagal
// const authError = computed(() => authStore.error); // Jika Anda menambahkan state error di store
</script>

<template>
  <VBadge
    v-if="isLoggedIn && currentUser"
    dot
    location="bottom right"
    offset-x="3"
    offset-y="3"
    bordered
    color="success"
  >
    <VAvatar
      class="cursor-pointer"
      color="primary"
      variant="tonal"
    >
      <VImg v-if="currentUser?.avatar_url" :src="currentUser.avatar_url" />
      <span v-else-if="displayName">{{ displayName.substring(0, 1).toUpperCase() }}</span>
      <VIcon v-else icon="tabler-user-circle" />

      <VMenu
        activator="parent"
        width="230"
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
                    <VImg v-if="currentUser?.avatar_url" :src="currentUser.avatar_url" />
                    <span v-else-if="displayName" class="text-h6">{{ displayName.substring(0, 1).toUpperCase() }}</span>
                    <VIcon v-else icon="tabler-user-circle" />
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

          <VListItem link to="/akun" density="compact">
            <template #prepend>
              <VIcon class="me-2" icon="tabler-user" size="22" />
            </template>
            <VListItemTitle>Profil Saya</VListItemTitle>
          </VListItem>
          <VListItem link disabled density="compact">
            <template #prepend>
              <VIcon class="me-2" icon="tabler-settings" size="22" />
            </template>
            <VListItemTitle>Pengaturan</VListItemTitle>
          </VListItem>
          <VDivider class="my-2" />

          <div class="pa-2">
            <VBtn block color="error" variant="flat" rounded="lg" @click="handleLogout">
              <template #prepend>
                <VIcon icon="tabler-logout" size="20" />
              </template>
              Logout
              <template #append>
                <VIcon icon="tabler-arrow-right" size="20" />
              </template>
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
