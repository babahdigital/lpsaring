<script setup lang="ts">
import { navigateTo, useRoute } from '#imports'

definePageMeta({
  layout: 'blank',
})

if (import.meta.client) {
  const route = useRoute()
  navigateTo({ path: '/admin', query: route.query }, { replace: true })
}
</script>

<template>
  <div />
</template>
