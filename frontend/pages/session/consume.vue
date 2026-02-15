<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
})

useHead({ title: 'Membuka Sesi' })

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const loading = ref(true)

function sanitizeNextPath(value: string | null): string {
  if (!value)
    return '/akun'
  if (!value.startsWith('/') || value.startsWith('//'))
    return '/akun'
  if (value.includes('://'))
    return '/akun'
  return value
}

onMounted(async () => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  const nextPath = sanitizeNextPath(typeof route.query.next === 'string' ? route.query.next : null)

  if (!token) {
    addSnackbar({
      title: 'Token tidak valid',
      text: 'Session token tidak ditemukan atau sudah kedaluwarsa.',
      type: 'error',
    })
    loading.value = false
    return
  }

  const success = await authStore.consumeSessionToken(token)
  loading.value = false

  if (success === true)
    await router.replace(nextPath)
})
</script>

<template>
  <div class="d-flex flex-column align-center justify-center" style="min-height: 60vh;">
    <VProgressCircular v-if="loading" indeterminate color="primary" size="48" />
    <div v-else>
      <h3 class="text-h6">Sesi siap digunakan</h3>
      <p>Jika tidak teralihkan otomatis, silakan kembali ke dashboard.</p>
    </div>
  </div>
</template>
