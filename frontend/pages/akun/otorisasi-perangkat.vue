<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { navigateTo, useNuxtApp } from '#app'
import { useAuthStore } from '~/store/auth'
import { useSnackbar } from '~/composables/useSnackbar'
import type { DeviceInfo } from '~/types/auth'

// Meta dan Layout
definePageMeta({
  title: 'Otorisasi Perangkat Baru',
  layout: 'blank', // Menggunakan layout 'blank' lebih cocok untuk halaman fokus seperti ini
  // Gunakan middleware bernama 'device-auth' untuk memastikan akses yang benar
  middleware: ['device-auth'],
})

useHead({
  title: 'Otorisasi Perangkat',
})

// Composables
const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const { $api } = useNuxtApp()
const router = useRouter()

// State Lokal
const isLoading = ref(true)
const deviceInfo = ref<DeviceInfo | null>(null)

// Computed property untuk menampilkan informasi perangkat
const displayedInfo = computed(() => {
  const info = deviceInfo.value || authStore.pendingDeviceInfo
  return {
    ip: info?.ip || 'Tidak terdeteksi',
    mac: info?.mac || 'Tidak terdeteksi',
    userAgent: info?.user_agent || 'Tidak tersedia',
  }
})

// Fungsi untuk mengambil informasi perangkat jika belum ada
async function fetchPendingDevice() {
  isLoading.value = true
  try {
    // Jika state sudah ada, gunakan itu
    if (authStore.pendingDeviceInfo) {
      deviceInfo.value = authStore.pendingDeviceInfo
      return
    }

    // Jika tidak ada, coba ambil dari backend
    const response = await $api<{ status: string, data: { device_info: DeviceInfo } }>('/auth/pending-device')
    if (response.status === 'SUCCESS' && response.data?.device_info) {
      deviceInfo.value = response.data.device_info
      // Simpan juga ke store untuk konsistensi
      authStore.setDeviceAuthRequired(true, response.data.device_info)
    }
    else {
      addSnackbar({
        title: 'Info',
        text: 'Tidak ada perangkat yang menunggu otorisasi. Mengarahkan Anda kembali...',
        type: 'info',
      })
      await navigateTo('/dashboard', { replace: true })
    }
  }
  catch (error) {
    console.error('Gagal mengambil info perangkat:', error)
    addSnackbar({
      title: 'Error',
      text: 'Gagal memuat informasi perangkat. Silakan coba login kembali.',
      type: 'error',
    })
    await authStore.logout()
  }
  finally {
    isLoading.value = false
  }
}

// Handler untuk tombol otorisasi
async function handleAuthorizeDevice() {
  const success = await authStore.authorizeDevice()
  if (success) {
    addSnackbar({
      title: 'Berhasil',
      text: 'Perangkat Anda telah berhasil diotorisasi.',
      type: 'success',
    })
    await navigateTo('/dashboard', { replace: true })
  }
}

// Handler untuk tombol tolak
async function handleRejectDevice() {
  // `rejectDeviceAuthorization` akan menangani proses logout secara otomatis
  await authStore.rejectDeviceAuthorization()
}

// Lifecycle Hook
onMounted(() => {
  fetchPendingDevice()
})
</script>

<template>
  <div class="d-flex align-center justify-center pa-4 h-100">
    <VCard
      class="auth-card pa-4 pt-7"
      max-width="600"
    >
      <VCardItem class="justify-center">
        <VCardTitle class="font-weight-bold text-h5">
          <VIcon
            icon="tabler-device-mobile-question"
            class="me-2"
          />
          Otorisasi Perangkat Baru
        </VCardTitle>
      </VCardItem>

      <VCardText class="pt-2">
        <p class="mb-6 text-center">
          Kami mendeteksi Anda masuk dari perangkat atau browser yang belum pernah terdaftar. Untuk keamanan akun, silakan konfirmasi tindakan ini.
        </p>

        <VAlert
          v-if="!isLoading"
          color="warning"
          variant="tonal"
          class="mb-6"
        >
          <VAlertTitle class="mb-2">
            Detail Perangkat Terdeteksi
          </VAlertTitle>
          <VList
            density="compact"
            class="bg-transparent"
          >
            <VListItem>
              <template #prepend>
                <VIcon
                  icon="tabler-network"
                  size="20"
                  class="me-2"
                />
              </template>
              <VListItemTitle class="text-caption">
                <strong>Alamat IP:</strong> {{ displayedInfo.ip }}
              </VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon
                  icon="tabler-fingerprint"
                  size="20"
                  class="me-2"
                />
              </template>
              <VListItemTitle class="text-caption">
                <strong>Alamat MAC:</strong> {{ displayedInfo.mac }}
              </VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon
                  icon="tabler-browser"
                  size="20"
                  class="me-2"
                />
              </template>
              <VListItemTitle class="text-caption">
                <strong>Browser:</strong> {{ displayedInfo.userAgent }}
              </VListItemTitle>
            </VListItem>
          </VList>
        </VAlert>

        <div
          v-if="isLoading"
          class="text-center"
        >
          <VProgressCircular
            indeterminate
            color="primary"
            class="mb-4"
          />
          <p>Memuat informasi perangkat...</p>
        </div>

        <div v-else>
          <p class="mb-4 text-body-2">
            Apakah Anda mengenali perangkat ini dan ingin menambahkannya ke akun Anda?
          </p>

          <VBtn
            block
            color="success"
            size="large"
            class="mb-3"
            :loading="authStore.loading"
            @click="handleAuthorizeDevice"
          >
            <VIcon
              icon="tabler-circle-check"
              class="me-2"
            />
            Ya, Ini Perangkat Saya
          </VBtn>

          <VBtn
            block
            color="error"
            variant="outlined"
            size="large"
            :loading="authStore.loading"
            @click="handleRejectDevice"
          >
            <VIcon
              icon="tabler-logout"
              class="me-2"
            />
            Bukan, Tolak & Logout
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style lang="scss">
.auth-card {
  .v-card-item {
    padding-bottom: 0;
  }
}
</style>