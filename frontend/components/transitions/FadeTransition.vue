<!-- components/transitions/FadeTransition.vue -->
<!-- Custom transition yang kompatibel dengan Nuxt 4 -->
<script setup lang="ts">
// Kompatibel dengan Nuxt 4 dan Vue 3
// Menggunakan native Vue Transition dengan Tailwind classes
</script>

<template>
  <Transition
    name="fade"
    enter-active-class="transition-opacity duration-300 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition-opacity duration-200 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
    appear
  >
    <slot />
  </Transition>
</template>

<style scoped>
/* Fallback CSS jika Tailwind tidak tersedia */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.fade-enter-to,
.fade-leave-from {
  opacity: 1;
}
</style>
