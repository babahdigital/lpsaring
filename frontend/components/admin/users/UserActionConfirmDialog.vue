<!-- frontend/components/admin/users/UserActionConfirmDialog.vue -->
<script lang="ts" setup>
import { computed } from 'vue'

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

const dialogToneMeta = computed(() => {
  if (props.color === 'error') {
    return {
      icon: 'tabler-alert-triangle',
      subtitle: 'Pastikan data yang dipilih sudah benar sebelum melanjutkan aksi permanen ini.',
    }
  }

  if (props.color === 'warning') {
    return {
      icon: 'tabler-alert-circle',
      subtitle: 'Tinjau kembali dampaknya lalu lanjutkan saat sudah yakin dengan perubahan ini.',
    }
  }

  return {
    icon: 'tabler-bolt',
    subtitle: 'Konfirmasi singkat agar tindakan admin tetap rapi dan tidak terpicu tanpa sengaja.',
  }
})

function onConfirm() {
  if (props.loading)
    return

  emit('confirm')
}

function onClose() {
  if (props.loading)
    return

  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    max-width="450"
    class="confirm-dialog"
    persistent
    @update:model-value="onClose"
  >
    <VCard>
      <VCardTitle class="confirm-dialog__hero text-white">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title confirm-dialog__hero-titleWrap">
            <div class="confirm-dialog__hero-icon">
              <VIcon :icon="dialogToneMeta.icon" size="22" />
            </div>
            <div class="confirm-dialog__hero-copy">
              <div class="confirm-dialog__hero-heading">
                {{ props.title }}
              </div>
              <div class="confirm-dialog__hero-subtitle text-white">
                {{ dialogToneMeta.subtitle }}
              </div>
            </div>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn :disabled="props.loading" icon="tabler-x" variant="text" class="text-white" @click="onClose" />
          </div>
        </div>
      </VCardTitle>
      <VDivider />
      <VCardText class="pt-5 pb-4 px-4 px-md-5">
        <div class="confirm-dialog__message" v-html="props.message" />
        <p
          v-if="props.color === 'error'"
          class="confirm-dialog__warning text-caption text-medium-emphasis mt-3"
        >
          Aksi ini tidak dapat dibatalkan.
        </p>
      </VCardText>
      <VCardActions class="confirm-dialog__actions pa-4 pt-0">
        <VSpacer />
        <VBtn
          class="confirm-dialog__actionBtn"
          :disabled="props.loading"
          variant="tonal"
          color="secondary"
          @click="onClose"
        >
          {{ props.cancelText }}
        </VBtn>
        <VBtn
          class="confirm-dialog__actionBtn"
          :color="props.color"
          :loading="props.loading"
          :disabled="props.loading"
          @click="onConfirm"
        >
          {{ props.confirmText }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.confirm-dialog :deep(.v-overlay__content) {
  width: min(450px, calc(100vw - 24px));
  max-width: min(450px, calc(100vw - 24px));
  margin: 12px;
}

.confirm-dialog :deep(.v-card-title) {
  white-space: normal;
}

.dialog-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.dialog-titlebar__title {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1 1 auto;
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.confirm-dialog__hero {
  padding: 18px 20px 16px;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)) 0%, rgba(var(--v-theme-primary), 0.82) 100%);
}

.confirm-dialog__hero-titleWrap {
  align-items: flex-start;
}

.confirm-dialog__hero-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  flex: 0 0 auto;
}

.confirm-dialog__hero-copy {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.confirm-dialog__hero-heading {
  overflow-wrap: anywhere;
  color: inherit;
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.25;
  white-space: normal;
}

.confirm-dialog__hero-subtitle {
  overflow-wrap: anywhere;
  font-size: 0.88rem;
  line-height: 1.45;
  opacity: 0.86;
  white-space: normal;
}

.confirm-dialog__message {
  overflow-wrap: anywhere;
  font-size: 0.96rem;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.82);
  white-space: normal;
}

.confirm-dialog__message :deep(strong) {
  font-weight: 700;
}

.confirm-dialog__warning {
  overflow-wrap: anywhere;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-error), 0.08);
  white-space: normal;
}

.confirm-dialog__actions {
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.confirm-dialog__actionBtn {
  min-width: 124px;
}

@media (max-width: 600px) {
  .dialog-titlebar {
    align-items: flex-start;
  }

  .dialog-titlebar__actions {
    margin-inline-start: auto;
    width: auto;
  }

  .dialog-titlebar__title {
    width: calc(100% - 52px);
  }

  .confirm-dialog__hero {
    padding: 16px 16px 14px;
  }

  .confirm-dialog__hero-icon {
    width: 36px;
    height: 36px;
    border-radius: 12px;
  }

  .confirm-dialog__hero-heading {
    font-size: 1.05rem;
  }

  .confirm-dialog__hero-subtitle {
    font-size: 0.8rem;
  }

  .confirm-dialog__actions {
    justify-content: stretch;
  }

  .confirm-dialog__actions :deep(.v-spacer) {
    display: none;
  }

  .confirm-dialog__actionBtn {
    flex: 1 1 100%;
    width: 100%;
    min-width: 0;
  }
}
</style>
