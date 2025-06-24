// frontend/components/SnackbarWrapper.vue

<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()

const iconMap = {
  success: 'tabler:circle-check',
  error: 'tabler:alert-circle',
  info: 'tabler:info-circle',
  warning: 'tabler:alert-triangle',
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
        variant="elevated"
        class="mb-4"
        max-width="400px"
        elevation="6"
        border="start"
      >
        <template #prepend>
          <VIcon
            :icon="iconMap[message.type]"
            color="white"
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
              icon="tabler:x"
              color="white"
              size="22"
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
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
</style>