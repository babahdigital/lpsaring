<script setup lang="ts">
import { computed } from 'vue'
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'

import 'perfect-scrollbar/css/perfect-scrollbar.css'

interface Props {
  tag?: string
  options?: Record<string, unknown>
}

const props = withDefaults(defineProps<Props>(), {
  tag: 'div',
  options: () => ({}),
})

const mergedOptions = computed(() => ({
  wheelPropagation: false,
  ...(props.options ?? {}),
}))
</script>

<template>
  <PerfectScrollbar :tag="props.tag" :options="mergedOptions">
    <slot />
  </PerfectScrollbar>
</template>
