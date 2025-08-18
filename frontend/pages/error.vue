<script setup lang="ts">
definePageMeta({
  layout: 'blank',
})

useHead({
  title: 'Error - Portal Hotspot',
})

const route = useRoute()
const router = useRouter()

// Get error message from query params
const errorCode = route.query.code as string || '500'
const errorMessage = computed(() => {
  switch (errorCode) {
    case '404':
      return 'Halaman tidak ditemukan. Silakan periksa alamat yang Anda masukkan.'
    case '403':
      return 'Akses ditolak. Anda tidak memiliki izin untuk mengakses halaman ini.'
    case '500':
      return 'Terjadi kesalahan server. Silakan coba lagi dalam beberapa saat.'
    case 'network':
      return 'Tidak dapat terhubung ke server. Periksa koneksi internet Anda.'
    case 'timeout':
      return 'Koneksi timeout. Server membutuhkan waktu terlalu lama untuk merespons.'
    case 'captive':
      return 'Browser captive terdeteksi. Beberapa fitur mungkin terbatas.'
    default:
      return 'Terjadi kesalahan yang tidak diketahui. Silakan coba lagi.'
  }
})

const { checkIsCaptiveBrowser, handleCaptiveNavigation } = useCaptiveBrowser()

function handleRetry() {
  const isCaptive = checkIsCaptiveBrowser()

  if (isCaptive) {
    // Untuk captive browser, reload halaman
    window.location.reload()
  }
  else {
    // Untuk browser normal, gunakan router
    router.go(-1)
  }
}

function goToLogin() {
  const isCaptive = checkIsCaptiveBrowser()

  if (isCaptive) {
    // Gunakan window.location untuk captive browser
    handleCaptiveNavigation('/captive')
  }
  else {
    // Gunakan router untuk browser normal
    navigateTo('/login')
  }
}

// Auto-redirect jika di captive browser dan ada parameter MikroTik
onMounted(() => {
  if (import.meta.client) {
    const urlParams = new URLSearchParams(window.location.search)
    const clientIp = urlParams.get('client_ip')
    const clientMac = urlParams.get('client_mac')

    if ((clientIp || clientMac) && checkIsCaptiveBrowser()) {
      console.log('[ERROR-PAGE] Auto-redirecting captive browser to captive portal')
      setTimeout(() => {
        const captiveUrl = `/captive?${urlParams.toString()}`
        handleCaptiveNavigation(captiveUrl)
      }, 2000)
    }
  }
})
</script>

<template>
  <div class="error-page">
    <VContainer fluid class="fill-height pa-4">
      <VRow align="center" justify="center">
        <VCol cols="12" sm="10" md="6" lg="4">
          <VCard class="pa-6 text-center" elevation="4" rounded="lg">
            <VIcon color="error" size="64" class="mb-4">
              mdi-wifi-off
            </VIcon>

            <h2 class="text-h5 font-weight-bold mb-3">
              Koneksi Bermasalah
            </h2>

            <p class="text-medium-emphasis mb-4">
              {{ errorMessage }}
            </p>

            <VDivider class="my-4" />

            <div class="text-left">
              <h3 class="text-h6 mb-2">Langkah Perbaikan:</h3>
              <ol class="text-body-2 text-medium-emphasis">
                <li class="mb-1">Pastikan WiFi terhubung</li>
                <li class="mb-1">Matikan dan nyalakan WiFi</li>
                <li class="mb-1">Restart aplikasi browser</li>
                <li class="mb-1">Hubungi administrator jika masalah berlanjut</li>
              </ol>
            </div>

            <VBtn
              color="primary"
              block
              size="large"
              class="mt-4"
              @click="handleRetry"
            >
              Coba Lagi
            </VBtn>

            <VBtn
              variant="text"
              size="small"
              class="mt-2"
              @click="goToLogin"
            >
              Kembali ke Halaman Utama
            </VBtn>
          </VCard>
        </VCol>
      </VRow>
    </VContainer>
  </div>
</template>

<style scoped>
.error-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

ol {
  padding-left: 1.2rem;
}

li {
  margin-bottom: 0.25rem;
}
</style>
