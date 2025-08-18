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
      <VCardTitle class="d-flex align-center">
        <span class="headline">{{ props.title }}</span>
        <VSpacer />
        <VBtn
          icon="tabler-x"
          variant="text"
          @click="onClose"
        />
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
