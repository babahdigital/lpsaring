<script setup lang="ts">
const { messages, remove } = useSnackbar()
</script>

<template>
  <div class="app-snackbar-wrapper">
    <TransitionGroup name="slide-fade-right" tag="div">
      <VAlert
        v-for="message in messages"
        :key="message.id"
        :type="message.type"
        :title="message.title"
        variant="elevated"
        closable
        class="mb-4"
        max-width="400px"
        @click:close="remove(message.id)"
      >
        {{ message.text }}
      </VAlert>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.app-snackbar-wrapper {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
  max-width: 400px;
  width: 100%;
}

/* Animasi untuk transisi */
.slide-fade-right-enter-active,
.slide-fade-right-leave-active {
  transition: all 0.4s ease;
}
.slide-fade-right-enter-from,
.slide-fade-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
