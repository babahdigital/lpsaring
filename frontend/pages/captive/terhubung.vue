<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '~/store/auth'
definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Koneksi Berhasil' })

const authStore = useAuthStore()
const { public: { captiveSuccessRedirectUrl } } = useRuntimeConfig()
const countdown = ref(5)
const isClosing = ref(false)

function isConnectedStatus(status: string): boolean {
  return status === 'ok' || status === 'fup'
}

function startAutoClose() {
  if (!import.meta.client)
    return

  const interval = window.setInterval(() => {
    if (countdown.value <= 1) {
      window.clearInterval(interval)
      handleDone()
      return
    }
    countdown.value -= 1
  }, 1000)
}

function handleDone() {
  if (isClosing.value)
    return

  isClosing.value = true
  if (import.meta.client) {
    window.close()
    setTimeout(() => {
      window.location.href = captiveSuccessRedirectUrl || '/'
    }, 500)
  }
}

onMounted(() => {
  const user = authStore.currentUser ?? authStore.lastKnownUser
  if (!user) {
    navigateTo('/captive', { replace: true })
    return
  }

  const status = authStore.getAccessStatusFromUser(user)
  if (!isConnectedStatus(status)) {
    const redirectPath = authStore.getRedirectPathForStatus(status, 'captive') || '/captive'
    navigateTo(redirectPath, { replace: true })
    return
  }

  startAutoClose()
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="420">
      <VCardText class="text-center">
        <VIcon icon="tabler-circle-check" size="56" class="mb-4" color="success" />
        <h4 class="text-h5 mb-2">
          Anda Terhubung!
        </h4>
        <p class="text-medium-emphasis mb-6">
          Perangkat Anda saat ini telah berhasil terhubung ke jaringan internet. Selamat menikmati layanan kami.
        </p>

        <VCard variant="tonal" color="default" class="mb-6 text-start">
          <VCardText class="py-3 px-4">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-medium-emphasis text-body-2">Status Akses</span>
              <span class="text-success font-weight-semibold text-body-2">Aktif</span>
            </div>
            <div class="d-flex justify-space-between align-center">
              <span class="text-medium-emphasis text-body-2">Koneksi</span>
              <span class="font-weight-semibold text-body-2">Aman & Terenkripsi</span>
            </div>
          </VCardText>
        </VCard>

        <p class="text-caption text-medium-emphasis mb-4">
          Halaman ini akan tertutup otomatis dalam {{ countdown }} detik.
        </p>

        <div class="d-flex flex-column ga-3">
          <VBtn color="primary" block :loading="isClosing" @click="handleDone">
            Mulai Browsing
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.auth-wrapper {
  min-block-size: 100dvh;
}
</style>
