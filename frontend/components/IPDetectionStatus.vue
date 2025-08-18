<!-- components/IPDetectionStatus.vue -->
<script setup lang="ts">
import { computed, toRefs } from 'vue'

import type { ClientInfo } from '~/composables/useClientGlobalState'

interface Props {
  clientInfo?: ClientInfo | null
  isDetecting?: boolean
  detectionData?: any
  showDebugInfo?: boolean
  showOnSuccess?: boolean
}

interface Emits {
  (event: 'refresh'): void
}

const props = withDefaults(defineProps<Props>(), {
  clientInfo: null,
  isDetecting: false,
  detectionData: null,
  showDebugInfo: false,
  showOnSuccess: true,
})

const emit = defineEmits<Emits>()

const { clientInfo, isDetecting, detectionData, showDebugInfo, showOnSuccess } = toRefs(props)

// Status computation
const statusInfo = computed(() => {
  if (!clientInfo.value) {
    if (isDetecting.value) {
      return {
        type: 'detecting',
        title: 'Mendeteksi Jaringan...',
        message: 'Sedang menganalisis koneksi Anda',
        color: 'info',
        icon: 'tabler-loader',
      }
    }

    return {
      type: 'unknown',
      title: 'Deteksi Jaringan Belum Dilakukan',
      message: 'Klik refresh untuk mendeteksi IP lokal',
      color: 'warning',
      icon: 'tabler-network-off',
    }
  }

  const info = clientInfo.value

  // Success case
  if (info.ip_detected && info.mac_detected) {
    return {
      type: 'success',
      title: 'Jaringan Terdeteksi',
      message: `IP: ${info.detected_ip} | MAC: ${info.detected_mac}`,
      color: 'success',
      icon: 'tabler-network',
    }
  }

  // Partial success - IP only
  if (info.ip_detected && !info.mac_detected) {
    const guidance = info.user_guidance || 'IP terdeteksi, mencari MAC address...'
    return {
      type: 'partial',
      title: 'IP Terdeteksi',
      message: `${info.detected_ip} | ${guidance}`,
      color: 'warning',
      icon: 'tabler-network',
    }
  }

  // Limited detection
  if (info.access_mode === 'web-direct') {
    return {
      type: 'limited',
      title: 'Akses Browser Langsung',
      message: info.user_guidance || 'Deteksi terbatas untuk akses web langsung',
      color: 'info',
      icon: 'tabler-browser',
    }
  }

  // Error case
  return {
    type: 'error',
    title: 'Deteksi Jaringan Gagal',
    message: info.user_guidance || 'Tidak dapat mendeteksi IP lokal',
    color: 'error',
    icon: 'tabler-network-off',
  }
})

// UI properties
const statusColor = computed(() => statusInfo.value.color)
const statusTitle = computed(() => statusInfo.value.title)
const statusMessage = computed(() => statusInfo.value.message)
const statusIcon = computed(() => statusInfo.value.icon)

const statusVariant = computed(() => {
  const type = statusInfo.value.type
  return type === 'success' ? 'tonal' : 'outlined'
})

const shouldShowStatus = computed(() => {
  if (isDetecting.value)
    return true
  if (!clientInfo.value)
    return true

  const info = clientInfo.value
  const isSuccess = info.ip_detected && info.mac_detected

  return showOnSuccess.value || !isSuccess
})

const showRefreshButton = computed(() => {
  return !isDetecting.value && statusInfo.value.type !== 'detecting'
})

// Methods
function refreshDetection() {
  emit('refresh')
}
</script>

<template>
  <VCard
    v-if="shouldShowStatus"
    :color="statusColor"
    :variant="statusVariant"
    class="mb-4"
  >
    <VCardText class="d-flex align-center">
      <VIcon
        :icon="statusIcon"
        :color="statusColor"
        class="me-3"
        size="20"
      />

      <div class="flex-grow-1">
        <div class="text-body-2 font-weight-medium">
          {{ statusTitle }}
        </div>
        <div
          v-if="statusMessage"
          class="text-caption mt-1"
          :class="statusColor === 'error' ? 'text-error' : 'text-medium-emphasis'"
        >
          {{ statusMessage }}
        </div>
      </div>

      <VBtn
        v-if="showRefreshButton"
        variant="text"
        size="small"
        :loading="isDetecting"
        @click="refreshDetection"
      >
        <VIcon
          icon="tabler-refresh"
          size="16"
        />
      </VBtn>
    </VCardText>

    <!-- Enhanced details for debugging (development only) -->
    <VExpansionPanels
      v-if="showDebugInfo && detectionData"
      variant="accordion"
      class="mt-2"
    >
      <VExpansionPanel>
        <VExpansionPanelTitle class="text-caption">
          <VIcon
            icon="tabler-bug"
            size="14"
            class="me-2"
          />
          Debug Information
        </VExpansionPanelTitle>
        <VExpansionPanelText>
          <pre class="text-caption">{{ JSON.stringify(detectionData, null, 2) }}</pre>
        </VExpansionPanelText>
      </VExpansionPanel>
    </VExpansionPanels>
  </VCard>
</template>

<style scoped>
pre {
  font-size: 10px;
  line-height: 1.2;
  max-height: 200px;
  overflow: auto;
  background: rgba(var(--v-theme-surface-variant), 0.1);
  padding: 8px;
  border-radius: 4px;
}
</style>
