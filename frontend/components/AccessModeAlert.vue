<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  accessMode?: string
  ipDetected?: boolean
  macDetected?: boolean
  seemsCaptive?: boolean
  recommendedAction?: string
  webAccessMode?: boolean
  macDetectionAvailable?: boolean
  deviceMismatch?: boolean
  deviceUnregistered?: boolean
  showActions?: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'connect-hotspot'): void
}

const props = withDefaults(defineProps<Props>(), {
  accessMode: 'unknown',
  ipDetected: false,
  macDetected: false,
  seemsCaptive: false,
  recommendedAction: '',
  webAccessMode: false,
  macDetectionAvailable: true,
  deviceMismatch: false,
  deviceUnregistered: false,
  showActions: true,
})

const emit = defineEmits<Emits>()

const shouldShow = computed(() => {
  return (
    props.webAccessMode
    || props.deviceMismatch
    || props.deviceUnregistered
    || (props.accessMode === 'web-direct' && !props.macDetected)
    || props.recommendedAction === 'connect_via_hotspot_for_device_management'
  )
})

const alertColor = computed(() => {
  if (props.deviceMismatch || props.deviceUnregistered)
    return 'warning'
  if (props.webAccessMode)
    return 'info'
  if (props.accessMode === 'captive-portal')
    return 'success'
  return 'info'
})

const alertIcon = computed(() => {
  if (props.deviceMismatch || props.deviceUnregistered)
    return 'tabler-alert-triangle'
  if (props.webAccessMode)
    return 'tabler-world-www'
  if (props.accessMode === 'captive-portal')
    return 'tabler-wifi'
  return 'tabler-info-circle'
})

const alertTitle = computed(() => {
  if (props.deviceMismatch)
    return 'Perangkat Berbeda Terdeteksi'
  if (props.deviceUnregistered)
    return 'Perangkat Belum Terdaftar'
  if (props.webAccessMode)
    return 'Akses Web Mode'
  if (props.accessMode === 'captive-portal')
    return 'Mode Captive Portal'
  if (!props.macDetectionAvailable)
    return 'Deteksi Perangkat Terbatas'
  return 'Informasi Akses'
})

const alertMessage = computed(() => {
  if (props.deviceMismatch) {
    return 'Anda menggunakan perangkat yang berbeda dari yang terdaftar. Untuk mengelola perangkat, silakan hubungkan via hotspot Wi-Fi.'
  }

  if (props.deviceUnregistered) {
    return 'Perangkat yang Anda gunakan belum terdaftar dalam sistem. Silakan daftarkan perangkat ini untuk menggunakan semua fitur dengan optimal.'
  }

  if (props.webAccessMode && !props.macDetectionAvailable) {
    return 'Anda mengakses portal melalui browser web biasa. Untuk fitur manajemen perangkat yang lengkap, hubungkan ke Wi-Fi hotspot terlebih dahulu.'
  }

  if (props.accessMode === 'web-direct' && !props.macDetected) {
    return 'Akses web langsung tidak dapat mendeteksi informasi perangkat. Hubungkan ke Wi-Fi hotspot untuk fitur device management.'
  }

  if (props.recommendedAction === 'connect_via_hotspot_for_device_management') {
    return 'Untuk mengelola dan sinkronisasi perangkat, pastikan Anda terhubung ke jaringan Wi-Fi hotspot.'
  }

  return 'Mode akses terdeteksi. Beberapa fitur mungkin terbatas berdasarkan cara Anda mengakses portal.'
})

function handleConnectViaHotspot() {
  emit('connect-hotspot')
}
</script>

<template>
  <VAlert
    v-if="shouldShow"
    :color="alertColor"
    :icon="alertIcon"
    variant="tonal"
    class="mb-4"
    closable
    @click:close="$emit('close')"
  >
    <VAlertTitle>{{ alertTitle }}</VAlertTitle>
    <div class="mt-2">
      {{ alertMessage }}
    </div>

    <template v-if="showActions" #append>
      <VBtn
        v-if="recommendedAction === 'connect_via_hotspot_for_device_management'"
        color="primary"
        variant="outlined"
        size="small"
        class="mt-3"
        @click="handleConnectViaHotspot"
      >
        <VIcon icon="tabler-wifi" start />
        Hubungkan via Hotspot
      </VBtn>
    </template>
  </VAlert>
</template>

<style scoped>
/* Custom styles if needed */
</style>
