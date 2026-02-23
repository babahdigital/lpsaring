<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'
import { computed } from 'vue'

const { messages, remove } = useSnackbar()

const iconMap = {
  success: 'tabler-circle-check',
  error: 'tabler-alert-circle',
  info: 'tabler-info-circle',
  warning: 'tabler-alert-triangle',
}

const visibleMessages = computed(() => {
  return (messages.value || []).slice(0, 3)
})
</script>

<template>
  <div class="snackbar-wrapper" aria-live="polite" aria-atomic="true">
    <VSlideYTransition group tag="div">
      <VAlert
        v-for="message in visibleMessages"
        :key="message.id"
        :type="message.type"
        :title="message.title"
        variant="tonal"
        class="snackbar-alert mb-3"
        border="start"
        density="comfortable"
      >
        <template #prepend>
          <VIcon
            :icon="iconMap[message.type]"
            :color="message.type"
            size="22"
          />
        </template>

        <template #append>
          <VBtn density="compact" variant="text" icon @click="remove(message.id)">
            <VIcon icon="tabler-x" :color="message.type" size="20" />
          </VBtn>
        </template>

        <p class="text-body-2 mb-0">
          {{ message.text }}
        </p>
      </VAlert>
    </VSlideYTransition>
  </div>
</template>

<style scoped>
.snackbar-wrapper {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 9999;
  pointer-events: none;
  width: 100%;
  max-width: 420px;
}

.snackbar-alert {
  width: 100%;
  margin: 0;
  pointer-events: auto;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  background-color: rgba(var(--v-theme-surface), 0.88) !important;
}

@media (max-width: 600px) {
  .snackbar-wrapper {
    top: 8px;
    left: 8px;
    right: 8px;
    max-width: none;
  }

  .snackbar-alert {
    margin: 0;
  }
}
</style>
