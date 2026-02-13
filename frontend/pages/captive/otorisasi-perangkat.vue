<script setup lang="ts">
import { navigateTo } from '#imports'
import { ref, watch } from 'vue'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
  auth: false,
})

useHead({ title: 'Otorisasi Perangkat' })

const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const isLoading = ref(false)

async function authorize() {
  isLoading.value = true
  try {
    const success = await authStore.authorizeDevice()
    if (success) {
      addSnackbar({ type: 'success', title: 'Berhasil', text: 'Perangkat diotorisasi.' })
      await navigateTo('/captive/terhubung', { replace: true })
    }
  }
  finally {
    isLoading.value = false
  }
}

watch(() => authStore.error, (newError) => {
  if (typeof newError === 'string' && newError.length > 0) {
    addSnackbar({ type: 'error', title: 'Gagal', text: newError })
    authStore.clearError()
  }
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="520">
      <VCardText class="text-center">
        <VIcon icon="tabler-device-mobile" size="56" class="mb-4" color="primary" />
        <h4 class="text-h5 mb-2">
          Otorisasi Perangkat
        </h4>
        <p class="text-medium-emphasis mb-6">
          Perangkat Anda perlu diotorisasi agar dapat terhubung ke internet.
        </p>
        <VBtn color="primary" block :loading="isLoading" @click="authorize">
          Otorisasi Sekarang
        </VBtn>
        <VBtn variant="text" class="mt-3" block @click="navigateTo('/captive')">
          Kembali ke Login
        </VBtn>
      </VCardText>
    </VCard>
  </div>
</template>
