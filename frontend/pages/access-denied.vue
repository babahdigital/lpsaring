<script setup lang="ts">
definePageMeta({
  layout: 'blank',
  title: 'Akses Ditolak',
})

function goToWebsite() {
  // Redirect to main website - adjust URL as needed
  window.location.href = 'https://dev.sobigidul.com'
}
</script>

<template>
  <div class="d-flex align-center justify-center min-vh-100">
    <VCard class="pa-8 text-center" max-width="500">
      <VIcon
        icon="tabler-shield-x"
        size="80"
        color="error"
        class="mb-4"
      />

      <VCardTitle class="text-h4 mb-4">
        Akses Ditolak
      </VCardTitle>

      <VCardText class="text-body-1 mb-6">
        Halaman ini hanya dapat diakses melalui captive portal.
        Silakan gunakan koneksi WiFi untuk mengakses portal hotspot.
      </VCardText>

      <VBtn
        color="primary"
        variant="flat"
        size="large"
        @click="goToWebsite"
      >
        Kunjungi Website Utama
      </VBtn>
    </VCard>
  </div>
</template>

<style scoped>
.min-vh-100 {
  min-height: 100vh;
}
</style>
