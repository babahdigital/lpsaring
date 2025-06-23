<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { usePromoStore } from '~/store/promo'

const { mobile: isMobile } = useDisplay()
const promoStore = usePromoStore()
const { isPromoDialogVisible, activePromo } = storeToRefs(promoStore)

const dialogVisible = ref(false)

const bonusGbDisplay = computed(() => {
  if (!activePromo.value?.bonus_value_mb)
    return '0'
  const gbValue = activePromo.value.bonus_value_mb / 1024
  return Number.isInteger(gbValue) ? gbValue.toString() : gbValue.toFixed(1)
})

watch(isPromoDialogVisible, (newValue) => {
  if (newValue && activePromo.value?.event_type === 'BONUS_REGISTRATION') {
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
  if (activePromo.value?.event_type === 'BONUS_REGISTRATION') {
    promoStore.resetPromo()
  }
}
</script>

<template>
  <VDialog
    v-model="dialogVisible"
    :max-width="isMobile ? '95%' : '480px'"
    transition="dialog-bottom-transition"
    @after-leave="onDialogClose"
  >
    <VCard v-if="activePromo" class="promo-dialog-card">
      <VCardTitle class="promo-header pa-0">
        <VIcon icon="tabler-gift" class="promo-icon" />
      </VCardTitle>

      <VCardText class="text-center pt-8">
        <h3 class="text-h4 font-weight-bold text-primary mb-2">
          Bonus Pendaftaran!
        </h3>
        <p class="text-h6 font-weight-regular text-medium-emphasis mb-6">
          {{ activePromo.name }}
        </p>

        <p class="text-body-1 mb-4">
          Selamat datang! Sebagai pengguna baru, Anda berhak mendapatkan:
        </p>

        <div class="bonus-display-container">
          <div class="bonus-value">
            <span class="bonus-number">{{ bonusGbDisplay }}</span>
            <span class="bonus-unit">GB</span>
          </div>
          <VDivider vertical class="mx-4" />
          <div class="bonus-value">
            <span class="bonus-number">{{ activePromo.bonus_duration_days }}</span>
            <span class="bonus-unit">Hari</span>
          </div>
        </div>

        <p class="text-caption text-disabled mt-6">
          Bonus akan otomatis diterapkan pada akun Anda setelah disetujui oleh Admin.
        </p>
      </VCardText>

      <VCardActions class="pa-4 pt-0">
        <VBtn
          color="primary"
          variant="flat"
          block
          size="large"
          @click="closeDialog"
        >
          Mengerti
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.promo-dialog-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow: hidden;
}
.promo-header {
  height: 120px;
  background: linear-gradient(45deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  display: flex;
  align-items: center;
  justify-content: center;
  animation: background-pan 3s ease-in-out infinite alternate;
}
@keyframes background-pan {
  from { background-position: 0% center; }
  to { background-position: 100% center; }
}
.promo-icon {
  font-size: 64px;
  color: white;
  opacity: 0.8;
  transform: rotate(-15deg);
}
.bonus-display-container {
  display: flex;
  justify-content: center;
  align-items: stretch;
  background-color: rgba(var(--v-theme-on-surface), 0.05);
  border-radius: 12px;
  padding: 1rem;
  margin: 1.5rem 0;
}
.bonus-value {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-grow: 1;
}
.bonus-number {
  font-size: 2.75rem;
  font-weight: 700;
  line-height: 1;
  color: rgb(var(--v-theme-secondary));
}
.bonus-unit {
  font-size: 1rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  margin-top: 4px;
}
</style>
