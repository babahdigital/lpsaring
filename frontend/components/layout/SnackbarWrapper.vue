// frontend/components/SnackbarWrapper.vue

<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()

const iconMap = {
  success: 'tabler-circle-check',
  error: 'tabler-alert-circle',
  info: 'tabler-info-circle',
  warning: 'tabler-alert-triangle',
}
</script>

<template>
  <div class="snackbar-wrapper">
    <VScaleTransition
      group
      tag="div"
    >
      <VAlert
        v-for="message in messages"
        :key="message.id"
        :type="message.type"
        :title="message.title"
        variant="tonal"
        class="mb-3"
        max-width="420px"
        elevation="2"
        border="start"
        density="comfortable"
      >
        <template #prepend>
          <VIcon
            :icon="iconMap[message.type]"
            :color="message.type"
            size="24"
          />
        </template>

        <template #append>
          <VBtn
            density="compact"
            variant="text"
            icon
            @click="remove(message.id)"
          >
            <VIcon
              icon="tabler-x"
              :color="message.type"
              size="20"
            />
          </VBtn>
        </template>

        <p
          class="text-body-2 mb-0"
          v-html="message.text"
        />
      </VAlert>
    </VScaleTransition>
  </div>
</template>

<style scoped>
.snackbar-wrapper {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

@media (max-width: 600px) {
  .snackbar-wrapper {
    top: 12px;
    right: 12px;
    left: 12px;
    align-items: stretch;
  }
}
</style>
