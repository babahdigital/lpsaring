<script setup lang="ts">
import { computed } from 'vue'
import { ref } from 'vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Login Hotspot Diperlukan' })

const runtimeConfig = useRuntimeConfig()
const { $api } = useNuxtApp()
const rechecking = ref(false)
const statusMessage = ref('')

const appBaseUrl = computed(() => String(runtimeConfig.public.appBaseUrl ?? '').trim())
const mikrotikLoginUrl = computed(() => {
  const appLink = String(runtimeConfig.public.appLinkMikrotik ?? '').trim()
  if (appLink)
    return appLink
  return String(runtimeConfig.public.mikrotikLoginUrl ?? '').trim()
})

const fallbackLoginPath = computed(() => {
  const base = appBaseUrl.value
  if (!base)
    return '/captive'
  return `${base.replace(/\/+$/, '')}/captive`
})

const loginHotspotUrl = computed(() => mikrotikLoginUrl.value || fallbackLoginPath.value)

function openHotspotLogin() {
  if (!import.meta.client)
    return
  window.location.href = loginHotspotUrl.value
}

async function continueToPortal() {
  rechecking.value = true
  statusMessage.value = ''
  try {
    const response = await $api<{ hotspot_login_required?: boolean | null, hotspot_session_active?: boolean | null }>('/auth/hotspot-session-status', {
      method: 'GET',
    })

    const hotspotRequired = response?.hotspot_login_required === true
    const hotspotActive = response?.hotspot_session_active === true

    if (!hotspotRequired || hotspotActive) {
      await navigateTo('/dashboard', { replace: true })
      return
    }

    statusMessage.value = 'Sesi hotspot belum aktif. Silakan login MikroTik terlebih dahulu, lalu cek lagi.'
  }
  catch {
    statusMessage.value = 'Gagal memeriksa status hotspot. Pastikan koneksi portal tersedia lalu coba lagi.'
  }
  finally {
    rechecking.value = false
  }
}
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4 pa-sm-6">
    <VCard class="auth-card" max-width="460" width="100%">
      <VCardText class="text-center pa-6 pa-sm-8">
        <VIcon icon="tabler-router" size="56" color="warning" class="mb-4" />

        <h4 class="text-h5 text-sm-h4 mb-2">
          Login Hotspot MikroTik Diperlukan
        </h4>

        <p class="text-medium-emphasis mb-6 text-body-2 text-sm-body-1">
          Anda sudah berhasil login ke portal. Agar internet aktif, silakan login hotspot MikroTik terlebih dahulu.
        </p>

        <VAlert type="info" variant="tonal" density="comfortable" class="mb-6 text-start">
          Jika sudah login hotspot, klik <strong>Saya Sudah Login Hotspot</strong> untuk lanjut ke portal.
        </VAlert>

        <VAlert
          v-if="statusMessage"
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mb-6 text-start"
        >
          {{ statusMessage }}
        </VAlert>

        <div class="d-flex flex-column ga-3">
          <VBtn color="primary" size="large" block @click="openHotspotLogin">
            Buka Login MikroTik
          </VBtn>

          <VBtn variant="tonal" color="success" size="large" block :loading="rechecking" :disabled="rechecking" @click="continueToPortal">
            Saya Sudah Login Hotspot
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.auth-wrapper {
  min-block-size: 100dvh;
}
</style>
