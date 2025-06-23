<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

const { messages, remove } = useSnackbar()

// Peta untuk menentukan ikon secara eksplisit berdasarkan tipe pesan.
// Tidak ada perubahan di sini, ini sudah benar.
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
            class="ms-1"
          />
        </template>

        <template #append>
          <VBtn
            density="compact"
            icon="tabler:x"
            variant="text"
            @click="remove(message.id)"
          />
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
