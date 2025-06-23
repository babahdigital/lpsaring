<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()
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
        closable
        class="mb-4"
        max-width="400px"
        elevation="6"
        border="start"
      >
        <p
          class="text-body-2 mb-0"
          v-html="message.text"
        />
        <template #close>
          <VBtn
            icon="tabler-x"
            variant="text"
            size="small"
            @click="remove(message.id)"
          />
        </template>
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
