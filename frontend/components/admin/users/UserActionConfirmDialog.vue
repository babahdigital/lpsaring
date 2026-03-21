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
      <VCardTitle class="confirm-dialog__hero text-white">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title confirm-dialog__hero-titleWrap">
            <div class="confirm-dialog__hero-icon">
              <VIcon :icon="dialogToneMeta.icon" size="22" />
            </div>
            <div class="confirm-dialog__hero-copy">
              <span class="headline">{{ props.title }}</span>
              <div class="confirm-dialog__hero-subtitle text-white">
                {{ dialogToneMeta.subtitle }}
              </div>
            </div>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-x" variant="text" class="text-white" @click="onClose" />
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
      <VCardActions class="pa-4 pt-0">
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
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.confirm-dialog__hero-subtitle {
  font-size: 0.88rem;
  line-height: 1.45;
  opacity: 0.86;
}

.confirm-dialog__message {
  font-size: 0.96rem;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.82);
}

.confirm-dialog__warning {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-error), 0.08);
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

  .confirm-dialog__hero {
    padding: 16px 16px 14px;
  }

  .confirm-dialog__hero-icon {
    width: 36px;
    height: 36px;
    border-radius: 12px;
  }

  .confirm-dialog__hero-subtitle {
    font-size: 0.8rem;
  }
}
</style>
