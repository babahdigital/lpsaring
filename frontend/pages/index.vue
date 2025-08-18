<script setup lang="ts">
import { useAuthStore } from '~/store/auth'

/**
 * Halaman root (/) menggunakan layout blank dan bertindak sebagai redirect page.
 * 
 * Jika pengguna sudah login: redirect ke /dashboard
 * Jika pengguna belum login: redirect ke /login
 */

definePageMeta({
  layout: 'blank',
  // Disable SSR untuk halaman ini karena kita perlu cek auth state
  ssr: false
})

const authStore = useAuthStore()
const router = useRouter()

// Setelah mounting, langsung redirect sesuai status autentikasi
onMounted(async () => {
  console.log('[ROOT-PAGE] Memulai redirect berdasarkan status autentikasi')
  
  // Tunggu auth check selesai untuk mengambil keputusan tepat
  if (!authStore.isAuthCheckDone) {
    await nextTick()
    // Tunggu lagi jika masih belum selesai
    if (!authStore.isAuthCheckDone) {
      console.log('[ROOT-PAGE] Menunggu auth check selesai...')
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }
  
  // Redirect ke halaman yang sesuai
  const targetPath = authStore.isLoggedIn ? '/dashboard' : '/login'
  console.log(`[ROOT-PAGE] Mengarahkan ke ${targetPath}`)
  
  await router.replace(targetPath)
})
</script>

<template>
  <div class="d-flex flex-column align-center justify-center min-vh-100">
    <v-progress-circular
      indeterminate
      color="primary"
      size="48"
    ></v-progress-circular>
    <p class="mt-4 text-body-1 text-medium-emphasis">
      Mengarahkan ke halaman yang sesuai...
    </p>
  </div>
</template>
