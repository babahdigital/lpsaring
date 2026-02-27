<script setup lang="ts">
const route = useRoute()
await navigateTo({ path: '/policy/inactive', query: route.query }, { replace: true })
</script>

<template>
  <div />
</template>
