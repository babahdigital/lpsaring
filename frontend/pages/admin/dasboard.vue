<script setup lang="ts">
import { navigateTo } from '#imports'

definePageMeta({
  layout: 'blank',
})

if (import.meta.client) {
  navigateTo('/admin/dashboard', { replace: true })
}
</script>

<template>
  <div />
</template>
