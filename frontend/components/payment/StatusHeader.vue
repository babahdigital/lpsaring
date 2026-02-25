<script setup lang="ts">
import type { PropType } from 'vue'

defineProps({
  alertType: {
    type: String as PropType<'success' | 'warning' | 'error' | 'info'>,
    required: true,
  },
  alertIcon: {
    type: String,
    required: true,
  },
  alertTitle: {
    type: String,
    required: true,
  },
  detailMessage: {
    type: String,
    required: true,
  },
  finalStatus: {
    type: String,
    required: true,
  },
  isPublicView: {
    type: Boolean,
    default: false,
  },
  paymentMethodBadgeLabel: {
    type: String,
    default: null,
  },
})
</script>

<template>
  <div class="px-sm-8 px-6 pt-10 pb-6 text-center">
    <v-avatar size="80" :color="alertType" variant="tonal" class="mb-5">
      <v-icon :icon="alertIcon" :color="alertType" size="38" />
    </v-avatar>

    <h1 class="text-h5 font-weight-bold mb-2 text-high-emphasis finish-header-title">
      {{ alertTitle }}
    </h1>

    <p class="text-body-1 text-medium-emphasis finish-header-desc" style="line-height: 1.7;">
      {{ detailMessage }}
    </p>

    <div class="d-flex justify-center flex-wrap mt-5" style="gap: 10px;">
      <v-chip :color="alertType" variant="tonal" class="font-weight-bold">
        {{ finalStatus }}
      </v-chip>
      <v-chip v-if="isPublicView" color="info" variant="tonal" class="font-weight-medium">
        Link Publik
      </v-chip>
      <v-chip v-if="paymentMethodBadgeLabel" color="primary" variant="tonal" class="font-weight-medium">
        {{ paymentMethodBadgeLabel }}
      </v-chip>
    </div>

    <p v-if="finalStatus === 'SUCCESS'" class="text-body-2 text-medium-emphasis mt-4 mb-0">
      Silakan sambungkan ulang WiFi jika belum aktif.
    </p>
  </div>
</template>
