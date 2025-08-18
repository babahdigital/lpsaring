// pages/captive/terhubung.vue
<script setup lang="ts">
definePageMeta({ layout: 'captive' })
useHead({ title: 'Koneksi Berhasil' })

function handleDone() {
  // Coba tutup jendela (perilaku standar untuk captive portal)
  window.close()
  // Fallback jika window.close() gagal, arahkan ke situs populer
  setTimeout(() => {
    window.location.href = 'https://google.com'
  }, 500)
}
</script>

<template>
  <VCard class="w-100 pa-2 pa-sm-8 text-center" rounded="xl" elevation="12">
    <VCardText>
      <div class="success-animation mb-4">
        <VIcon icon="tabler-circle-check" size="80" color="success" />
      </div>
      <h2 class="text-h4 font-weight-bold mb-2">
        Koneksi Berhasil!
      </h2>
      <p class="text-medium-emphasis mb-8">
        Anda sekarang terhubung ke internet. Anda dapat menutup halaman ini.
      </p>

      <VBtn
        color="primary"
        size="large"
        block
        @click="handleDone"
      >
        Selesai
      </VBtn>
    </VCardText>
  </VCard>
</template>

<style scoped>
.success-animation {
  animation: success-pop-in 0.8s cubic-bezier(0.175, 0.885, 0.32, 1.275) both;
}

@keyframes success-pop-in {
  0% { transform: scale(0); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}
</style>
