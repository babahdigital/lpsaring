<script setup lang="ts">
// This page serves as a router for the admin section
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

definePageMeta({
  layout: 'admin',
  middleware: 'admin-only',
})

const router = useRouter()

onMounted(() => {
  // Always redirect to the admin dashboard
  router.replace('/admin/dashboard')
})
</script>

<template>
  <div>
    Redirecting to admin dashboard...
  </div>
</template>
