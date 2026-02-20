<script setup lang="ts">
import { computed } from 'vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Portal Info' })

const config = useRuntimeConfig()
const appBaseUrl = computed(() => (config.public.appBaseUrl || '').replace(/\/$/, ''))
const appLinkMikrotik = computed(() => config.public.appLinkMikrotik || '')

const loginUrl = computed(() => (appBaseUrl.value ? `${appBaseUrl.value}/login` : '/login'))
const captiveUrl = computed(() => (appBaseUrl.value ? `${appBaseUrl.value}/captive` : '/captive'))
const dashboardUrl = computed(() => (appBaseUrl.value ? `${appBaseUrl.value}/dashboard` : '/dashboard'))
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="720">
      <VCardText class="text-center">
        <VIcon icon="tabler-router" size="56" class="mb-4" color="primary" />
        <h4 class="text-h5 mb-2">Portal Info</h4>
        <p class="text-medium-emphasis mb-6">
          Halaman ini membantu ketika perangkat sudah online tetapi IP/MAC belum terbaca di portal.
        </p>
      </VCardText>

      <VCardText class="pt-0">
        <VAlert type="info" variant="tonal" density="compact" class="mb-4">
          Jika halaman login hotspot tidak muncul otomatis, buka link berikut agar IP/MAC terbaca:
        </VAlert>
        <div class="d-flex flex-column gap-3">
          <VBtn
            v-if="appLinkMikrotik"
            :href="appLinkMikrotik"
            target="_blank"
            rel="noopener"
            color="primary"
            variant="flat"
          >
            Buka Login Mikrotik
          </VBtn>
          <VBtn :href="captiveUrl" color="secondary" variant="tonal">
            Buka Captive Portal
          </VBtn>
          <VBtn :href="loginUrl" color="secondary" variant="tonal">
            Buka Login OTP
          </VBtn>
          <VBtn :href="dashboardUrl" color="secondary" variant="tonal">
            Buka Dashboard
          </VBtn>
        </div>
      </VCardText>

      <VCardText class="pt-0">
        <VAlert type="warning" variant="tonal" density="compact">
          Jika OTP sukses tetapi tetap tidak ada akses, pastikan perangkat sudah terdaftar dan IP binding berhasil dibuat.
        </VAlert>
      </VCardText>
    </VCard>
  </div>
</template>
