<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { usePromoStore } from '~/store/promo'

const { mobile: isMobile } = useDisplay()
const promoStore = usePromoStore()
const { isPromoDialogVisible, activePromo } = storeToRefs(promoStore)
const dialogVisible = ref(false)

watch(isPromoDialogVisible, (newValue) => {
  if (newValue && activePromo.value?.event_type === 'GENERAL_ANNOUNCEMENT') {
    dialogVisible.value = true
  }
  else {
    dialogVisible.value = false
  }
})

function closeDialog() {
  promoStore.hidePromoDialog()
}

function onDialogClose() {
  if (activePromo.value?.event_type === 'GENERAL_ANNOUNCEMENT') {
    promoStore.resetPromo()
  }
}
</script>

<template>
  <VDialog
    v-model="dialogVisible"
    :max-width="isMobile ? '95%' : '520px'"
    transition="dialog-bottom-transition"
    @after-leave="onDialogClose"
  >
    <VCard v-if="activePromo" class="promo-dialog-card">
      <VCardTitle class="promo-header pa-0">
        <VIcon icon="tabler-broadcast" class="promo-icon" />
      </VCardTitle>

      <VCardText class="text-center pt-8 px-sm-8">
        <h3 class="text-h4 font-weight-bold text-primary mb-2">
          Pengumuman Penting
        </h3>
        <p class="text-h6 font-weight-regular text-medium-emphasis mb-6">
          {{ activePromo.name }}
        </p>

        <VDivider class="my-6" />

        <div class="description-content">
          <p class="text-body-1" style="white-space: pre-wrap;">
            {{ activePromo.description || 'Tidak ada informasi lebih lanjut.' }}
          </p>
        </div>
      </VCardText>

      <VCardActions class="pa-4 pt-2 mt-4">
        <VBtn
          color="primary"
          variant="flat"
          block
          size="large"
          @click="closeDialog"
        >
          Saya Mengerti
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.promo-dialog-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow: hidden;
  border-radius: 16px !important;
}
.promo-header {
  height: 120px;
  background: linear-gradient(135deg, rgb(var(--v-theme-info)), rgb(var(--v-theme-primary)));
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.promo-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px);
  background-size: 1rem 1rem;
}
.promo-icon {
  font-size: 64px;
  color: white;
  opacity: 0.9;
  z-index: 1;
  animation: pulse-icon 3s infinite ease-in-out;
}
@keyframes pulse-icon {
  0%, 100% {
    transform: scale(1);
    opacity: 0.9;
  }
  50% {
    transform: scale(1.1);
    opacity: 1;
  }
}
.description-content {
  max-height: 250px;
  overflow-y: auto;
  padding: 0 12px;
  margin: 0 -12px;
  text-align: left;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.description-content::-webkit-scrollbar {
  width: 6px;
}
.description-content::-webkit-scrollbar-track {
  background: transparent;
}
.description-content::-webkit-scrollbar-thumb {
  background-color: rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 10px;
}
</style>
