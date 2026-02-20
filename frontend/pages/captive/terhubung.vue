<script setup lang="ts">
import { onMounted, ref } from 'vue'
definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Koneksi Berhasil' })

const { public: { captiveSuccessRedirectUrl } } = useRuntimeConfig()
const countdown = ref(5)

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
  if (import.meta.client) {
    window.close()
    setTimeout(() => {
      window.location.href = captiveSuccessRedirectUrl || '/'
    }, 500)
  }
}

onMounted(() => {
  startAutoClose()
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="520">
      <VCardText class="text-center">
        <VIcon icon="tabler-circle-check" size="56" class="mb-4" color="success" />
        <h4 class="text-h5 mb-2">
          Koneksi Berhasil
        </h4>
        <p class="text-medium-emphasis mb-6">
          Perangkat Anda sudah terhubung ke internet. Halaman ini akan tertutup otomatis dalam {{ countdown }} detik.
        </p>
        <VBtn color="primary" block @click="handleDone">
          Selesai
        </VBtn>
      </VCardText>
    </VCard>
  </div>
</template>
