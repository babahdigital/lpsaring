<script setup lang="ts">
import { computed } from 'vue'
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'

import 'perfect-scrollbar/css/perfect-scrollbar.css'

interface Props {
  tag?: string
  options?: Record<string, unknown>
  nativeScroll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  tag: 'div',
  options: () => ({}),
  nativeScroll: false,
})

const mergedOptions = computed(() => ({
  wheelPropagation: false,
  ...(props.options ?? {}),
}))
</script>

<template>
  <component :is="props.tag" v-if="props.nativeScroll" class="app-perfect-scrollbar--native">
    <slot />
  </component>

  <PerfectScrollbar v-else :tag="props.tag" :options="mergedOptions">
    <slot />
  </PerfectScrollbar>
</template>

<style scoped>
.app-perfect-scrollbar--native {
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
}
</style>
