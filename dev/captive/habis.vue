<script setup lang="ts">
import { definePageMeta, navigateTo, useHead } from '#imports'
import { computed, onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'

import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  auth: false,
})

useHead({ title: 'Kuota Habis - Portal Hotspot' })

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { smAndDown } = useDisplay()

// State management
const isLoading = ref(true)
const isCaptiveBrowser = ref(false)

// Computed properties
const user = computed(() => authStore.currentUser)
const adminContact = computed(() => settingsStore.settings?.ADMIN_WHATSAPP_NUMBER || '+62811580039')

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact.value)
  let text = 'Halo Admin, kuota internet saya telah habis dan butuh bantuan untuk pembelian paket.'

  if (user.value) {
    const nama = user.value.full_name || 'Tanpa Nama'
    const noHpPengguna = format_to_local_phone(user.value.phone_number) || 'Tidak terdaftar'
    text = `Halo Admin, kuota internet saya dengan detail berikut telah habis:\n\n*Nama:* ${nama}\n*No. Telepon:* ${noHpPengguna}\n\nMohon bantuannya untuk proses pembelian paket baru.`
  }

  return `https://wa.me/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})

const userPhone = computed(() => {
  if (!user.value?.phone_number)
    return ''
  return format_to_local_phone(user.value.phone_number)
})

const quotaInfo = computed(() => {
  if (!user.value)
    return null

  return {
    purchased: user.value.total_quota_purchased_mb || 0,
    used: user.value.total_quota_used_mb || 0,
    expiryDate: user.value.quota_expiry_date,
  }
})

// Captive browser detection
function detectCaptiveBrowser(): boolean {
  if (import.meta.server)
    return false

  const userAgent = navigator.userAgent
  const captivePatterns = [
    /CaptiveNetworkSupport/i,
    /Apple-captive/i,
    /iOS.*CaptiveNetworkSupport/i,
    /Android.*CaptivePortalLogin/i,
    /dalvik/i,
    /Microsoft-CryptoAPI/i,
    /Microsoft NCSI/i,
    /wispr/i,
    /CaptivePortal/i,
    /ConnectivityCheck/i,
    /NetworkProbe/i,
  ]

  return captivePatterns.some(pattern => pattern.test(userAgent))
}

function applyCaptiveBrowserOptimizations() {
  (window as any).__IS_CAPTIVE_BROWSER__ = true

  const style = document.createElement('style')
  style.innerHTML = `
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  `
  document.head.appendChild(style)
}

// Navigation functions
function goToBuyPage() {
  // FIXED: Always use captive/beli for quota finished users to avoid middleware redirect
  if (isCaptiveBrowser.value) {
    window.location.href = '/captive/beli?flow=captive'
  }
  else {
    // For quota finished users, always use captive beli to avoid middleware blocking
    navigateTo('/captive/beli')
  }
}

function contactAdmin() {
  const whatsappUrl = whatsappHref.value

  if (import.meta.client) {
    // Untuk captive browser, buka WhatsApp dengan cara khusus
    if (isCaptiveBrowser.value) {
      // Coba buka WhatsApp terlebih dahulu
      try {
        const whatsappApp = whatsappUrl.replace('https://wa.me/', 'whatsapp://send?phone=')
        window.location.href = whatsappApp

        // Fallback ke browser setelah delay
        setTimeout(() => {
          // Force redirect ke login captive setelah mencoba WhatsApp
          window.location.href = '/captive?source=whatsapp_fallback'
        }, 3000)
      }
      catch {
        // Jika gagal, langsung ke captive login
        window.location.href = '/captive?source=whatsapp_error'
      }
    }
    else {
      // Browser normal - buka WhatsApp biasa
      window.location.href = whatsappUrl
    }
  }
}

// Lifecycle
onMounted(async () => {
  if (import.meta.client) {
    isCaptiveBrowser.value = detectCaptiveBrowser()

    if (isCaptiveBrowser.value) {
      applyCaptiveBrowserOptimizations()
    }

    // OPTIONAL: Manual bypass disable (backend already handles this automatically)
    // This is mainly for immediate feedback and redundancy
    try {
      const { $api } = useNuxtApp()
      await $api('auth/disable-ip-binding', {
        method: 'POST',
        body: {
          reason: 'quota_exhausted',
        },
      })
      console.log('[QUOTA-HABIS] Bypass akses dinonaktifkan untuk efek langsung')
    }
    catch (error) {
      // This is not critical since backend handles bypass automatically
      console.warn('[QUOTA-HABIS] Nonaktifasi bypass gagal (backend akan menangani otomatis):', error)
    }
  }

  // Load settings
  isLoading.value = false
})
</script>

<template>
  <div class="quota-exhausted">
    <!-- Background -->
    <div class="background-pattern" />

    <!-- Loading overlay -->
    <VOverlay
      v-model="isLoading"
      persistent
      class="d-flex align-center justify-center"
    >
      <VProgressCircular
        indeterminate
        size="48"
        color="warning"
      />
      <div class="ml-4 text-body-1">
        Memuat informasi...
      </div>
    </VOverlay>

    <!-- Main content -->
    <div class="full-height-container">
      <VContainer
        fluid
        class="fill-height pa-0 d-flex align-center justify-center"
      >
        <VRow
          justify="center"
          align="center"
          class="fill-height ma-0"
          no-gutters
        >
          <VCol
            cols="12"
            sm="10"
            md="8"
            lg="6"
            xl="4"
            class="pa-4"
          >
            <!-- Main Card -->
            <VCard
              class="quota-card mx-auto"
              :elevation="smAndDown ? 0 : 24"
              rounded="xl"
            >
              <!-- Header -->
              <div class="quota-header">
                <div class="icon-container mb-6">
                  <svg
                    width="80"
                    height="80"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    class="warning-icon"
                  >
                    <path d="M12 9v4" />
                    <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636-2.87L13.637 3.59a1.914 1.914 0 0 0-3.274 0z" />
                    <path d="M12 16h.01" />
                  </svg>
                </div>

                <h1 class="quota-title">
                  Kuota Habis
                </h1>

                <p class="quota-subtitle">
                  Paket internet Anda telah habis
                </p>
              </div>

              <!-- Content -->
              <VCardText class="pa-6">
                <!-- User info -->
                <div v-if="user" class="user-info-card mb-6">
                  <div class="d-flex align-center mb-3">
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      class="text-primary mr-3"
                    >
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    <div>
                      <div class="text-body-1 font-weight-medium">
                        {{ user.full_name || 'Pengguna' }}
                      </div>
                      <div class="text-body-2 text-medium-emphasis">
                        {{ userPhone }}
                      </div>
                    </div>
                  </div>

                  <!-- Quota details -->
                  <div v-if="quotaInfo" class="quota-details">
                    <div class="d-flex justify-space-between align-center mb-2">
                      <span class="text-body-2 text-medium-emphasis">Kuota Dibeli:</span>
                      <VChip color="primary" size="small" variant="tonal">
                        {{ quotaInfo.purchased }} MB
                      </VChip>
                    </div>
                    <div class="d-flex justify-space-between align-center mb-2">
                      <span class="text-body-2 text-medium-emphasis">Kuota Terpakai:</span>
                      <VChip color="warning" size="small" variant="tonal">
                        {{ Math.round(quotaInfo.used) }} MB
                      </VChip>
                    </div>
                    <div v-if="quotaInfo.expiryDate" class="d-flex justify-space-between align-center">
                      <span class="text-body-2 text-medium-emphasis">Berlaku Hingga:</span>
                      <VChip color="error" size="small" variant="tonal">
                        {{ new Date(quotaInfo.expiryDate).toLocaleDateString('id-ID') }}
                      </VChip>
                    </div>
                  </div>
                </div>

                <!-- Status alert -->
                <VAlert
                  color="warning"
                  variant="tonal"
                  class="mb-6"
                  rounded="lg"
                >
                  <template #prepend>
                    <div class="alert-icon">
                      <svg
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                      >
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                    </div>
                  </template>

                  <VAlertTitle class="text-body-1 font-weight-bold">
                    Akses Internet Terbatas
                  </VAlertTitle>

                  <div class="text-body-2 mt-2">
                    Kuota internet Anda telah habis. Untuk melanjutkan browsing, silakan beli paket baru atau hubungi admin.
                  </div>
                </VAlert>

                <!-- Action buttons -->
                <div class="action-buttons">
                  <!-- Buy package button -->
                  <VBtn
                    color="primary"
                    size="large"
                    block
                    rounded="lg"
                    class="mb-3 font-weight-bold"
                    @click="goToBuyPage"
                  >
                    <template #prepend>
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="mr-2"
                      >
                        <circle cx="8" cy="21" r="1" />
                        <circle cx="19" cy="21" r="1" />
                        <path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12" />
                      </svg>
                    </template>
                    Beli Paket Internet
                  </VBtn>

                  <!-- Contact admin button -->
                  <VBtn
                    color="success"
                    variant="outlined"
                    size="large"
                    block
                    rounded="lg"
                    class="font-weight-bold"
                    @click="contactAdmin"
                  >
                    <template #prepend>
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="mr-2"
                      >
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                      </svg>
                    </template>
                    Hubungi Admin WhatsApp
                  </VBtn>
                </div>
              </VCardText>

              <!-- Footer -->
              <div class="quota-footer">
                <VDivider class="mb-4" />
                <div class="d-flex align-center justify-center">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    class="mr-2 text-medium-emphasis"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12,6 12,12 16,14" />
                  </svg>
                  <span class="text-caption text-medium-emphasis">
                    Kuota akan direset setelah pembelian paket baru
                  </span>
                </div>
              </div>
            </VCard>
          </VCol>
        </VRow>
      </VContainer>
    </div>
  </div>
</template>

<style scoped>
.quota-exhausted {
  min-height: 100vh;
  min-height: 100dvh; /* Support for dynamic viewport height */
  position: relative;
  background: linear-gradient(135deg,
    rgba(var(--v-theme-warning), 0.08) 0%,
    rgba(var(--v-theme-error), 0.08) 100%);
  overflow-y: auto; /* Allow scrolling */
}

.full-height-container {
  position: relative; /* Changed from absolute */
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px 0; /* Add padding for mobile scroll */
}

.background-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    radial-gradient(circle at 25% 75%, rgba(var(--v-theme-warning), 0.1) 0%, transparent 50%),
    radial-gradient(circle at 75% 25%, rgba(var(--v-theme-error), 0.1) 0%, transparent 50%);
  background-size: 400px 400px, 300px 300px;
  animation: float 20s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0px) rotate(0deg); }
  50% { transform: translateY(-20px) rotate(2deg); }
}

.quota-card {
  backdrop-filter: blur(20px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(var(--v-theme-warning), 0.2);
  max-width: 500px;
  overflow: hidden;
}

.quota-header {
  text-align: center;
  padding: 3rem 2rem 1.5rem;
  background: linear-gradient(135deg,
    rgba(var(--v-theme-warning), 0.1) 0%,
    rgba(var(--v-theme-warning), 0.05) 100%);
  border-bottom: 1px solid rgba(var(--v-theme-warning), 0.2);
}

.icon-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 120px;
  height: 120px;
  background: linear-gradient(135deg,
    rgb(var(--v-theme-warning)),
    rgb(var(--v-theme-error)));
  border-radius: 30px;
  margin: 0 auto;
  box-shadow:
    0 8px 32px rgba(var(--v-theme-warning), 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.1);
}

.warning-icon {
  color: white;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
}

.quota-title {
  font-size: 2.25rem;
  font-weight: 800;
  color: rgb(var(--v-theme-warning));
  margin-bottom: 0.5rem;
  letter-spacing: -0.02em;
}

.quota-subtitle {
  font-size: 1.1rem;
  font-weight: 500;
  margin: 0;
  opacity: 0.9; /* Better visibility */
}

.alert-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgb(var(--v-theme-warning));
}

.alert-icon svg {
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
}

.user-info-card {
  background: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.15);
  border-radius: 16px;
  padding: 1.5rem;
}

.quota-details {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(var(--v-theme-outline), 0.2);
  gap: 0.5rem;
}

.action-buttons {
  margin-top: 1.5rem;
}

.alert-icon {
  display: flex;
  align-items: center;
  color: rgb(var(--v-theme-warning));
}

.quota-footer {
  padding: 1.5rem 2rem 2rem;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border-top: 1px solid rgba(var(--v-theme-outline), 0.1);
}

/* Dark theme adjustments */
.v-theme--dark .quota-card {
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(var(--v-theme-warning), 0.3);
}

.v-theme--dark .user-info-card {
  background: rgba(var(--v-theme-primary), 0.1);
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
}

.v-theme--dark .quota-footer {
  background: rgba(var(--v-theme-surface-variant), 0.1);
}

/* Mobile optimizations */
@media (max-width: 600px) {
  .quota-exhausted {
    background: rgb(var(--v-theme-surface));
  }

  .background-pattern {
    opacity: 0.3;
  }

  .quota-card {
    background: rgb(var(--v-theme-surface));
    box-shadow: none !important;
    border: none;
  }

  .quota-header {
    padding: 2rem 1.5rem 1rem;
  }

  .icon-container {
    width: 100px;
    height: 100px;
    border-radius: 25px;
  }

  .quota-title {
    font-size: 2rem;
  }

  .quota-subtitle {
    font-size: 1rem;
  }
}

/* Captive browser optimizations */
.__IS_CAPTIVE_BROWSER__ .quota-card {
  animation: none !important;
  transition: none !important;
}

.__IS_CAPTIVE_BROWSER__ .background-pattern {
  animation: none !important;
}
</style>
