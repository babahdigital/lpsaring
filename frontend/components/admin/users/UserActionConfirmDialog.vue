<!-- frontend/components/admin/users/UserActionConfirmDialog.vue -->
<script lang="ts" setup>
interface Props {
  modelValue: boolean
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  color?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  confirmText: 'Ya, Lanjutkan',
  cancelText: 'Batal',
  color: 'primary',
  loading: false,
})

const emit = defineEmits(['update:modelValue', 'confirm'])

function onConfirm() {
  emit('confirm')
}

function onClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    max-width="450"
    persistent
    @update:model-value="onClose"
  >
    <VCard>
      <VCardTitle>
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title">
            <span class="headline">{{ props.title }}</span>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-x" variant="text" @click="onClose" />
          </div>
        </div>
      </VCardTitle>
      <VDivider />
      <VCardText class="pt-4">
        <p v-html="props.message" />
        <p
          v-if="props.color === 'error'"
          class="text-caption text-medium-emphasis mt-2"
        >
          Aksi ini tidak dapat dibatalkan.
        </p>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn
          variant="tonal"
          color="secondary"
          @click="onClose"
        >
          {{ props.cancelText }}
        </VBtn>
        <VBtn
          :color="props.color"
          :loading="props.loading"
          @click="onConfirm"
        >
          {{ props.confirmText }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.dialog-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.dialog-titlebar__title {
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 600px) {
  .dialog-titlebar {
    flex-direction: column;
    align-items: flex-start;
  }

  .dialog-titlebar__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
