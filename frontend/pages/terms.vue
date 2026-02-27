<script setup lang="ts">
const route = useRoute()
await navigateTo({ path: '/merchant-center/terms', query: route.query }, { replace: true })
</script>

<template>
  <div />
</template>
