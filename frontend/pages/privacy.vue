<script setup lang="ts">
const route = useRoute()
await navigateTo({ path: '/merchant-center/privacy', query: route.query }, { replace: true })
</script>

<template>
  <div />
</template>
