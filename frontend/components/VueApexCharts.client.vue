<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

const VueApexCharts = defineAsyncComponent(async () => {
  const module = await import('vue3-apexcharts')
  return module.default
})

defineOptions({
  inheritAttrs: false,
})
</script>

<template>
  <VueApexCharts v-bind="$attrs" />
</template>
