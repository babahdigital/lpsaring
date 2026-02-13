<script setup lang="ts">
import { onMounted } from 'vue'
import { navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
})

const authStore = useAuthStore()

onMounted(async () => {
  await authStore.initializeAuth()
  if (authStore.isLoggedIn)
    await navigateTo('/dashboard', { replace: true })
  else
    await navigateTo('/login', { replace: true })
})
</script>

<template>
  <div />
</template>
