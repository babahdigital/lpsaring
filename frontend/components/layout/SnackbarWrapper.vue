<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()

// Peta untuk menentukan ikon secara eksplisit berdasarkan tipe pesan
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
        :icon="iconMap[message.type]"  
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
            variant="text"
            size="small"
            icon="tabler:x"
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