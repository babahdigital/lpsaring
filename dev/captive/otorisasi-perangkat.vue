// pages/captive/otorisasi-perangkat.vue
<script setup lang="ts">
import { ref } from 'vue'

import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

definePageMeta({ layout: 'captive' })
useHead({ title: 'Otorisasi Perangkat' })

const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const isLoading = ref(false)

async function authorize() {
  isLoading.value = true
  try {
    const success = await authStore.authorizeDevice()
    if (success) {
      // Clear sync throttling after successful authorization
      localStorage.removeItem('last_device_sync')

      addSnackbar({ type: 'success', title: 'Berhasil', text: 'Perangkat diotorisasi.' })

      // Small delay to ensure state is updated
      await new Promise(resolve => setTimeout(resolve, 500))

      await navigateTo('/captive/terhubung')
    }
    else {
      addSnackbar({ type: 'error', title: 'Gagal', text: authStore.error || 'Otorisasi perangkat gagal.' })
    }
  }
  finally {
    isLoading.value = false
  }
}

async function deny() {
  addSnackbar({ type: 'warning', title: 'Akses Ditolak', text: 'Anda akan dikeluarkan dari sesi ini.' })
  await authStore.logout(false)
  await navigateTo('/captive')
}
</script>

<template>
  <VCard class="w-100 pa-2 pa-sm-8 text-center" rounded="xl" elevation="12">
    <VCardText>
      <VIcon icon="tabler-device-mobile-question" size="64" color="warning" class="mb-4" />
      <h2 class="text-h5 font-weight-bold mb-2">
        Otorisasi Perangkat Baru
      </h2>
      <p class="text-medium-emphasis mb-6">
        Perangkat ini belum terdaftar di akun Anda. Izinkan untuk melanjutkan.
      </p>

      <VCard variant="tonal" class="mb-6 text-left">
        <VList class="bg-transparent">
          <VListItem title="Alamat IP" :subtitle="authStore.clientIp || 'N/A'">
            <template #prepend>
              <VIcon icon="tabler-map-pin" />
            </template>
          </VListItem>
          <VListItem title="Alamat MAC" :subtitle="authStore.clientMac || 'N/A'">
            <template #prepend>
              <VIcon icon="tabler-fingerprint" />
            </template>
          </VListItem>
        </VList>
      </VCard>

      <VBtn
        :loading="isLoading"
        color="success"
        size="large"
        block
        class="mb-3"
        @click="authorize"
      >
        Izinkan Perangkat Ini
      </VBtn>
      <VBtn
        :disabled="isLoading"
        variant="text"
        block
        @click="deny"
      >
        Tolak dan Logout
      </VBtn>
    </VCardText>
  </VCard>
</template>
